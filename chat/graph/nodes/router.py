"""
Router Node - Single LLM call for intent, entities, and difficult user detection.

This node consolidates what was previously 3+ separate LLM calls into a single
structured output call, improving latency and reducing costs.
"""
import logging
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from chat.graph.state import (
    ConversationState, 
    NodeOutput, 
    IntentCategory, 
    DifficultUserType
)
from chat.config.settings import settings

logger = logging.getLogger(__name__)

# System prompt for unified router
ROUTER_SYSTEM_PROMPT = """Eres un clasificador experto para The Hap & D Company, una plataforma de proveedores gastronómicos en México.

Tu tarea es analizar el mensaje del usuario y extraer:
1. **intent**: La intención principal del usuario
2. **entities**: Información relevante extraída (producto, marca, precio, etc.)
3. **is_difficult**: Si el mensaje es problemático (insultos, fuera de tema, etc.)
4. **requires_search**: Si necesita buscar en la base de datos de proveedores

### INTENCIONES VÁLIDAS (intent):
- `busqueda_proveedores`: Busca productos, proveedores, o responde a preguntas sobre ellos
- `mostrar_mas`: Pide ver más proveedores/opciones
- `detalle_proveedor`: Pide información detallada de un proveedor específico
- `filtrar_marca`: Especifica una marca para filtrar resultados
- `filtrar_precio`: Pregunta por precios, quiere ordenar por precio, o pide "los más baratos/caros"
  - Ejemplos: "dame los más baratos", "ordena por precio", "cuánto cuestan", "precios", "el más económico"
- `chef`: Pide recetas, técnicas de cocina, preparación de platillos
- `nutriologo`: Pregunta sobre calorías, nutrición, información nutricional
- `bartender`: Busca cócteles, recetas de bebidas, maridajes
- `barista`: Técnicas de café, métodos de extracción
- `ingeniero_alimentos`: Conservación, almacenamiento, inocuidad, vida útil
- `saludo`: Saludo inicial (hola, buenos días, etc.)
- `despedida`: Despedida (adiós, gracias, hasta luego)
- `agradecimiento`: Agradecimiento por el servicio
- `fuera_alcance`: Completamente fuera del sector gastronómico

### EXTRACCIÓN DE ENTIDADES (entities):
Extrae lo que aplique según el contexto:
- `producto`: Nombre del producto buscado (aceite, harina, mantequilla, etc.)
- `marca`: Marca específica si se menciona (Capullo, Tres Estrellas, etc.)
- `precio_max`: Precio máximo mencionado
- `precio_min`: Precio mínimo mencionado
- `proveedor_nombre`: Nombre del proveedor si se menciona
- `cantidad`: Cantidad mencionada
- `unidad`: Unidad de medida (kg, litros, etc.)
- `busca_precio`: **TRUE** si el usuario menciona precios, baratos, económicos, caros, ordenar por precio

### DETECCIÓN DE USUARIO DIFÍCIL (is_difficult + difficult_type):
Detecta si el mensaje es problemático:
- `none`: Mensaje normal y apropiado
- `queja_servicio`: Se queja del servicio sin agredir
- `descalificacion`: Descalifica proveedores sin fundamento
- `insulto_agresion`: Contiene insultos o groserías
- `insistencia_fuera`: Insiste en temas fuera del sector (después de ser redirigido)

### EJEMPLOS DE CLASIFICACIÓN:
| Mensaje | intent | busca_precio |
|---------|--------|--------------|
| "busco aceite" | busqueda_proveedores | false |
| "dame los más baratos" | filtrar_precio | true |
| "ordénalos por precio" | filtrar_precio | true |
| "cuánto cuesta" | filtrar_precio | true |
| "el más económico" | filtrar_precio | true |
| "quiero ver precios" | filtrar_precio | true |
| "información de La Ranita" | detalle_proveedor | false |
| "mostrar más" | mostrar_mas | false |

### REGLAS IMPORTANTES:
1. Si el usuario responde a una pregunta anterior (ej: eligiendo marca), la intención es `filtrar_marca` o sigue siendo `busqueda_proveedores`
2. "mostrar más", "ver más opciones" → intent: `mostrar_mas`
3. "información de [proveedor]", "contacto de [proveedor]" → intent: `detalle_proveedor`
4. **IMPORTANTE**: Cualquier mención de precio/barato/económico/caro → intent: `filtrar_precio` + busca_precio: true
5. Si detectas insultos/agresión, SIEMPRE marca is_difficult: true
6. requires_search es true para: busqueda_proveedores, filtrar_marca, filtrar_precio, mostrar_mas, detalle_proveedor

### CONTEXTO DE CONVERSACIÓN:
Si recibes contexto de conversación previo, úsalo para:
- Entender referencias implícitas ("ese", "la primera opción", "sí")
- Determinar si el usuario está respondiendo a una pregunta anterior
- Mantener coherencia con el flujo de conversación

Responde SIEMPRE en formato JSON válido con esta estructura exacta:
{
    "intent": "string",
    "entities": {
        "producto": "string o null",
        "marca": "string o null",
        "precio_max": "number o null",
        "precio_min": "number o null",
        "proveedor_nombre": "string o null",
        "busca_precio": "boolean"
    },
    "is_difficult": false,
    "difficult_type": "none",
    "requires_search": false,
    "confidence": 0.95
}"""


