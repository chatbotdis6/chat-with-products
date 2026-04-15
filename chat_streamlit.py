"""
Streamlit chat — replica exacta del flujo WhatsApp.

Incluye: platform_exhausted, slash commands (/reset, /help),
markdown→WhatsApp formatting, manejo de errores, debug info.

Run: streamlit run chat_streamlit.py
"""
import re
import logging
import streamlit as st

from chat.agent.chatbot import Chatbot
from chat.config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("streamlit_chat")


# ── Formatting (same as whatsapp_server.py) ─────────────────────────
def _markdown_to_whatsapp(text: str) -> str:
    """Convert Markdown → WhatsApp-compatible formatting."""
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^-{3,}$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── Slash commands (same as whatsapp_server.py) ─────────────────────
_SLASH_COMMANDS = {
    "/reset", "/reiniciar", "/nuevo",
    "/help", "/ayuda", "/comandos",
}


def _handle_slash_command(cmd: str) -> str | None:
    """Handle a slash command. Returns the response or None if not a command."""
    cmd = cmd.lower().strip()

    if cmd in ("/reset", "/reiniciar", "/nuevo"):
        st.session_state.bot.reset()
        st.session_state.messages = []
        return (
            "✅ Conversación reiniciada.\n\n"
            "¡Hola! Soy el asistente de *The Hap & D Company*. "
            "¿En qué te puedo ayudar? 😊"
        )

    if cmd in ("/help", "/ayuda", "/comandos"):
        return (
            "📋 *Comandos disponibles:*\n\n"
            "/reset — Reiniciar conversación desde cero\n"
            "/help — Ver esta ayuda\n\n"
            "También puedes escribirme cualquier producto que busques, "
            "por ejemplo: _busco aceite de oliva_ 🫒"
        )

    return None


# ── Platform exhausted check (same as whatsapp_server.py) ───────────
def _get_platform_exhausted_response() -> str | None:
    """If platform is exhausted, return fixed message (0 tokens)."""
    bot = st.session_state.bot
    if bot.state.get("platform_exhausted", False):
        return (
            f"¡Gracias por usar nuestro chat! 😊 Para seguir explorando todos los "
            f"productos gastronómicos y proveedores líderes en la CDMX, accede sin "
            f"costo a {settings.PLATFORM_URL} — no necesitas registrarte para "
            f"consultar todo lo que manejamos."
        )
    return None


# ── Process message (same flow as whatsapp_server._process_and_reply)
def _process_message(user_message: str) -> str:
    """Full processing pipeline — identical to WhatsApp flow."""
    # 1. Slash command?
    slash_response = _handle_slash_command(user_message)
    if slash_response is not None:
        return slash_response

    # 2. Platform exhausted?
    exhausted = _get_platform_exhausted_response()
    if exhausted:
        logger.info("🚫 Platform exhausted — fixed message (0 tokens)")
        return exhausted

    # 3. Call the LLM
    try:
        bot = st.session_state.bot
        response = bot.chat(user_message)
        response = _markdown_to_whatsapp(response)
        return response
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        return "Lo siento, tuve un problema procesando tu mensaje. ¿Puedes intentar de nuevo? 😊"


# ── Streamlit UI ────────────────────────────────────────────────────
st.set_page_config(page_title="Hap & D — Chat", page_icon="🤖")
st.title("🤖 The Hap & D Company")
st.caption("Asistente de búsqueda de proveedores gastronómicos")

# Session state
if "bot" not in st.session_state:
    st.session_state.bot = Chatbot(session_id="streamlit")
if "messages" not in st.session_state:
    st.session_state.messages = []

bot = st.session_state.bot

# Sidebar — debug info
with st.sidebar:
    st.header("📊 Estado")
    st.write(f"**Turno:** {bot.turn_number}")
    st.write(f"**Plataforma agotada:** {'🔴 Sí' if bot.state.get('platform_exhausted') else '🟢 No'}")
    st.write(f"**Mensajes en historial:** {len(bot.state.get('messages', []))}")
    st.divider()

    st.header("⚙️ Config")
    st.caption(f"Aviso plataforma: turno {settings.CONSULTAS_ANTES_DERIVACION}")
    st.caption(f"Bloqueo plantilla: turno {settings.CONSULTAS_ANTES_PLANTILLA}")
    st.caption(f"Plataforma: {settings.PLATFORM_URL}")
    st.divider()

    st.header("💡 Comandos")
    st.caption("/reset — Reiniciar conversación")
    st.caption("/help — Ver ayuda")
    st.divider()

    if st.button("🔄 Reiniciar conversación"):
        bot.reset()
        st.session_state.messages = []
        st.rerun()

# Chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# User input
if prompt := st.chat_input("Escribe tu mensaje…"):
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process (same flow as WhatsApp)
    is_slash = prompt.lower().strip() in _SLASH_COMMANDS
    with st.chat_message("assistant"):
        if is_slash:
            response = _process_message(prompt)
        else:
            with st.spinner("Pensando…"):
                response = _process_message(prompt)
        st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})

    # If it was /reset, clear the displayed messages and rerun
    if prompt.lower().strip() in ("/reset", "/reiniciar", "/nuevo"):
        st.session_state.messages = []
        st.rerun()

    # Rerun to update sidebar counters
    st.rerun()
