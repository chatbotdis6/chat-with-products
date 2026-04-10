"""
Transition Node - Suggests platform transition at appropriate moments.

This node implements Task 8: At appropriate conversation points, suggest
the user transition to the full web platform for advanced features.
"""
import logging
from typing import Dict, Any

from chat.graph.state import ConversationState, NodeOutput, IntentCategory
from chat.config.settings import settings

logger = logging.getLogger(__name__)


# Turn threshold for soft suggestion (turns 1-4 only reach this node)
TURN_THRESHOLD_SOFT = 3   # First gentle suggestion


def _generate_platform_message(
    turn_number: int,
    proveedores_ocultos: int = 0,
    marcas_disponibles: int = 0,
    is_price_query: bool = False,
) -> str:
    """Generate an appropriate platform transition message based on context.
    
    Note: This function only receives turns 1-4 because graph.py routes
    turn >= CONSULTAS_ANTES_PLANTILLA (5) directly to PLATFORM_BLOCK.
    """
    platform_url = settings.PLATFORM_URL
    
    # Price comparison - always suggest platform
    if is_price_query:
        return (
            f"\n\n💡 En nuestra **Plataforma** puedes ver todos los proveedores y "
            f"armar un cuadro comparativo con precios actualizados: {platform_url}"
        )
    
    # Many hidden providers - highlight full list
    if proveedores_ocultos >= 5:
        return (
            f"\n\n🔍 Hay **{proveedores_ocultos} proveedores más** disponibles. "
            f"En la Plataforma puedes ver todos de un vistazo, filtrar por zona "
            f"y comparar precios: {platform_url}"
        )
    
    # Many brands - highlight filtering
    if marcas_disponibles >= 5:
        return (
            f"\n\n💡 **Tip**: Con tantas marcas disponibles, en la Plataforma puedes "
            f"filtrar rápidamente por marca, precio y presentación: {platform_url}"
        )
    
    # Soft suggestion after a few turns
    if turn_number >= TURN_THRESHOLD_SOFT:
        return (
            f"\n\n💡 También puedes explorar todos los proveedores en nuestra "
            f"Plataforma: {platform_url}"
        )
    
    # No suggestion for early turns
    return ""


def transition_node(state: ConversationState) -> NodeOutput:
    """
    Transition node that adds platform suggestions at appropriate moments.
    
    The node appends a contextual platform suggestion to the response
    based on:
    - Turn number in the conversation
    - Number of hidden providers
    - Number of available brands
    - Whether it's a price query
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state with platform suggestion appended to response
    """
    logger.info("🌐 ════════════════════════════════════════════════════")
    logger.info("🌐 TRANSITION NODE")
    
    turn_number = state.get("turn_number", 0)
    response = state.get("response", "")
    entities = state.get("entities", {})
    search_results = state.get("search_results") or {}
    response_metadata = state.get("response_metadata", {})
    
    # Get context metrics
    proveedores_ocultos = search_results.get("proveedores_ocultos", 0)
    marcas = search_results.get("marcas_disponibles", [])
    marcas_disponibles = len(marcas) if isinstance(marcas, list) else 0
    is_price_query = entities.get("busca_precio", False)
    
    logger.info(f"📊 Turn: {turn_number} | Hidden: {proveedores_ocultos} | "
               f"Brands: {marcas_disponibles} | Price query: {is_price_query}")
    
    # Don't add platform suggestions to conversational responses (greetings, etc.)
    intent = state.get("intent", "")
    if intent == IntentCategory.CONVERSATIONAL.value:
        logger.info(f"ℹ️  Conversational intent, not adding platform suggestion")
        return {}
    
    platform_url = settings.PLATFORM_URL
    
    # ── TURNO 5 (turn=4): Derivación fuerte (appends strong suggestion) ──
    # Note: turn >= CONSULTAS_ANTES_PLANTILLA (5) is handled by PLATFORM_BLOCK
    # in graph.py and never reaches this node.
    if turn_number >= settings.CONSULTAS_ANTES_DERIVACION:
        logger.info(f"🔄 Turn {turn_number} ≥ {settings.CONSULTAS_ANTES_DERIVACION} → DERIVACIÓN")
        derivation_response = (
            f"{response}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 *¡Importante!* Ya llevamos varias consultas y me encanta ayudarte, "
            f"pero en nuestra *Plataforma* vas a encontrar TODO esto mucho más rápido:\n\n"
            f"🔍 Búsqueda avanzada con filtros\n"
            f"📊 Cuadros comparativos de precios\n"
            f"📱 Contacto directo con proveedores\n\n"
            f"👉 {platform_url}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        return {
            "response": derivation_response,
            "should_suggest_platform": True,
            "platform_suggestion": derivation_response,
        }
    
    # ── TURNOS 1-4: Sugerencia suave (solo si no hay URL ya) ──
    if settings.PLATFORM_URL in response:
        logger.info("ℹ️  Platform URL already in response, skipping")
        return {}
    
    # Generate platform suggestion
    platform_message = _generate_platform_message(
        turn_number=turn_number,
        proveedores_ocultos=proveedores_ocultos,
        marcas_disponibles=marcas_disponibles,
        is_price_query=is_price_query,
    )
    
    if platform_message:
        logger.info(f"✅ Adding platform suggestion to response")
        
        updated_response = response + platform_message
        
        logger.info("🌐 ════════════════════════════════════════════════════")
        
        return {
            "response": updated_response,
            "should_suggest_platform": True,
            "platform_suggestion": platform_message,
        }
    
    logger.info("ℹ️  No platform suggestion for this turn")
    logger.info("🌐 ════════════════════════════════════════════════════")
    
    return {
        "should_suggest_platform": False,
    }
