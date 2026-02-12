"""
Main Conversation Graph - LangGraph state machine.

This module assembles all nodes into a coherent conversation flow
using LangGraph's StateGraph.
"""
import logging
from typing import Dict, Any, Literal

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage

from chat.graph.state import (
    ConversationState, 
    IntentCategory,
    RelevanciaLevel,
    DifficultUserType,
    create_initial_state,
)
from chat.graph.nodes.router import router_node
from chat.graph.nodes.query import query_node
from chat.graph.nodes.specialist import specialist_node
from chat.graph.nodes.response import response_node
from chat.graph.nodes.transition import transition_node
from chat.graph.nodes.unregistered import unregistered_product_node
from chat.graph.nodes.difficult_user import difficult_user_node
from chat.config.settings import settings

logger = logging.getLogger(__name__)


# Define node names
ROUTER = "router"
QUERY = "query"
SPECIALIST = "specialist"
RESPONSE = "response"
TRANSITION = "transition"
UNREGISTERED = "unregistered"
DIFFICULT = "difficult_user"
PLATFORM_BLOCK = "platform_block"


def _platform_block_node(state: ConversationState) -> Dict[str, Any]:
    """
    Platform block node — returns fixed template without any LLM call.
    Activated on turn 6+ (after derivation was shown on turn 5).
    """
    turn_number = state.get("turn_number", 0)
    platform_url = settings.PLATFORM_URL
    
    logger.info(f"🚫 PLATFORM BLOCK: Turn {turn_number} — fixed template (0 tokens)")
    response = (
        f"Para brindarte la mejor experiencia, te invitamos a continuar "
        f"en nuestra *Plataforma*, donde podrás:\n\n"
        f"✅ Ver todos los proveedores y marcas\n"
        f"✅ Armar cuadros comparativos de precios\n"
        f"✅ Filtrar por zona, marca y presentación\n"
        f"✅ Contactar proveedores directamente\n\n"
        f"👉 {platform_url}\n\n"
        f"¡Gracias por usar nuestro chat! 😊"
    )
    
    return {
        "response": response,
        "platform_exhausted": True,
    }


def _route_after_router(state: ConversationState) -> str:
    """
    Determine the next node after routing.
    
    Decision logic:
    0. If turn >= DERIVACION threshold → platform_block (NO LLM)
    1. If difficult user → difficult_user node
    2. If specialist intent → specialist node
    3. If requires search → query node
    4. Otherwise → response node (for simple intents)
    """
    turn_number = state.get("turn_number", 0)
    is_difficult = state.get("is_difficult_user", False)
    difficult_type = state.get("difficult_type", "")
    intent = state.get("intent", "")
    requires_search = state.get("requires_search", False)
    
    logger.info(f"🔀 Routing after router: difficult={is_difficult}, "
               f"intent={intent}, requires_search={requires_search}")
    
    # ── PLATFORM BLOCK: Turn 6+ → fixed template, no LLM at all ──
    # Turn 5 (derivación) still goes through normal search + TRANSITION appends the warning
    if turn_number >= settings.CONSULTAS_ANTES_PLANTILLA and intent not in ["saludo", "despedida", "agradecimiento", "fuera_alcance"]:
        logger.info(f"🔀 → PLATFORM_BLOCK (turn {turn_number} ≥ {settings.CONSULTAS_ANTES_PLANTILLA})")
        return PLATFORM_BLOCK
    
    # Difficult user (insultos, quejas, etc.) — MUST be checked BEFORE fuera_alcance
    # because router may set both difficult=True AND intent=fuera_alcance for insults
    if is_difficult:
        logger.info(f"🔀 → DIFFICULT_USER (type: {difficult_type})")
        return DIFFICULT
    
    # fuera_alcance → UNREGISTERED for classification + email
    # This ensures gastronomic products get the 12h promise + email to team
    if intent == "fuera_alcance":
        logger.info(f"🔀 → UNREGISTERED (fuera_alcance)")
        return UNREGISTERED
    
    # Specialist intents
    specialist_intents = ["chef", "nutriologo", "bartender", "barista", "ingeniero_alimentos"]
    if intent in specialist_intents:
        logger.info(f"🔀 → SPECIALIST ({intent})")
        return SPECIALIST
    
    # Search-related intents
    if requires_search or intent in ["busqueda_proveedores", "filtrar_marca", "filtrar_precio", "mostrar_mas", "detalle_proveedor"]:
        logger.info(f"🔀 → QUERY")
        return QUERY
    
    # Simple intents go directly to response
    logger.info(f"🔀 → RESPONSE (simple intent: {intent})")
    return RESPONSE


def _route_after_query(state: ConversationState) -> str:
    """
    Determine the next node after query.
    
    Decision logic:
    1. If nivel_relevancia is NULA → unregistered product handling
    2. Otherwise → response node
    """
    nivel_relevancia = state.get("nivel_relevancia", "")
    
    logger.info(f"🔀 Routing after query: relevancia={nivel_relevancia}")
    
    if nivel_relevancia == RelevanciaLevel.NULA.value:
        logger.info(f"🔀 → UNREGISTERED (no results)")
        return UNREGISTERED
    
    logger.info(f"🔀 → RESPONSE")
    return RESPONSE


def _route_after_response(state: ConversationState) -> str:
    """
    Determine if we should add platform transition.
    
    Always go to transition node to check if we should add suggestion.
    """
    logger.info(f"🔀 → TRANSITION")
    return TRANSITION


