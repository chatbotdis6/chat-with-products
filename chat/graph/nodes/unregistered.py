"""
Unregistered Product Node - Handles products not found in the database.

This node implements Task 6: When a product is not found, classify if it's
gastronomic (promise 12h response + send email) vs non-gastronomic (politely decline).
"""
import logging
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from chat.graph.state import (
    ConversationState, 
    NodeOutput, 
    RelevanciaLevel,
    UnregisteredProductInfo
)
from chat.config.settings import settings
from chat.services.email_service import email_service

logger = logging.getLogger(__name__)


# Gastronomic categories for classification
CATEGORIAS_GASTRONOMICAS = [
    "ingredientes de cocina", "especias", "condimentos", "aceites", "vinagres",
    "carnes", "pescados", "mariscos", "aves", "embutidos",
    "lácteos", "quesos", "mantequillas", "cremas", "yogures",
    "frutas", "verduras", "hortalizas", "legumbres", "granos",
    "harinas", "pastas", "arroces", "cereales", "panadería",
    "chocolates", "cacao", "azúcares", "mieles", "endulzantes",
    "bebidas alcohólicas", "vinos", "licores", "cervezas", "destilados",
    "bebidas", "cafés", "tés", "jugos", "aguas",
    "conservas", "enlatados", "encurtidos", "salsas", "aderezos",
    "equipo de cocina", "utensilios", "cristalería", "vajilla",
]


CLASSIFICATION_PROMPT = """Eres un experto en el sector gastronómico y de hospitalidad.

Tu tarea es clasificar si el siguiente producto pertenece o NO al sector gastronómico/hospitalidad.

PRODUCTO A CLASIFICAR: "{producto}"

CATEGORÍAS QUE SÍ SON GASTRONÓMICAS:
- Ingredientes de cocina (carnes, pescados, lácteos, frutas, verduras, especias)
- Bebidas (vinos, licores, cervezas, cafés, tés, jugos)
- Productos procesados para cocina (conservas, salsas, aderezos)
- Equipo y utensilios de cocina profesional
- Vajilla, cristalería, cubiertos para restaurantes
- Empaques y desechables para alimentos
- Productos gourmet, artesanales o importados para gastronomía

CATEGORÍAS QUE NO SON GASTRONÓMICAS:
- Cosméticos y belleza
- Medicamentos y farmacia
- Electrónica de consumo
- Ropa y moda
- Automotriz
- Construcción
- Juguetes
- Productos para mascotas

Responde SOLO: GASTRONOMICO o NO_GASTRONOMICO"""


def _clasificar_producto(producto: str) -> tuple[bool, str]:
    """Classify if a product is gastronomic or not."""
    try:
        llm = ChatOpenAI(model=settings.ROUTER_MODEL, temperature=0)
        
        response = llm.invoke([
            ("user", CLASSIFICATION_PROMPT.format(producto=producto))
        ])
        
        resultado = response.content.strip().upper()
        logger.info(f"🏷️  Raw classification response: '{resultado}'")
        
        # Check for NO_GASTRONOMICO first (more specific), then GASTRONOMICO
        if "NO_GASTRONOMICO" in resultado or "NO GASTRONOMICO" in resultado:
            return False, "Producto fuera del sector gastronómico"
        elif "GASTRONOMICO" in resultado:
            return True, "Producto del sector gastronómico"
        else:
            # Fallback: assume gastronomic to not lose opportunities
            logger.warning(f"⚠️  Unexpected classification result: '{resultado}', assuming gastronomic")
            return True, "Clasificación ambigua - asumiendo gastronómico"
            
    except Exception as e:
        logger.error(f"❌ Classification error: {e}")
        # On error, assume gastronomic to not lose opportunities
        return True, "Error en clasificación - asumiendo gastronómico"


def _generar_resumen_conversacion(messages: list, producto: str) -> str:
    """Generate a clean conversation summary for the email (no emojis, no markdown).
    
    Only includes the last user message that triggered the unregistered product flow,
    not the full session history.
    """
    # Find the last user message
    last_user_msg = None
    for msg in reversed(messages):
        if hasattr(msg, 'type') and msg.type == 'human':
            last_user_msg = msg.content[:500]
            break
    
    if last_user_msg:
        return f"Cliente: {last_user_msg}"
    else:
        return f"Cliente: (preguntó por {producto})"


def unregistered_product_node(state: ConversationState) -> NodeOutput:
    """
    Unregistered product node that handles products not found in the database.
    
    Flow:
    1. Classify if the product is gastronomic or not
    2. If gastronomic: Promise 12h response, send email to team
    3. If not gastronomic: Politely decline and redirect
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state with appropriate response
    """
    logger.info("📦 ════════════════════════════════════════════════════")
    logger.info("📦 UNREGISTERED PRODUCT NODE")
    
    # Get the product that wasn't found
    producto = state.get("last_search_query", "")
    if not producto:
        entities = state.get("entities", {})
        producto = entities.get("producto", "producto desconocido")
    
    messages = state.get("messages", [])
    user_phone = state.get("user_phone")
    session_id = state.get("session_id", "unknown")
    
    logger.info(f"📦 Product not found: '{producto}'")
    
    # 1. Classify the product
    es_gastronomico, razon = _clasificar_producto(producto)
    
    logger.info(f"🏷️  Classification: {'GASTRONÓMICO' if es_gastronomico else 'NO GASTRONÓMICO'}")
    logger.info(f"📝 Reason: {razon}")
    
    # 2. Generate conversation summary
    resumen = _generar_resumen_conversacion(messages, producto)
    
    # 3. Send email and generate response
    if es_gastronomico:
        logger.info(f"🍽️  Gastronomic product - initiating investigation flow")
        
        # Send email to team
        email_enviado = email_service.enviar_solicitud_producto(
            producto_solicitado=producto,
            telefono_usuario=user_phone,
            resumen_conversacion=resumen,
            es_gastronomico=True,
            session_id=session_id
        )
        
        response = (
            f"Ese producto no lo tenemos en nuestro registro todavía, "
            f"pero dame hasta 12 horas y regreso contigo con una sugerencia.\n\n"
            f"¿Quieres que te avise aquí mismo en WhatsApp cuando lo tenga?"
        )
        
        unregistered_info = UnregisteredProductInfo(
            producto=producto,
            es_gastronomico=True,
            email_enviado=email_enviado,
            mensaje_usuario=response,
        )
        
    else:
        logger.info(f"🚫 Product outside gastronomic sector")
        
        # Also notify for statistics
        email_service.enviar_solicitud_producto(
            producto_solicitado=producto,
            telefono_usuario=user_phone,
            resumen_conversacion=resumen,
            es_gastronomico=False,
            session_id=session_id
        )
        
        response = (
            f"Ese producto no forma parte del sector gastronómico en el que nos especializamos. "
            f"Trabajamos únicamente con insumos para cocinas profesionales y negocios de hospitalidad gastronómica.\n\n"
            f"¿Te gustaría buscar algún producto de cocina o abasto?"
        )
        
        unregistered_info = UnregisteredProductInfo(
            producto=producto,
            es_gastronomico=False,
            email_enviado=True,
            mensaje_usuario=response,
        )
    
    logger.info(f"✅ Response generated for unregistered product")
    logger.info("📦 ════════════════════════════════════════════════════")
    
    return {
        "response": response,
        "unregistered_product": unregistered_info,
        "response_metadata": {
            "product_type": "gastronomico" if es_gastronomico else "no_gastronomico",
            "classification_reason": razon,
        }
    }
