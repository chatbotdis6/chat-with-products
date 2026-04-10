"""
Agent Graph — 2-node tool-calling agent built with LangGraph.

Replaces the 9-node hardcoded graph with a simple loop:
  agent (LLM decides) → tools (execute) → agent (evaluate) → … → END

The LLM autonomously decides routing via tool selection instead of
a separate router node + Python conditionals.
"""
import logging
from typing import Dict, Any, Optional, List, Literal

from typing_extensions import TypedDict, Annotated
from operator import add

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    SystemMessage,
)

from chat.config.settings import settings
from chat.agent.tools import ALL_TOOLS
from chat.agent.prompts import build_agent_system_prompt

logger = logging.getLogger(__name__)


# ── State ───────────────────────────────────────────────────────────
class AgentState(TypedDict, total=False):
    """Minimal agent state — the LLM manages context via messages."""
    messages: Annotated[List[BaseMessage], add]
    session_id: str
    turn_number: int
    user_phone: Optional[str]
    platform_exhausted: bool


def create_initial_agent_state(
    session_id: str,
    user_phone: Optional[str] = None,
) -> AgentState:
    """Create blank state for a new conversation."""
    return AgentState(
        messages=[],
        session_id=session_id,
        turn_number=0,
        user_phone=user_phone,
        platform_exhausted=False,
    )


# ── Platform-block message (no LLM needed) ─────────────────────────
_PLATFORM_BLOCK_MSG = (
    f"Para brindarte la mejor experiencia, te invitamos a continuar "
    f"en nuestra *Plataforma*, donde podrás:\n\n"
    f"✅ Ver todos los proveedores y marcas\n"
    f"✅ Armar cuadros comparativos de precios\n"
    f"✅ Filtrar por zona, marca y presentación\n"
    f"✅ Contactar proveedores directamente\n\n"
    f"👉 {settings.PLATFORM_URL}\n\n"
    f"¡Gracias por usar nuestro chat! 😊"
)


# ── LLM with tools bound ───────────────────────────────────────────
_llm = ChatOpenAI(model=settings.ROUTER_MODEL, temperature=0.3)
_llm_with_tools = _llm.bind_tools(ALL_TOOLS)


# ── Nodes ───────────────────────────────────────────────────────────
def agent_node(state: AgentState) -> Dict[str, Any]:
    """Agent node: LLM reasons and optionally calls tools."""
    turn = state.get("turn_number", 0)

    # Platform block: turn 6+ → fixed template, skip LLM entirely
    if turn >= settings.CONSULTAS_ANTES_PLANTILLA:
        logger.info(f"🚫 PLATFORM BLOCK: Turn {turn} — fixed template (0 tokens)")
        return {
            "messages": [AIMessage(content=_PLATFORM_BLOCK_MSG)],
            "platform_exhausted": True,
        }

    # Build system prompt (includes soft/strong platform suggestion)
    system_prompt = build_agent_system_prompt(turn_number=turn)

    msgs = [SystemMessage(content=system_prompt)] + state.get("messages", [])

    logger.info(f"🤖 Agent LLM call (turn {turn}, {len(msgs)} messages)")
    response = _llm_with_tools.invoke(msgs)
    logger.info(
        f"🤖 Agent response: tool_calls={len(response.tool_calls) if response.tool_calls else 0}, "
        f"content_len={len(response.content) if response.content else 0}"
    )
    return {"messages": [response]}


def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    """Route: if the LLM issued tool calls → execute them; else → END."""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


# ── Build graph ─────────────────────────────────────────────────────
def create_agent_graph() -> StateGraph:
    """Create the 2-node tool-calling agent graph.

    Graph:
        START → agent → [tool_calls?]
                         ├─ yes → tools → agent (loop)
                         └─ no  → END
    """
    logger.info("🔧 Building agent graph (2-node tool-calling)…")

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(ALL_TOOLS))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, ["tools", END])
    graph.add_edge("tools", "agent")

    logger.info("✅ Agent graph built successfully")
    return graph.compile()


# ── Singleton ───────────────────────────────────────────────────────
_default_agent_graph = None


def get_agent_graph():
    """Get or create the default agent graph (singleton)."""
    global _default_agent_graph
    if _default_agent_graph is None:
        _default_agent_graph = create_agent_graph()
    return _default_agent_graph
