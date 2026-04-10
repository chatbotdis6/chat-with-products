"""
Router Node - Single LLM call for intent, entities, and difficult user detection.

This node consolidates what was previously 3+ separate LLM calls into a single
structured output call, improving latency and reducing costs.
"""
import logging
import json
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from chat.graph.state import (
    ConversationState, 
    NodeOutput, 
    IntentCategory,
    DbAction,
    SpecialistType,
    DifficultUserType
)
from chat.config.settings import settings

logger = logging.getLogger(__name__)

# System prompt for unified router — 3 macro-categories
ROUTER_SYSTEM_PROMPT = """Eres un clasificador experto para The Hap & D Company, una plataforma de proveedores gastronómicos en el Valle de México.

Tu tarea es analizar el mensaje del usuario (CON el contexto de la conversación previa) y clasificarlo en UNA de 3 categorías:

### CATEGORÍAS (intent):

1. `needs_db_action` — El usuario quiere buscar, filtrar, comparar, ver más o pedir detalle de productos/proveedores. **Requiere acceso a la base de datos.**
   - Incluye: búsquedas ("busco aceite"), filtrado por marca ("quiero Capullo"), precios ("cuánto cuesta", "el más barato"), ver más ("muéstrame más"), detalle de proveedor ("info de La Ranita")
   - **IMPORTANTE**: Si el usuario responde a una pregunta anterior sobre productos/marcas/precios (ej: "sí", "ese", "la primera", "no importa la marca"), y la conversación previa era sobre búsqueda de productos, TAMBIÉN es `needs_db_action`

2. `specialist` — El usuario pregunta sobre recetas, cocina, nutrición, cócteles, café, o conservación/inocuidad de alimentos. No necesita la base de datos, necesita un experto temático.
   - Incluye: recetas, técnicas de cocina, información nutricional, cócteles, métodos de café, conservación, vida útil

3. `conversational` — **TODO lo demás.** Saludos, despedidas, agradecimientos, preguntas sobre el servicio ("qué productos manejan?"), confirmaciones sin contexto de búsqueda ("sí por favor", "ok"), quejas, mensajes ambiguos, cualquier cosa que NO requiera buscar en la DB ni un especialista.
   - Incluye: "hola", "gracias", "adiós", "qué hacen ustedes?", "cómo funciona?", "qué tipo de proveedores tienen?", "sí por favor" (si NO hay búsqueda previa activa), mensajes fuera de tema, etc.

### Si intent == `needs_db_action`, especifica db_action:
- `search`: Buscar producto/proveedor nuevo
- `filter_brand`: Filtrar por marca específica (incluye cuando el usuario responde con una marca)
- `filter_price`: Preguntar/filtrar/ordenar por precio ("el más barato", "cuánto cuesta")
- `show_more`: Ver más resultados ("muéstrame más", "hay más?")
- `detail`: Detalle de un proveedor ("info de X", "contacto de X")

### Si intent == `specialist`, especifica specialist_type:
- `chef`, `nutriologo`, `bartender`, `barista`, `ingeniero_alimentos`

### EXTRACCIÓN DE ENTIDADES (entities):
- `producto`: Nombre del producto buscado (solo si se menciona explícitamente o está en contexto activo)
- `marca`: Marca específica si se menciona
- `precio_max` / `precio_min`: Precios mencionados
- `proveedor_nombre`: Nombre del proveedor si se menciona
- `busca_precio`: **TRUE** si el usuario menciona precios/baratos/económicos/caros

### DETECCIÓN DE USUARIO DIFÍCIL:
- `is_difficult`: true si el mensaje contiene insultos, agresión, o insiste en temas inapropiados DESPUÉS de ser redirigido
- `difficult_type`: `none`, `queja_servicio`, `descalificacion`, `insulto_agresion`, `insistencia_fuera`

### REGLA CRÍTICA — USA EL CONTEXTO:
Cuando el usuario responde con mensajes cortos ("sí", "no", "ok", "ese", "la primera", "sí por favor"), DEBES revisar la CONVERSACIÓN PREVIA para decidir:
- Si el bot acaba de preguntar por marca/producto/proveedor → `needs_db_action`
- Si el bot acaba de pedir confirmación de algo no-DB (aviso, despedida) → `conversational`
- Si no hay contexto claro → `conversational`

Responde SIEMPRE en JSON válido:
{
    "intent": "needs_db_action | specialist | conversational",
    "db_action": "search | filter_brand | filter_price | show_more | detail | null",
    "specialist_type": "chef | nutriologo | bartender | barista | ingeniero_alimentos | null",
    "entities": {
        "producto": "string o null",
        "marca": "string o null",
        "precio_max": "number o null",
        "precio_min": "number o null",
        "proveedor_nombre": "string o null",
        "busca_precio": false
    },
    "is_difficult": false,
    "difficult_type": "none",
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
            "intent": IntentCategory.CONVERSATIONAL.value,
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
            "intent": IntentCategory.CONVERSATIONAL.value,
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
        result = json.loads(response.content)
        
        # Validate and extract fields
        intent = result.get("intent", "conversational")
        db_action = result.get("db_action")
        specialist_type = result.get("specialist_type")
        entities = result.get("entities", {})
        is_difficult = result.get("is_difficult", False)
        difficult_type = result.get("difficult_type", "none")
        confidence = result.get("confidence", 0.8)
        
        # Normalize null-like strings from LLM JSON output
        # The LLM may return "null", "none", "" for absent values
        _null_like = (None, "null", "none", "None", "")
        if db_action in _null_like:
            db_action = None
        if specialist_type in _null_like:
            specialist_type = None
        # Clean entities: remove keys with null-like values
        entities = {k: v for k, v in entities.items() if v not in _null_like}
        
        # Normalize intent to one of 3 valid values
        valid_intents = [e.value for e in IntentCategory]
        if intent not in valid_intents:
            logger.warning(f"⚠️  Invalid intent '{intent}', defaulting to conversational")
            intent = IntentCategory.CONVERSATIONAL.value
        
        # Normalize db_action
        valid_db_actions = [e.value for e in DbAction]
        if db_action and db_action not in valid_db_actions:
            logger.warning(f"⚠️  Invalid db_action '{db_action}', defaulting to search")
            db_action = DbAction.SEARCH.value
        
        # Normalize specialist_type
        valid_specialist_types = [e.value for e in SpecialistType]
        if specialist_type and specialist_type not in valid_specialist_types:
            logger.warning(f"⚠️  Invalid specialist_type '{specialist_type}', defaulting to chef")
            specialist_type = SpecialistType.CHEF.value
        
        # Derive requires_search from intent
        requires_search = (intent == IntentCategory.NEEDS_DB_ACTION.value)
        
        # Get previous search filters to inherit context
        prev_filters = state.get("search_filters", {})
        logger.info(f"📋 prev_filters from state: {prev_filters}")
        
        # Build search filters from entities, inheriting from previous if needed
        search_filters = {}
        
        # If user asks about price/filtering without specifying product, inherit from previous
        if intent == IntentCategory.NEEDS_DB_ACTION.value and db_action in ["filter_price", "show_more", "filter_brand"] and not entities.get("producto"):
            logger.info(f"📋 Attempting product inheritance: db_action={db_action}, prev_producto={prev_filters.get('producto')}")
            if prev_filters.get("producto"):
                search_filters["producto"] = prev_filters["producto"]
                entities["producto"] = prev_filters["producto"]
                logger.info(f"📦 Inherited product from previous search: {prev_filters['producto']}")
            else:
                # Fallback: try last_search_query
                last_query = state.get("last_search_query", "")
                if last_query:
                    search_filters["producto"] = last_query
                    entities["producto"] = last_query
                    logger.info(f"📦 Inherited product from last_search_query: {last_query}")
                else:
                    logger.warning(f"⚠️ No previous product to inherit for {db_action}")
        
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
        
        # Set specialist role if applicable
        specialist_role = specialist_type if intent == IntentCategory.SPECIALIST.value else None
        
        logger.info(f"🎯 Intent: {intent} (confidence: {confidence:.2f})")
        if db_action:
            logger.info(f"🗄️  DB Action: {db_action}")
        if specialist_type and intent == IntentCategory.SPECIALIST.value:
            logger.info(f"👨‍🍳 Specialist: {specialist_type}")
        logger.info(f"📦 Entities: {entities}")
        logger.info(f"🔎 Requires search: {requires_search}")
        if is_difficult:
            logger.warning(f"⚠️  Difficult user detected: {difficult_type}")
        logger.info("🔍 ════════════════════════════════════════════════════")
        
        # Only update search_filters if we have new filter data.
        # If search_filters is empty (e.g. conversational turn), preserve the
        # previous filters so query_node can inherit them on the NEXT DB turn.
        output: Dict[str, Any] = {
            "intent": intent,
            "db_action": db_action,
            "specialist_type": specialist_type,
            "entities": entities,
            "is_difficult_user": is_difficult,
            "difficult_type": difficult_type,
            "requires_search": requires_search,
            "router_confidence": confidence,
            "specialist_role": specialist_role,
        }
        
        if search_filters:
            # We extracted new filters — update the state
            output["search_filters"] = search_filters
            logger.info(f"📦 Writing new search_filters to state: {search_filters}")
        else:
            # No new filters (conversational or ambiguous turn) — preserve previous
            logger.info(f"📦 Preserving previous search_filters (not overwriting with empty)")
        
        # Only overwrite last_search_query if we actually have a new product
        new_producto = entities.get("producto", "")
        if new_producto:
            output["last_search_query"] = new_producto
            logger.info(f"📦 Writing last_search_query: {new_producto}")
        else:
            logger.info(f"📦 Preserving previous last_search_query (no new product in entities)")
        
        return output
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse router response as JSON: {e}")
        # Fallback: try to extract basic info
        return {
            "intent": IntentCategory.NEEDS_DB_ACTION.value,
            "db_action": DbAction.SEARCH.value,
            "specialist_type": None,
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
            "intent": IntentCategory.CONVERSATIONAL.value,
            "db_action": None,
            "specialist_type": None,
            "entities": {},
            "is_difficult_user": False,
            "difficult_type": DifficultUserType.NONE.value,
            "requires_search": False,
            "router_confidence": 0.0,
            "error": str(e),
            "error_node": "router"
        }
