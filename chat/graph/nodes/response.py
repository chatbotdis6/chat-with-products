"""
Response Node - Generates user-facing responses based on search results
or conversational context.

For DB-action results: formats search results, prices, provider details.
For conversational messages: uses an LLM with full conversation history
to generate contextual responses (saludos, confirmaciones, preguntas
sobre el servicio, follow-ups, etc.)
"""
import logging
import re
from typing import Dict, Any, List

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage

from chat.graph.state import (
    ConversationState, 
    NodeOutput, 
    RelevanciaLevel,
    IntentCategory,
)
from chat.config.settings import settings
from chat.prompts.system_prompts import SystemPrompts

logger = logging.getLogger(__name__)


# Fallback response when search returns no results
NO_RESULTS_RESPONSE = (
    "No encontré resultados para tu búsqueda 😕\n\n"
    "¿Podrías intentar con otro término o ser más específico?"
)


def _format_provider_list(proveedores: List[Dict], include_prices: bool = False) -> str:
    """Format a list of providers for display."""
    if not proveedores:
        return ""
    
    lines = []
    for p in proveedores:
        proveedor_name = p.get("proveedor", "Proveedor")
        descripcion = p.get("descripcion", "")
        ejemplos = p.get("ejemplos", "")
        
        # Basic format: number + provider name
        line = f"{p.get('rank', '')}. **{proveedor_name}**"
        
        # Add description and product examples on separate lines
        if descripcion and descripcion != "—":
            line += f"\n   - {descripcion}"
        if ejemplos and ejemplos != "—":
            line += f"\n   - Productos encontrados: {ejemplos}"
        
        # Add prices if requested
        if include_prices:
            contexto_precios = p.get("contexto_precios", [])
            if contexto_precios:
                precio_info = contexto_precios[0]
                precio_str = precio_info.get("precio_formateado", "")
                if precio_str:
                    line += f" | {precio_str}"
        
        lines.append(line)
    
    return "\n\n".join(lines)


def _format_price_list(precios: List[Dict], producto: str) -> str:
    """Format a price comparison list."""
    if not precios:
        return "No encontré precios para ese producto."
    
    lines = [f"Precios actuales de **{producto}**:\n"]
    
    for p in precios:
        proveedor = p.get("proveedor", "Proveedor")
        precio = p.get("precio_formateado", "N/A")
        nombre_prod = p.get("producto", "")
        presentacion = p.get("presentacion", "")
        marca = p.get("marca", "")
        # Build detail: "Producto Marca (Presentación)"
        detalle_parts = []
        if nombre_prod:
            detalle_parts.append(nombre_prod)
        if marca:
            detalle_parts.append(marca)
        detalle = " ".join(detalle_parts)
        if presentacion:
            detalle += f" ({presentacion})"
        if detalle:
            lines.append(f"• {detalle} – {precio}\n  _{proveedor}_")
        else:
            lines.append(f"• {proveedor} – {precio}")
    
    return "\n".join(lines)


def _format_provider_detail(detail: Dict[str, Any]) -> str:
    """Format detailed provider information for display."""
    nombre = detail.get("nombre", "Proveedor")
    descripcion = detail.get("descripcion", "Sin descripción")
    ejecutivo = detail.get("ejecutivo_ventas", "No especificado")
    whatsapp_list = detail.get("whatsapp_ventas", [])
    whatsapp_links = detail.get("whatsapp_links", [])
    pagina_web = detail.get("pagina_web", "No disponible")
    calificacion = detail.get("calificacion", 0)
    
    lines = [f"📋 **{nombre}**\n"]
    
    # Description
    if descripcion and descripcion != "Sin descripción disponible":
        lines.append(f"📝 *Descripción:* {descripcion}\n")
    
    # Contact info
    lines.append("📞 **Información de contacto:**")
    
    if ejecutivo and ejecutivo != "No especificado":
        lines.append(f"• Ejecutivo de ventas: {ejecutivo}")
    
    if whatsapp_list:
        # Format number for display: 52 55 1257 6593 -> +52 55 1257 6593
        def _format_display(num: str) -> str:
            if len(num) >= 12 and num.startswith("52"):
                return f"+{num[:2]} {num[2:4]} {num[4:8]} {num[8:]}"
            return num
        whatsapp_text = ", ".join(_format_display(n) for n in whatsapp_list)
        lines.append(f"• WhatsApp: {whatsapp_text}")
        if whatsapp_links:
            lines.append(f"• 💬 Contactar: {whatsapp_links[0]}")
    else:
        lines.append("• WhatsApp: No disponible")
    
    if pagina_web and pagina_web != "No disponible":
        lines.append(f"• 🌐 Web: {pagina_web}")
    
    # Rating
    if calificacion > 0:
        stars = "⭐" * int(calificacion)
        lines.append(f"\n⭐ Calificación: {stars} ({calificacion}/5)")
    
    lines.append("\n¿Te gustaría ver los productos de este proveedor o contactarlo directamente?")
    
    return "\n".join(lines)


