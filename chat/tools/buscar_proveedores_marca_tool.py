"""Tool para buscar proveedores filtrando por marca - Single Responsibility."""
import json
import logging
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from chat.services.search_service import SearchService
from chat.services.platform_transition_service import PlatformTransitionService, TransitionContext
from chat.config.settings import settings
from chat.tools.state import proveedores_state

logger = logging.getLogger(__name__)


class ProductMarcaArgs(BaseModel):
    """Argumentos para la búsqueda por producto y marca."""
    product: str = Field(
        ...,
        description="Nombre del producto a buscar (ej. 'mantequilla', 'aceite').",
    )
    marca: str = Field(
        ...,
        description="Marca específica a filtrar (ej. 'Anchor', 'Lyncott', 'Président').",
    )


def _tool_buscar_proveedores_marca(product: str, marca: str) -> str:
    """
    Busca proveedores filtrando por marca específica.
    
    Args:
        product: Nombre del producto
        marca: Marca a filtrar
        
    Returns:
        JSON con proveedores filtrados por marca
    """
    logger.info(f"🔧 TOOL LLAMADA: buscar_proveedores_marca(product='{product}', marca='{marca}')")
    logger.debug(f"🔍 Iniciando búsqueda con filtro de marca: '{marca}' para producto: '{product}'")
    
    search_service = SearchService()
    transition_service = PlatformTransitionService()
    
    rows, nivel_relevancia, _ = search_service.buscar_proveedores_con_relevancia(
        product=product,
        marca_filtro=marca
    )
    
    logger.info(f"📊 Nivel de relevancia detectado: '{nivel_relevancia}' | Marca: '{marca}'")
    logger.info(f"📈 Total de proveedores encontrados: {len(rows)}")
    
    # Si no hay resultados
    if nivel_relevancia == "nula" or not rows:
        logger.warning(f"❌ No se encontraron productos de marca '{marca}' para '{product}'")
        resultado = {
            "nivel_relevancia": "nula",
            "mensaje": f"No encontré '{product}' de la marca '{marca}'. ¿Quieres ver otras marcas disponibles?",
            "proveedores": [],
            "contexto_precios": []
        }
        logger.debug(f"📤 JSON resultado: {json.dumps(resultado, ensure_ascii=False)}")
        return json.dumps(resultado, ensure_ascii=False)
    
    # Dividir en mostrados y ocultos
    max_inicial = settings.MAX_PROVEEDORES_MOSTRADOS
    rows_mostrados = rows[:max_inicial]
    rows_ocultos = rows[max_inicial:]
    
    key_pendiente = f"{product}_{marca}"
    logger.debug(f"✂️  Dividiendo resultados: {len(rows_mostrados)} mostrados, {len(rows_ocultos)} ocultos")
    logger.debug(f"🗃️  Key para pendientes: '{key_pendiente.lower()}'")
    
    proveedores_state.set_pendientes(key_pendiente, rows_ocultos)
    
    if rows_ocultos:
        logger.info(f"💾 Guardados {len(rows_ocultos)} proveedores para 'mostrar_mas'")
    
    # Construir metadata (sin precios - los precios van por buscar_proveedores_precio)
    meta = []
    for idx, r in enumerate(rows_mostrados):
        logger.debug(f"📦 Proveedor {idx+1}: {r['proveedor']} (ID: {r['proveedor_id']}, Rank: {r['rank']})") 
        
        meta.append({
            "rank": r["rank"],
            "proveedor_id": r["proveedor_id"],
            "proveedor": r["proveedor"],
            "descripcion_proveedor": r.get("descripcion_proveedor"),
            "ejemplos": r["ejemplos"],
        })
    
    mensaje = (
        f"El producto '{product}' marca '{marca}' no está exactamente, pero encontré similares."
        if nivel_relevancia == "media"
        else f"Encontré {len(rows)} proveedores de '{product}' marca '{marca}'."
    )
    
    # Detectar si debemos sugerir la plataforma
    platform_suggestion = ""
    metadata_transition = {
        "proveedores_ocultos": len(rows_ocultos),
        "marca_especifica": marca
    }
    
    if transition_service.should_suggest_transition(
        TransitionContext.AFTER_PROVIDER_LIST,
        metadata_transition
    ):
        platform_suggestion = transition_service.generate_transition_message(
            TransitionContext.AFTER_PROVIDER_LIST,
            metadata_transition
        )
    
    resultado = {
        "nivel_relevancia": nivel_relevancia,
        "mensaje": mensaje,
        "proveedores_mostrados": len(rows_mostrados),
        "proveedores_ocultos": len(rows_ocultos),
        "proveedores": meta,
        "marca_solicitada": marca,
        "platform_suggestion": platform_suggestion
    }
    
    logger.info(f"✅ Retornando {len(meta)} proveedores de marca específica al LLM")
    logger.debug(f"📤 JSON resultado: {json.dumps(resultado, ensure_ascii=False)[:200]}...")
    
    return json.dumps(resultado, ensure_ascii=False)


# Crear la tool
buscar_proveedores_marca_tool = StructuredTool.from_function(
    func=_tool_buscar_proveedores_marca,
    name="buscar_proveedores_marca",
    description=(
        "Busca proveedores de un producto FILTRANDO por marca específica. "
        "Requiere 'product' y 'marca'. Úsala cuando el usuario especifique una marca concreta "
        "(ej: 'Anchor', 'Lyncott', 'Président'). Para precios usa buscar_proveedores_precio."
    ),
    args_schema=ProductMarcaArgs,
)
