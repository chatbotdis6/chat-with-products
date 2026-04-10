"""
WhatsApp Webhook Server for Twilio.

This server receives WhatsApp messages from Twilio, processes them
through the ChatbotV2 (LangGraph), and sends back the response.

Usage:
    # Development (with auto-reload)
    uvicorn whatsapp_server:app --reload --port 8000

    # Production
    uvicorn whatsapp_server:app --host 0.0.0.0 --port 8000 --workers 2

    # Expose via ngrok for Twilio webhook
    ngrok http 8000
"""
import os
import re
import asyncio
import logging
import hmac
import hashlib
from typing import Optional
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from twilio.rest import Client as TwilioClient
from twilio.request_validator import RequestValidator

from chat.chatbot_v2 import ChatbotV2
from chat.config.settings import settings

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "")  # e.g. "whatsapp:+14155238886"
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "")  # e.g. "https://xxxx.ngrok-free.app"
VALIDATE_TWILIO_SIGNATURE = os.getenv("VALIDATE_TWILIO_SIGNATURE", "true").lower() == "true"

# Twilio message size limit
WHATSAPP_MAX_LENGTH = 1600

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("whatsapp_server")

# ──────────────────────────────────────────────
# Session store (phone → ChatbotV2)
# ──────────────────────────────────────────────
_sessions: dict[str, ChatbotV2] = {}
_session_locks: dict[str, asyncio.Lock] = {}


def _get_session_lock(phone: str) -> asyncio.Lock:
    """Get or create a lock for this phone number to serialize messages."""
    if phone not in _session_locks:
        _session_locks[phone] = asyncio.Lock()
    return _session_locks[phone]


def _get_or_create_bot(phone: str) -> ChatbotV2:
    """Get existing session or create a new one for this phone number."""
    if phone not in _sessions:
        logger.info(f"🆕 New session for {phone}")
        _sessions[phone] = ChatbotV2(
            session_id=phone,
            user_phone=phone,
            use_persistence=True,
        )
    return _sessions[phone]


# ──────────────────────────────────────────────
# Twilio signature validation
# ──────────────────────────────────────────────
_validator: Optional[RequestValidator] = None


def _get_validator() -> Optional[RequestValidator]:
    global _validator
    if _validator is None and TWILIO_AUTH_TOKEN:
        _validator = RequestValidator(TWILIO_AUTH_TOKEN)
    return _validator


async def _validate_twilio_request(request: Request, body_params: dict) -> bool:
    """Validate that the request actually comes from Twilio."""
    if not VALIDATE_TWILIO_SIGNATURE:
        return True

    validator = _get_validator()
    if not validator:
        logger.warning("⚠️  No TWILIO_AUTH_TOKEN set — skipping signature validation")
        return True

    # Reconstruct the full URL Twilio used to call us
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)

    # If behind a proxy/ngrok, use the configured base URL
    if WEBHOOK_BASE_URL:
        url = f"{WEBHOOK_BASE_URL}/webhook"

    is_valid = validator.validate(url, body_params, signature)
    if not is_valid:
        logger.warning(f"⚠️  Invalid Twilio signature for {url}")
    return is_valid


