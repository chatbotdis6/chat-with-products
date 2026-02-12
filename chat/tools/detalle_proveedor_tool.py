"""Tool para obtener detalle de proveedor - Single Responsibility."""
import logging
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from chat.services.search_service import SearchService
from chat.services.platform_transition_service import PlatformTransitionService, TransitionContext

logger = logging.getLogger(__name__)


class DetalleArgs(BaseModel):
    """Argumentos para obtener detalle de proveedor."""
    proveedor_id: int = Field(
        ...,
        description="ID del proveedor del que se quiere obtener la información detallada."
    )


def _tool_detalle_proveedor(proveedor_id: int) -> str:
    """
    Devuelve la ficha detallada del proveedor con información de contacto.
    
    Args:
        proveedor_id: ID del proveedor
        
    Returns:
        String formateado con información de contacto
    """
    logger.info(f"🔧 TOOL LLAMADA: detalle_proveedor(proveedor_id={proveedor_id})")
    logger.debug(f"🔍 Consultando detalles del proveedor con ID: {proveedor_id}")
    
    search_service = SearchService()
    transition_service = PlatformTransitionService()
    
    data = search_service.obtener_detalle_proveedor(proveedor_id)
    
    if not data:
        logger.warning(f"⚠️  No se encontró información para proveedor_id={proveedor_id}")
        logger.debug(f"❌ SearchService retornó None/vacío")
        return f"No encontré detalle para proveedor_id={proveedor_id}."
    
    nombre = data.get("proveedor") or "Proveedor"
    logger.info(f"📋 Detalles obtenidos para proveedor: {nombre}")
    logger.debug(f"📊 Datos recibidos: {list(data.keys())}")
    
    ejecutivo = data.get("nombre_ejecutivo_ventas") or "—"
    wa_numbers = data.get("whatsapp_ventas_list") or []
    wa_links = data.get("whatsapp_links") or []
    web = data.get("pagina_web") or "—"
    
    logger.debug(f"👤 Ejecutivo de ventas: {ejecutivo}")
    logger.debug(f"📱 WhatsApp numbers: {len(wa_numbers)} número(s)")
    logger.debug(f"🔗 WhatsApp links: {len(wa_links)} enlace(s)")
    logger.debug(f"🌐 Sitio web: {web}")
    
    # Render de múltiples WhatsApp como enlaces clickeables
    if wa_links:
        wa_lines = []
        for i, link in enumerate(wa_links):
            numero_raw = wa_numbers[i] if i < len(wa_numbers) else f"Número {i+1}"
            
            # Formatear el número
            if numero_raw.startswith("52") and len(numero_raw) >= 12:
                numero_formateado = f"+52 {numero_raw[2:4]} {numero_raw[4:8]} {numero_raw[8:]}"
            elif numero_raw.startswith("521") and len(numero_raw) >= 13:
                numero_formateado = f"+52 1 {numero_raw[3:5]} {numero_raw[5:9]} {numero_raw[9:]}"
            else:
                numero_formateado = numero_raw
            
            # Crear enlace clickeable en formato Markdown
            wa_lines.append(f"[{numero_formateado}]({link})")
            logger.debug(f"   └─ WhatsApp {i+1}: {numero_formateado} -> {link}")
        
        wa_block = ", ".join(wa_lines)
    else:
        wa_block = "—"
        logger.debug("📱 No hay números de WhatsApp disponibles")
    
    lines = [
        f"**Detalles de {nombre}:**",
        f"- **Vendedor:** {ejecutivo}",
        f"- **WhatsApp:** {wa_block}",
        f"- **Sitio web:** {web}",
    ]
    
    # Sugerir plataforma después de ver contacto (usuario en fase de decisión)
    platform_suggestion = transition_service.generate_transition_message(
        TransitionContext.AFTER_CONTACT_DETAILS,
        {"proveedor": nombre}
    )
    lines.append(platform_suggestion)
    
    resultado = "\n".join(lines)
    logger.info(f"✅ Detalles del proveedor generados exitosamente")
    logger.debug(f"📤 Respuesta: {len(resultado)} caracteres")
    
    return resultado


# Crear la tool
detalle_proveedor_tool = StructuredTool.from_function(
    func=_tool_detalle_proveedor,
    name="detalle_proveedor",
    description=(
        "Muestra la información detallada de un proveedor (vendedor, WhatsApp/link y web). "
        "Requiere 'proveedor_id'. Úsala cuando el usuario pida más información de un proveedor concreto."
    ),
    args_schema=DetalleArgs,
)
