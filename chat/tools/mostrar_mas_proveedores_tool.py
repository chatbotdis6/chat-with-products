"""Tool para mostrar proveedores adicionales - Single Responsibility."""
import json
import logging
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from chat.services.platform_transition_service import PlatformTransitionService, TransitionContext
from chat.tools.state import proveedores_state

logger = logging.getLogger(__name__)


class MostrarMasArgs(BaseModel):
    """Argumentos para mostrar más proveedores."""
    product: str = Field(
        ...,
        description="Nombre del producto sobre el que se hizo la búsqueda anterior.",
    )


def _tool_mostrar_mas_proveedores(product: str) -> str:
    """
    Muestra los proveedores que quedaron ocultos en la búsqueda anterior.
    
    Args:
        product: Nombre del producto de la búsqueda anterior
        
    Returns:
        String con proveedores adicionales formateados
    """
    logger.info(f"🔧 TOOL LLAMADA: mostrar_mas_proveedores(product='{product}')")
    
    key = product.lower()
    logger.debug(f"🔍 Buscando proveedores pendientes con key: '{key}'")
    
    if not proveedores_state.has_pendientes(key):
        logger.warning(f"⚠️  No hay proveedores pendientes para '{product}'")
        logger.debug(f"❌ Key '{key}' no encontrada o lista vacía")
        
        return (
            f"No hay más proveedores para mostrar de '{product}'. "
            "Puede que ya hayas visto todos los resultados disponibles."
        )
    
    rows_ocultos = proveedores_state.get_pendientes(key)
    logger.info(f"📤 Mostrando {len(rows_ocultos)} proveedores adicionales de '{product}'")
    
    transition_service = PlatformTransitionService()
    
    # Render de los proveedores ocultos
    lines = [f"**Proveedores adicionales para '{product}'**:"]
    meta = []
    
    for idx, r in enumerate(rows_ocultos):
        logger.debug(f"📦 Proveedor adicional {idx+1}: {r['proveedor']} (ID: {r['proveedor_id']}, Rank: {r['rank']})")
        
        ejemplos = f" — ej.: {r['ejemplos']}" if r.get("ejemplos") and r["ejemplos"] != "—" else ""
        lines.append(f"{r['rank']}. **{r['proveedor']}**{ejemplos}")
        
        meta.append({
            "rank": r["rank"],
            "proveedor_id": r["proveedor_id"],
            "proveedor": r["proveedor"],
            "descripcion_proveedor": r.get("descripcion_proveedor"),
            "contacto_detallado": r.get("contacto_detallado", {}),
        })
    
    lines.append("\n¿Quieres más información de alguno? 😉")
    
    # Sugerir plataforma después de "mostrar más" (usuario está explorando a fondo)
    platform_suggestion = transition_service.generate_transition_message(
        TransitionContext.AFTER_SHOW_MORE,
        {"proveedores_mostrados": len(rows_ocultos)}
    )
    lines.append(platform_suggestion)
    
    # Bloque JSON de metadatos
    meta_block = json.dumps(meta, ensure_ascii=False)
    lines.append("\n```json meta_proveedores\n" + meta_block + "\n```")
    
    # Limpiar los proveedores pendientes
    proveedores_state.clear_pendientes(key)
    logger.info(f"🧹 Limpiados proveedores pendientes de '{product}'")
    logger.debug(f"✅ Key '{key}' ahora tiene lista vacía")
    
    resultado = "\n".join(lines)
    logger.debug(f"📤 Respuesta generada: {len(resultado)} caracteres")
    
    return resultado


# Crear la tool
mostrar_mas_proveedores_tool = StructuredTool.from_function(
    func=_tool_mostrar_mas_proveedores,
    name="mostrar_mas_proveedores",
    description=(
        "Muestra SOLO los nombres y ejemplos de productos de los proveedores adicionales "
        "que no se mostraron en la búsqueda inicial. Requiere 'product' (el mismo producto "
        "de la búsqueda anterior). Úsala cuando el usuario pida ver más opciones, más proveedores, "
        "otros resultados, etc. IMPORTANTE: Esta tool NO incluye información de contacto, solo nombres."
    ),
    args_schema=MostrarMasArgs,
)
