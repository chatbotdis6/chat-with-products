"""
Difficult User Node - Handles inappropriate, aggressive, or off-topic messages.

This node provides appropriate responses while maintaining professionalism
and redirecting users to the appropriate channels.
"""
import logging
from typing import Dict, Any

from chat.graph.state import ConversationState, NodeOutput, DifficultUserType
from chat.config.settings import settings

logger = logging.getLogger(__name__)

# Responses for different difficult user types
DIFFICULT_RESPONSES = {
    DifficultUserType.QUEJA_SERVICIO.value: (
        "Entiendo tu comentario y lo tomamos en cuenta 😊\n\n"
        "Si deseas, puedes enviarnos tu feedback detallado a nuestro "
        "buzón de quejas y sugerencias: {buzon}\n\n"
        "Mientras tanto, ¿hay algún producto del sector gastronómico "
        "que pueda ayudarte a encontrar?"
    ),
    
    DifficultUserType.DESCALIFICACION.value: (
        "Gracias por compartir tu opinión 😊\n\n"
        "Trabajamos constantemente para mejorar nuestra base de proveedores. "
        "Tu feedback es valioso y puedes enviarlo a: {buzon}\n\n"
        "¿Hay algún producto específico que estés buscando? "
        "Con gusto te ayudo a encontrar opciones que se ajusten a lo que necesitas."
    ),
    
    DifficultUserType.INSULTO_AGRESION.value: (
        "Entiendo que puedas estar frustrado 😊\n\n"
        "Estoy aquí para ayudarte a encontrar proveedores del sector gastronómico. "
        "Si tienes alguna queja sobre el servicio, puedes escribir a: {buzon}\n\n"
        "¿Hay algo del sector de alimentos y bebidas en lo que pueda asistirte?"
    ),
    
    DifficultUserType.INSISTENCIA_FUERA.value: (
        "Entiendo tu interés, pero debo ser claro: nuestro servicio está "
        "exclusivamente enfocado en el sector gastronómico 🍽️\n\n"
        "Si buscas insumos para cocina profesional o para tu negocio de "
        "hospitalidad gastronómica, aquí puedo ayudarte.\n\n"
        "Para otros comentarios o sugerencias, puedes usar nuestro buzón: {buzon}"
    ),
    
    # Default for other cases (neutral off-topic, sarcasm, illegal)
    "default": (
        "Esa consulta está fuera de mi área de especialización 😊\n\n"
        "Soy experto en ayudarte a encontrar proveedores del sector gastronómico "
        "en el Valle de México.\n\n"
        "¿Necesitas algún ingrediente, producto o insumo para tu cocina o negocio de alimentos?"
    ),
}


def difficult_user_node(state: ConversationState) -> NodeOutput:
    """
    Difficult user node that handles inappropriate or problematic messages.
    
    Types handled:
    - queja_servicio: Complaints about service
    - descalificacion: Unfounded criticism of providers
    - insulto_agresion: Insults or aggressive language
    - insistencia_fuera: Persistent off-topic requests
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state with appropriate response
    """
    logger.info("🚨 ════════════════════════════════════════════════════")
    logger.info("🚨 DIFFICULT USER NODE")
    
    difficult_type = state.get("difficult_type", DifficultUserType.NONE.value)
    buzon = settings.BUZON_QUEJAS
    
    logger.info(f"⚠️  Difficult type: {difficult_type}")
    logger.info(f"📧 Buzón de quejas: {buzon}")
    
    # Get the appropriate response template
    response_template = DIFFICULT_RESPONSES.get(
        difficult_type, 
        DIFFICULT_RESPONSES["default"]
    )
    
    # Format with buzón
    response = response_template.format(buzon=buzon)
    
    logger.info(f"✅ Response generated for difficult user")
    logger.info("🚨 ════════════════════════════════════════════════════")
    
    return {
        "response": response,
        "response_metadata": {
            "difficult_type": difficult_type,
            "buzon_included": True
        }
    }