def _finalize_state(state: ConversationState) -> Dict[str, Any]:
    """
    Finalize the state before returning.
    
    This node:
    1. Increments turn number
    2. Adds AI message to history
    """
    response = state.get("response", "")
    turn_number = state.get("turn_number", 0)
    
    # Increment turn
    new_turn = turn_number + 1
    
    # Add AI message to history
    if response:
        new_message = AIMessage(content=response)
        return {
            "turn_number": new_turn,
            "messages": [new_message],
        }
    
    return {"turn_number": new_turn}


def create_conversation_graph() -> StateGraph:
    """
    Create the main conversation graph.
    
    Graph structure:
    
    START → router → [routing decision]
                     ├─ difficult_user → finalize → END
                     ├─ specialist → transition → finalize → END
                     └─ query → [query decision]
                                ├─ unregistered → finalize → END
                                └─ response → transition → finalize → END
    
    Returns:
        Compiled StateGraph ready for use
    """
    logger.info("🔧 Building conversation graph...")
    
    # Create the graph
    workflow = StateGraph(ConversationState)
    
    # Add nodes
    workflow.add_node(ROUTER, router_node)
    workflow.add_node(QUERY, query_node)
    workflow.add_node(SPECIALIST, specialist_node)
    workflow.add_node(RESPONSE, response_node)
    workflow.add_node(TRANSITION, transition_node)
    workflow.add_node(UNREGISTERED, unregistered_product_node)
    workflow.add_node(DIFFICULT, difficult_user_node)
    workflow.add_node(PLATFORM_BLOCK, _platform_block_node)
    workflow.add_node("finalize", _finalize_state)
    
    # Set entry point
    workflow.set_entry_point(ROUTER)
    
    # Add conditional edges from router
    workflow.add_conditional_edges(
        ROUTER,
        _route_after_router,
        {
            DIFFICULT: DIFFICULT,
            SPECIALIST: SPECIALIST,
            QUERY: QUERY,
            RESPONSE: RESPONSE,
            UNREGISTERED: UNREGISTERED,
            PLATFORM_BLOCK: PLATFORM_BLOCK,
        }
    )
    
    # Add conditional edges from query
    workflow.add_conditional_edges(
        QUERY,
        _route_after_query,
        {
            UNREGISTERED: UNREGISTERED,
            RESPONSE: RESPONSE,
        }
    )
    
    # Add edges from specialist/response to transition
    workflow.add_edge(SPECIALIST, TRANSITION)
    workflow.add_edge(RESPONSE, TRANSITION)
    workflow.add_edge(UNREGISTERED, "finalize")
    workflow.add_edge(DIFFICULT, "finalize")
    workflow.add_edge(PLATFORM_BLOCK, "finalize")  # Skip transition — already has the message
    
    # Transition always goes to finalize
    workflow.add_edge(TRANSITION, "finalize")
    
    # Finalize goes to END
    workflow.add_edge("finalize", END)
    
    logger.info("✅ Conversation graph built successfully")
    
    return workflow.compile()


def create_conversation_graph_with_checkpointer(checkpointer):
    """
    Create the conversation graph with a checkpointer for persistence.
    
    Args:
        checkpointer: A LangGraph checkpointer (e.g., PostgresSaver)
        
    Returns:
        Compiled StateGraph with persistence
    """
    logger.info("🔧 Building conversation graph with checkpointer...")
    
    # Create the graph
    workflow = StateGraph(ConversationState)
    
    # Add nodes
    workflow.add_node(ROUTER, router_node)
    workflow.add_node(QUERY, query_node)
    workflow.add_node(SPECIALIST, specialist_node)
    workflow.add_node(RESPONSE, response_node)
    workflow.add_node(TRANSITION, transition_node)
    workflow.add_node(UNREGISTERED, unregistered_product_node)
    workflow.add_node(DIFFICULT, difficult_user_node)
    workflow.add_node(PLATFORM_BLOCK, _platform_block_node)
    workflow.add_node("finalize", _finalize_state)
    
    # Set entry point
    workflow.set_entry_point(ROUTER)
    
    # Add conditional edges from router
    workflow.add_conditional_edges(
        ROUTER,
        _route_after_router,
        {
            DIFFICULT: DIFFICULT,
            SPECIALIST: SPECIALIST,
            QUERY: QUERY,
            RESPONSE: RESPONSE,
            UNREGISTERED: UNREGISTERED,
            PLATFORM_BLOCK: PLATFORM_BLOCK,
        }
    )
    
    # Add conditional edges from query
    workflow.add_conditional_edges(
        QUERY,
        _route_after_query,
        {
            UNREGISTERED: UNREGISTERED,
            RESPONSE: RESPONSE,
        }
    )
    
    # Add edges from specialist/response to transition
    workflow.add_edge(SPECIALIST, TRANSITION)
    workflow.add_edge(RESPONSE, TRANSITION)
    workflow.add_edge(UNREGISTERED, "finalize")
    workflow.add_edge(DIFFICULT, "finalize")
    workflow.add_edge(PLATFORM_BLOCK, "finalize")  # Skip transition — already has the message
    
    # Transition always goes to finalize
    workflow.add_edge(TRANSITION, "finalize")
    
    # Finalize goes to END
    workflow.add_edge("finalize", END)
    
    logger.info("✅ Conversation graph with checkpointer built successfully")
    
    return workflow.compile(checkpointer=checkpointer)


# Create a default graph instance
_default_graph = None


def get_conversation_graph():
    """Get or create the default conversation graph."""
    global _default_graph
    if _default_graph is None:
        _default_graph = create_conversation_graph()
    return _default_graph