def _build_context_messages(state: ConversationState) -> str:
    """Build context from previous messages and search state for better classification."""
    context_parts = []
    
    # Add previous search context if exists
    search_filters = state.get("search_filters", {})
    if search_filters.get("producto"):
        context_parts.append(f"BÚSQUEDA ACTIVA: El usuario estaba buscando '{search_filters['producto']}'")
        if search_filters.get("marca"):
            context_parts.append(f"MARCA SELECCIONADA: {search_filters['marca']}")
    
    # Add conversation history
    messages = state.get("messages", [])
    if messages:
        msg_parts = []
        # Get last 4 messages for context
        for msg in messages[-4:]:
            if hasattr(msg, 'type') and hasattr(msg, 'content') and msg.content:
                role = "Usuario" if msg.type == "human" else "Asistente"
                content = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
                msg_parts.append(f"{role}: {content}")
        
        if msg_parts:
            context_parts.append("CONVERSACIÓN PREVIA:\n" + "\n".join(msg_parts))
    
    if context_parts:
        return "\n\n".join(context_parts) + "\n\n"
    return ""


def router_node(state: ConversationState) -> NodeOutput:
    """
    Router node that performs intent classification, entity extraction,
    and difficult user detection in a single LLM call.
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state fields from router analysis
    """
    logger.info("🔍 ════════════════════════════════════════════════════")
    logger.info("🔍 ROUTER NODE - Analyzing user message")
    
    # Get the last user message
    messages = state.get("messages", [])
    if not messages:
        logger.warning("⚠️  No messages in state")
        return {
            "intent": IntentCategory.UNKNOWN.value,
            "entities": {},
            "is_difficult_user": False,
            "difficult_type": DifficultUserType.NONE.value,
            "requires_search": False,
            "router_confidence": 0.0,
            "error": "No messages to analyze",
            "error_node": "router"
        }
    
    # Find the last human message
    last_user_message = None
    for msg in reversed(messages):
        if hasattr(msg, 'type') and msg.type == "human":
            last_user_message = msg.content
            break
        elif isinstance(msg, HumanMessage):
            last_user_message = msg.content
            break
    
    if not last_user_message:
        logger.warning("⚠️  No user message found")
        return {
            "intent": IntentCategory.UNKNOWN.value,
            "entities": {},
            "is_difficult_user": False,
            "difficult_type": DifficultUserType.NONE.value,
            "requires_search": False,
            "router_confidence": 0.0
        }
    
    logger.info(f"💬 Message: '{last_user_message[:80]}...'")
    
    # Build context from conversation history
    context = _build_context_messages(state)
    
    # Create the prompt
    user_prompt = f"{context}MENSAJE ACTUAL A ANALIZAR:\n{last_user_message}"
    
    try:
        # Use gpt-4o for router (better at structured output and classification)
        llm = ChatOpenAI(
            model=settings.ROUTER_MODEL,
            temperature=0,
            model_kwargs={"response_format": {"type": "json_object"}}
        )
        
        response = llm.invoke([
            ("system", ROUTER_SYSTEM_PROMPT),
            ("user", user_prompt)
        ])
        
        # Parse JSON response
        import json
        result = json.loads(response.content)
        
        # Validate and extract fields
        intent = result.get("intent", "unknown")
        entities = result.get("entities", {})
        is_difficult = result.get("is_difficult", False)
        difficult_type = result.get("difficult_type", "none")
        requires_search = result.get("requires_search", False)
        confidence = result.get("confidence", 0.8)
        
        # Normalize intent
        valid_intents = [e.value for e in IntentCategory]
        if intent not in valid_intents:
            logger.warning(f"⚠️  Invalid intent '{intent}', defaulting to unknown")
            intent = IntentCategory.UNKNOWN.value
        
        # Get previous search filters to inherit context
        prev_filters = state.get("search_filters", {})
        
        # Build search filters from entities, inheriting from previous if needed
        search_filters = {}
        
        # If user asks about price/filtering without specifying product, inherit from previous
        if intent in ["filtrar_precio", "mostrar_mas", "filtrar_marca"] and not entities.get("producto"):
            if prev_filters.get("producto"):
                search_filters["producto"] = prev_filters["producto"]
                entities["producto"] = prev_filters["producto"]
                logger.info(f"📦 Inherited product from previous search: {prev_filters['producto']}")
        
        # Set current entities
        if entities.get("producto"):
            search_filters["producto"] = entities["producto"]
        if entities.get("marca"):
            search_filters["marca"] = entities["marca"]
        if entities.get("precio_max"):
            search_filters["precio_max"] = entities["precio_max"]
        if entities.get("precio_min"):
            search_filters["precio_min"] = entities["precio_min"]
        if entities.get("proveedor_nombre"):
            search_filters["proveedor_nombre"] = entities["proveedor_nombre"]
        
        # Determine specialist role if applicable
        specialist_role = None
        specialist_intents = ["chef", "nutriologo", "bartender", "barista", "ingeniero_alimentos"]
        if intent in specialist_intents:
            specialist_role = intent
        
        logger.info(f"🎯 Intent: {intent} (confidence: {confidence:.2f})")
        logger.info(f"📦 Entities: {entities}")
        logger.info(f"🔎 Requires search: {requires_search}")
        if is_difficult:
            logger.warning(f"⚠️  Difficult user detected: {difficult_type}")
        logger.info("🔍 ════════════════════════════════════════════════════")
        
        return {
            "intent": intent,
            "entities": entities,
            "is_difficult_user": is_difficult,
            "difficult_type": difficult_type,
            "requires_search": requires_search,
            "router_confidence": confidence,
            "search_filters": search_filters,
            "specialist_role": specialist_role,
            "last_search_query": entities.get("producto", ""),
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse router response as JSON: {e}")
        # Fallback: try to extract basic info
        return {
            "intent": IntentCategory.BUSQUEDA_PROVEEDORES.value,
            "entities": {"producto": last_user_message},
            "is_difficult_user": False,
            "difficult_type": DifficultUserType.NONE.value,
            "requires_search": True,
            "router_confidence": 0.5,
            "error": f"JSON parse error: {str(e)}",
            "error_node": "router"
        }
        
    except Exception as e:
        logger.error(f"❌ Router error: {e}", exc_info=True)
        return {
            "intent": IntentCategory.UNKNOWN.value,
            "entities": {},
            "is_difficult_user": False,
            "difficult_type": DifficultUserType.NONE.value,
            "requires_search": False,
            "router_confidence": 0.0,
            "error": str(e),
            "error_node": "router"
        }
