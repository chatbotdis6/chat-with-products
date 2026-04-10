"""
Chatbot — Tool-calling agent orchestrator.

Public API:
  - chat(message) → str
  - chat_with_metadata(message) → (str, dict)
  - get_history() → list[(role, content)]
  - reset()

Uses a 2-node agent graph: the LLM decides the flow by choosing
tools instead of following a hardcoded pipeline.
"""
import logging
import uuid
from typing import Optional, Dict, Any, List, Tuple

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from chat.agent.graph import (
    AgentState,
    create_initial_agent_state,
    get_agent_graph,
)
from chat.config.settings import settings

logger = logging.getLogger(__name__)


class Chatbot:
    """
    Tool-calling agent chatbot for The Hap & D Company.

    The LLM decides the flow by choosing tools instead of following
    a hardcoded router → query → response pipeline.

    Usage:
        bot = Chatbot()
        response = bot.chat("Busco aceite de oliva")

        # With session (WhatsApp)
        bot = Chatbot(session_id="+5255XXXXXXXX")
        response = bot.chat("Busco aceite de oliva")
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        user_phone: Optional[str] = None,
    ):
        self.session_id = session_id or str(uuid.uuid4())
        self.user_phone = user_phone

        self.state: AgentState = create_initial_agent_state(
            session_id=self.session_id,
            user_phone=user_phone,
        )
        self.graph = get_agent_graph()
        logger.info(f"✅ Chatbot initialized (session: {self.session_id[:8]}…)")

    # ── Main entry point ────────────────────────────────────────────
    def chat(self, message: str) -> str:
        """Process a user message and return the response."""
        turn = self.state.get("turn_number", 0)
        logger.info(f"💬 USER: '{message[:80]}' | session={self.session_id[:8]} | turn={turn}")

        user_msg = HumanMessage(content=message)

        input_state: AgentState = {
            **self.state,
            "messages": self.state.get("messages", []) + [user_msg],
        }

        try:
            config = {"configurable": {"thread_id": self.session_id}}
            result = self.graph.invoke(input_state, config)

            # Increment turn
            result["turn_number"] = turn + 1

            # Persist state
            self.state = result

            # Extract response from last AI message
            response = self._extract_response(result)
            logger.info(f"🤖 RESPONSE: '{response[:100]}…'")
            return response

        except Exception as e:
            logger.error(f"❌ Chatbot error: {e}", exc_info=True)
            return "Lo siento, hubo un error procesando tu mensaje. ¿Puedes intentar de nuevo? 😊"

    # ── With metadata ───────────────────────────────────────────────
    def chat_with_metadata(self, message: str) -> Tuple[str, Dict[str, Any]]:
        """Process a message and return (response, metadata)."""
        response = self.chat(message)
        metadata = {
            "session_id": self.session_id,
            "turn_number": self.state.get("turn_number", 0),
            "platform_exhausted": self.state.get("platform_exhausted", False),
        }
        return response, metadata

    # ── History ─────────────────────────────────────────────────────
    def get_history(self) -> List[Tuple[str, str]]:
        """Get conversation history as [(role, content)] tuples."""
        history = []
        for msg in self.state.get("messages", []):
            if isinstance(msg, HumanMessage):
                history.append(("user", msg.content))
            elif isinstance(msg, AIMessage) and msg.content:
                history.append(("assistant", msg.content))
        return history

    def get_messages(self) -> List[BaseMessage]:
        """Get raw LangChain messages."""
        return self.state.get("messages", [])

    # ── Reset ───────────────────────────────────────────────────────
    def reset(self):
        """Reset conversation state."""
        logger.info(f"🔄 Resetting session: {self.session_id[:8]}…")
        self.state = create_initial_agent_state(
            session_id=self.session_id,
            user_phone=self.user_phone,
        )

    # ── Properties ──────────────────────────────────────────────────
    @property
    def turn_number(self) -> int:
        return self.state.get("turn_number", 0)

    @property
    def last_intent(self) -> str:
        return ""

    @property
    def last_search_results(self) -> Optional[Dict]:
        return None

    # ── Internal ────────────────────────────────────────────────────
    @staticmethod
    def _extract_response(state: AgentState) -> str:
        """Extract the final text response from agent messages."""
        messages = state.get("messages", [])
        # Walk backwards to find the last AIMessage with content
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content
        return "Lo siento, no pude generar una respuesta. ¿Puedes repetir? 😊"