# ──────────────────────────────────────────────
# WhatsApp text formatting
# ──────────────────────────────────────────────
def _markdown_to_whatsapp(text: str) -> str:
    """
    Convert Markdown formatting to WhatsApp-compatible formatting.
    
    WhatsApp supports:
      *bold*  _italic_  ~strikethrough~  ```monospace```
    
    Markdown uses:
      **bold**  *italic*  ~~strike~~  `code`
    """
    # **bold** → *bold*
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    # [link text](url) → link text (url)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)
    # Remove ### headers (keep text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove horizontal rules
    text = re.sub(r'^-{3,}$', '', text, flags=re.MULTILINE)
    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _split_message(text: str, max_length: int = WHATSAPP_MAX_LENGTH) -> list[str]:
    """
    Split a long message into chunks that fit WhatsApp's limit.
    Splits on paragraph boundaries when possible.
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    current = ""

    for paragraph in text.split("\n\n"):
        # If adding this paragraph would exceed the limit
        if len(current) + len(paragraph) + 2 > max_length:
            if current:
                chunks.append(current.strip())
                current = ""
            # If a single paragraph exceeds the limit, split by lines
            if len(paragraph) > max_length:
                for line in paragraph.split("\n"):
                    if len(current) + len(line) + 1 > max_length:
                        if current:
                            chunks.append(current.strip())
                        current = line
                    else:
                        current = f"{current}\n{line}" if current else line
            else:
                current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph

    if current:
        chunks.append(current.strip())

    return chunks


# ──────────────────────────────────────────────
# Twilio client (for sending multi-part messages)
# ──────────────────────────────────────────────
_twilio_client: Optional[TwilioClient] = None


def _get_twilio_client() -> Optional[TwilioClient]:
    global _twilio_client
    if _twilio_client is None and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        _twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return _twilio_client


def _send_whatsapp(to: str, body: str):
    """Send a WhatsApp message via Twilio REST API."""
    client = _get_twilio_client()
    if not client:
        logger.error("❌ Twilio client not initialized — check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN")
        return
    
    client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=to,
        body=body,
    )


# ──────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("🚀 WhatsApp Webhook Server starting...")
    logger.info(f"   Twilio number: {TWILIO_WHATSAPP_NUMBER or '⚠️  NOT SET'}")
    logger.info(f"   Signature validation: {'ON' if VALIDATE_TWILIO_SIGNATURE else 'OFF'}")
    logger.info(f"   Webhook URL: {WEBHOOK_BASE_URL or '⚠️  NOT SET (use ngrok URL)'}")
    
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.warning("⚠️  TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not set!")
        logger.warning("   Set them in .env to enable WhatsApp messaging")
    
    yield
    
    # Cleanup
    logger.info("👋 Server shutting down — closing sessions...")
    _sessions.clear()


app = FastAPI(
    title="The Hap & D Company — WhatsApp Bot",
    description="Webhook server for Twilio WhatsApp integration",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "active_sessions": len(_sessions),
        "twilio_configured": bool(TWILIO_ACCOUNT_SID),
    }


@app.post("/webhook")
async def whatsapp_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...),
    ProfileName: str = Form(default=""),
    NumMedia: str = Form(default="0"),
):
    """
    Twilio WhatsApp webhook endpoint.
    
    Twilio sends a POST with form data:
      - From: "whatsapp:+5215512345678"
      - Body: "busco aceite de oliva"
      - ProfileName: "Carlos"
      - NumMedia: "0"
    """
    # ── 1. Validate Twilio signature ──
    body_params = dict(await request.form())
    if not await _validate_twilio_request(request, body_params):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    # ── 2. Extract phone number ──
    phone = From.replace("whatsapp:", "")
    user_message = Body.strip()
    
    logger.info(f"📱 ══════════════════════════════════════════")
    logger.info(f"📱 FROM: {phone} ({ProfileName})")
    logger.info(f"📱 MSG:  '{user_message[:100]}'")

    # ── 3. Ignore media-only messages ──
    if int(NumMedia) > 0 and not user_message:
        logger.info("📎 Media-only message, ignoring")
        return PlainTextResponse(
            content="",
            status_code=200,
            media_type="text/xml",
        )

    # ── 4. Ignore empty messages ──
    if not user_message:
        return PlainTextResponse(content="", status_code=200)

    # ── 4b. Handle slash commands ──
    cmd = user_message.lower().strip()
    if cmd in ("/reset", "/reiniciar", "/nuevo"):
        # Remove from in-memory sessions
        if phone in _sessions:
            del _sessions[phone]
        # Create a fresh bot (overwrites any persisted state)
        fresh_bot = ChatbotV2(
            session_id=phone,
            user_phone=phone,
            use_persistence=True,
        )
        fresh_bot.state["messages"] = []
        fresh_bot.state["turn_number"] = 0
        _sessions[phone] = fresh_bot

        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            "<Message>✅ Conversación reiniciada.\n\n"
            "¡Hola! Soy el asistente de *The Hap &amp; D Company*. "
            "¿En qué te puedo ayudar? 😊</Message>"
            "</Response>"
        )
        logger.info(f"🔄 Session reset for {phone}")
        return PlainTextResponse(content=twiml, media_type="text/xml")

    if cmd in ("/help", "/ayuda", "/comandos"):
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            "<Message>📋 *Comandos disponibles:*\n\n"
            "/reset — Reiniciar conversación desde cero\n"
            "/help — Ver esta ayuda\n\n"
            "También puedes escribirme cualquier producto que busques, "
            "por ejemplo: _busco aceite de oliva_ 🫒</Message>"
            "</Response>"
        )
        return PlainTextResponse(content=twiml, media_type="text/xml")

    # ── 5. Respond immediately, process in background ──
    # Twilio has a 15-second timeout for webhooks. LLM calls can take
    # longer, so we return an empty TwiML immediately and send the
    # actual response asynchronously via the Twilio REST API.
    asyncio.create_task(_process_and_reply(phone, From, user_message))

    # Empty TwiML — the real reply is sent via REST API in the background task
    return PlainTextResponse(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="text/xml",
    )


async def _process_and_reply(phone: str, twilio_from: str, user_message: str):
    """Process the user message in background and send reply via REST API.
    
    Uses a per-phone lock to serialize messages from the same user,
    preventing race conditions when multiple messages arrive before
    the bot responds.
    """
    lock = _get_session_lock(phone)
    async with lock:
        await _process_and_reply_locked(phone, twilio_from, user_message)


async def _process_and_reply_locked(phone: str, twilio_from: str, user_message: str):
    """Actual message processing (runs under session lock)."""
    try:
        bot = _get_or_create_bot(phone)
        logger.info(f"🔑 Bot id={id(bot)}, sessions={list(_sessions.keys())}, "
                    f"state.turn={bot.state.get('turn_number', '?')}, "
                    f"state.search_filters={bot.state.get('search_filters', 'MISSING')}")

        # ── Check if platform is exhausted (no LLM needed) ──
        if bot.state.get("platform_exhausted", False):
            platform_url = settings.PLATFORM_URL
            response = (
                f"Ya te hemos derivado a nuestra Plataforma donde encontrarás "
                f"todo lo que necesitas:\n\n"
                f"👉 {platform_url}\n\n"
                f"Si necesitas ayuda adicional, escríbenos por ahí. ¡Gracias! 😊"
            )
            logger.info(f"🚫 Platform exhausted for {phone} — returning fixed message (0 tokens)")
            _send_whatsapp(twilio_from, response)
            return

        # Run the (blocking) LLM call in a thread so we don't block the event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, bot.chat, user_message)

        # Format for WhatsApp
        response = _markdown_to_whatsapp(response)

        logger.info(f"🤖 RESP: '{response[:150]}'")
        logger.info(f"📱 ══════════════════════════════════════════")

        # Send response (may be multiple chunks)
        chunks = _split_message(response)
        for i, chunk in enumerate(chunks):
            if len(chunks) > 1:
                logger.info(f"   📤 Sending part {i+1}/{len(chunks)} ({len(chunk)} chars)")
            _send_whatsapp(twilio_from, chunk)

    except Exception as e:
        logger.error(f"❌ Background processing error for {phone}: {e}", exc_info=True)
        try:
            _send_whatsapp(
                twilio_from,
                "Lo siento, tuve un problema procesando tu mensaje. ¿Puedes intentar de nuevo? 😊",
            )
        except Exception as send_err:
            logger.error(f"❌ Failed to send error message: {send_err}")


def _escape_xml(text: str) -> str:
    """Escape special XML characters."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


# ──────────────────────────────────────────────
# Admin endpoints (optional, for debugging)
# ──────────────────────────────────────────────
@app.get("/sessions")
async def list_sessions():
    """List active sessions (for debugging)."""
    return {
        "total": len(_sessions),
        "sessions": [
            {
                "phone": phone,
                "turn": bot.turn_number,
                "last_intent": bot.last_intent,
            }
            for phone, bot in _sessions.items()
        ],
    }


@app.delete("/sessions/{phone}")
async def reset_session(phone: str):
    """Reset a specific session (for debugging)."""
    phone_with_plus = f"+{phone}" if not phone.startswith("+") else phone
    if phone_with_plus in _sessions:
        _sessions[phone_with_plus].reset()
        del _sessions[phone_with_plus]
        return {"status": "reset", "phone": phone_with_plus}
    return {"status": "not_found", "phone": phone_with_plus}


# ──────────────────────────────────────────────
# Run with: uvicorn whatsapp_server:app --reload
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "whatsapp_server:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