def _should_ask_for_brand(marcas: List[str]) -> bool:
    """Determine if we should ask the user about brand preference."""
    return len(marcas) >= 2


def _generate_conversational_response(state: ConversationState) -> str:
    """
    Generate a conversational response using an LLM with full conversation history.
    
    Handles: saludos, despedidas, confirmaciones, preguntas sobre el servicio,
    follow-ups, y cualquier mensaje que no requiera DB ni especialista.
    
    Uses gpt-4o-mini for cost efficiency (these are short, simple responses).
    """
    messages = state.get("messages", [])
    
    # Build conversation history for the LLM
    system_prompt = SystemPrompts.get_conversational_prompt()
    system_prompt = system_prompt.replace("{buzon}", settings.BUZON_QUEJAS)
    
    llm_messages = [("system", system_prompt)]
    
    # Include last 6 messages for context (3 turns)
    for msg in messages[-6:]:
        if hasattr(msg, 'type') and hasattr(msg, 'content') and msg.content:
            if msg.type == "human":
                llm_messages.append(("user", msg.content))
            else:
                llm_messages.append(("assistant", msg.content))
    
    # If no user messages were added (edge case), add a fallback
    if len(llm_messages) == 1:
        llm_messages.append(("user", "Hola"))
    
    try:
        llm = ChatOpenAI(
            model=settings.ROUTER_MODEL,  # gpt-4o — fast, cheap, good enough
            temperature=0.7,
            max_tokens=300,  # Keep responses short
        )
        
        response = llm.invoke(llm_messages)
        return response.content.strip()
        
    except Exception as e:
        logger.error(f"❌ Conversational LLM error: {e}")
        return (
            "¡Hola! 👋 Soy el asistente de The Hap & D Company.\n\n"
            "Te ayudo a encontrar proveedores de insumos gastronómicos "
            "en el Valle de México.\n\n"
            "¿Qué producto estás buscando hoy?"
        )


def response_node(state: ConversationState) -> NodeOutput:
    """
    Response node that generates user-facing responses.
    
    This node handles:
    - Search results formatting
    - Simple intents (saludo, despedida, agradecimiento)
    - Brand questions when multiple brands available
    - Price comparisons
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state with formatted response
    """
    logger.info("💬 ════════════════════════════════════════════════════")
    logger.info("💬 RESPONSE NODE")
    
    intent = state.get("intent", "")
    search_results = state.get("search_results")
    nivel_relevancia = state.get("nivel_relevancia", "")
    entities = state.get("entities", {})
    response_metadata = state.get("response_metadata", {})
    
    logger.info(f"🎯 Intent: {intent}")
    logger.info(f"📊 Relevancia: {nivel_relevancia}")
    
    # ── If a previous node (e.g. query_node for show_more) already set a response, keep it ──
    existing_response = state.get("response", "")
    if existing_response and not search_results and not nivel_relevancia and intent != IntentCategory.CONVERSATIONAL.value:
        logger.info(f"✅ Keeping response from previous node (len={len(existing_response)})")
        return {"response": existing_response}
    
    # ── CONVERSATIONAL PATH: Use LLM with conversation history ──
    if intent == IntentCategory.CONVERSATIONAL.value or (not search_results and not nivel_relevancia):
        logger.info("💬 Conversational path → LLM-powered response")
        response = _generate_conversational_response(state)
        logger.info(f"✅ Conversational response generated")
        return {"response": response}
    
    # Handle price queries
    if entities.get("busca_precio") and response_metadata.get("precios"):
        precios = response_metadata["precios"]
        producto = entities.get("producto", "producto")
        response = _format_price_list(precios, producto)
        logger.info(f"✅ Price response generated with {len(precios)} prices")
        return {"response": response}
    
    # Handle provider detail request
    if response_metadata.get("provider_detail"):
        detail = response_metadata["provider_detail"]
        response = _format_provider_detail(detail)
        logger.info(f"✅ Provider detail response for: {detail.get('nombre')}")
        return {"response": response}
    
    # Handle provider not found
    if response_metadata.get("provider_not_found"):
        nombre = response_metadata["provider_not_found"]
        response = f"No encontré un proveedor con el nombre \"{nombre}\". ¿Podrías verificar el nombre o buscar otro proveedor? 🔍"
        logger.info(f"⚠️  Provider not found: {nombre}")
        return {"response": response}
    
    # Handle no search results
    if not search_results:
        if state.get("error"):
            response = f"Lo siento, hubo un problema con la búsqueda. ¿Podrías intentar de nuevo? 😊"
        else:
            response = NO_RESULTS_RESPONSE
        logger.info(f"⚠️  No search results")
        return {"response": response}
    
    # Extract data from search results
    proveedores = search_results.get("proveedores", [])
    proveedores_ocultos = search_results.get("proveedores_ocultos", 0)
    marcas = search_results.get("marcas_disponibles", [])
    producto = entities.get("producto", "producto")
    
    # Generate response based on relevancia level
    if nivel_relevancia == RelevanciaLevel.NULA.value:
        # This case should be handled by unregistered_product_node
        # but we provide a fallback
        response = (
            f"No encontré '{producto}' en nuestra base de proveedores.\n\n"
            f"¿Podrías verificar el nombre o intentar con otro producto?"
        )
        logger.info(f"⚠️  NULA relevancia - fallback response")
        return {"response": response}
    
    # Build the response
    response_parts = []
    
    # Introduction based on relevancia
    if nivel_relevancia == RelevanciaLevel.ALTA.value:
        # Check if we should ask for brand
        if _should_ask_for_brand(marcas) and not entities.get("marca"):
            marcas_muestra = marcas[:5]
            marcas_str = ", ".join(marcas_muestra)
            if len(marcas) > 5:
                marcas_str += f" y {len(marcas) - 5} más"
            
            response = (
                f"Tenemos varias marcas de {producto} disponibles: **{marcas_str}**.\n\n"
                f"¿Tienes alguna preferencia de marca? 🤔"
            )
            logger.info(f"✅ Asking for brand preference ({len(marcas)} brands)")
            return {
                "response": response,
                "response_metadata": {
                    "debe_preguntar_marca": True,
                    "marcas_disponibles": marcas,
                }
            }
        
        # Show providers directly
        total = len(proveedores) + proveedores_ocultos
        if total == 1:
            response_parts.append(f"Tengo un proveedor de {producto} para ti:\n")
        elif total <= 3:
            response_parts.append(f"Tengo {total} proveedores de {producto}:\n")
        else:
            response_parts.append(f"Tengo **{total} proveedores** de {producto}. Aquí van los primeros:\n")
    
    elif nivel_relevancia == RelevanciaLevel.MEDIA.value:
        response_parts.append(
            f"Ese producto exacto no lo tenemos registrado, "
            f"pero te puedo ofrecer estos proveedores con productos similares:\n"
        )
    
    # Format provider list
    provider_list = _format_provider_list(proveedores)
    if provider_list:
        response_parts.append(provider_list)
    
    # Add "show more" prompt if there are hidden providers
    if proveedores_ocultos > 0:
        response_parts.append(
            f"\n\n📋 Hay **{proveedores_ocultos} proveedores más** disponibles. "
            f"¿Quieres que te los muestre? 😊"
        )
    
    # Add closing question
    response_parts.append(
        "\n\n¿Quieres más información de algún proveedor en particular? 😉"
    )
    
    response = "".join(response_parts)
    
    # Clean up any LLM artifacts like leading "2. Búsqueda" etc.
    import re
    response = re.sub(r'^\d+\.\s*(Búsqueda|Busqueda)\s*\n*', '', response).strip()
    
    logger.info(f"✅ Response generated: {len(proveedores)} shown, {proveedores_ocultos} hidden")
    logger.info("💬 ════════════════════════════════════════════════════")
    
    return {
        "response": response,
        "response_metadata": {
            "proveedores_mostrados": len(proveedores),
            "proveedores_ocultos": proveedores_ocultos,
            "marcas_disponibles": marcas,
        }
    }
