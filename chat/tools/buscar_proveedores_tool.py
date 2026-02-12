"""Tool para buscar proveedores - Single Responsibility Principle."""
import json
import logging
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from chat.services.search_service import SearchService
from chat.services.platform_transition_service import PlatformTransitionService, TransitionContext
from chat.services.unregistered_product_service import unregistered_product_service
from chat.config.settings import settings
from chat.tools.state import proveedores_state

logger = logging.getLogger(__name__)


class ProductArgs(BaseModel):
    """Argumentos para la búsqueda de productos."""
    product: str = Field(
        ...,
        description="Nombre del producto a buscar (ej. 'aceite de oliva', 'queso manchego').",
    )


def _tool_buscar_proveedores(product: str) -> str:
    """
    Llama a la búsqueda con umbrales escalonados y devuelve un JSON estructurado.
    
    Args:
        product: Nombre del producto a buscar
        
    Returns:
        JSON con proveedores, nivel de relevancia y marcas disponibles
    """
    logger.info(f"🔧 TOOL LLAMADA: buscar_proveedores(product='{product}')")
    logger.debug(f"🔍 Iniciando búsqueda de proveedores para producto: '{product}'")
    
    search_service = SearchService()
    transition_service = PlatformTransitionService()
    
    rows, nivel_relevancia, marcas_disponibles = search_service.buscar_proveedores_con_relevancia(
        product=product
    )
    
    logger.info(f"📊 Nivel de relevancia detectado: '{nivel_relevancia}'")
    logger.info(f"📈 Total de proveedores encontrados: {len(rows)}")
    
    if marcas_disponibles:
        logger.info(
            f"🏷️  Marcas disponibles: {marcas_disponibles[:5]}" +
            (f" (y {len(marcas_disponibles)-5} más)" if len(marcas_disponibles) > 5 else "")
        )
        logger.debug(f"🔖 Total de marcas únicas: {len(marcas_disponibles)}")
    
    # CASO 3: Producto no encontrado - clasificar si es gastronómico o no
    if nivel_relevancia == "nula":
        logger.warning(f"❌ Producto '{product}' no encontrado en base de datos")
        logger.info(f"🔍 Iniciando clasificación de producto no registrado...")
        
        # Usar el servicio de productos no registrados
        respuesta_nr = unregistered_product_service.manejar_producto_no_encontrado(
            producto=product,
            history=None,  # El historial se puede pasar desde el chatbot si es necesario
            telefono_usuario=None,  # Se obtiene del contexto de WhatsApp
            session_id=None
        )
        
        resultado = {
            "nivel_relevancia": "nula",
            "tipo_producto_no_encontrado": respuesta_nr["tipo"],
            "mensaje": respuesta_nr["mensaje_usuario"],
            "accion_requerida": respuesta_nr.get("accion_requerida"),
            "proveedores": [],
            "marcas_disponibles": [],
            "razon_clasificacion": respuesta_nr.get("razon_clasificacion", "")
        }
        
        logger.info(f"📤 Tipo: {respuesta_nr['tipo']}")
        logger.debug(f"📤 JSON resultado: {json.dumps(resultado, ensure_ascii=False)}")
        return json.dumps(resultado, ensure_ascii=False)
    
    # CASO 2 y CASO 1: Media y Alta relevancia
    max_inicial = settings.MAX_PROVEEDORES_MOSTRADOS
    rows_mostrados = rows[:max_inicial]
    rows_ocultos = rows[max_inicial:]
    
    logger.debug(f"✂️  Dividiendo resultados: {len(rows_mostrados)} mostrados, {len(rows_ocultos)} ocultos")
    
    # Guardar ocultos para "mostrar más"
    proveedores_state.set_pendientes(product, rows_ocultos)
    
    if rows_ocultos:
        logger.info(f"💾 Guardados {len(rows_ocultos)} proveedores para 'mostrar_mas'")
        logger.debug(f"🗃️  Key en dict pendientes: '{product.lower()}'")
    
    # Construir metadata (sin precios - los precios van por buscar_proveedores_precio)
    meta = []
    for idx, r in enumerate(rows_mostrados):
        logger.debug(f"📦 Proveedor {idx+1}: {r['proveedor']} (ID: {r['proveedor_id']}, Rank: {r['rank']})") 
        logger.debug(f"   └─ Ejemplos: {r['ejemplos'][:50]}..." if len(r.get('ejemplos', '')) > 50 else f"   └─ Ejemplos: {r.get('ejemplos', 'N/A')}")
        
        meta.append({
            "rank": r["rank"],
            "proveedor_id": r["proveedor_id"],
            "proveedor": r["proveedor"],
            "descripcion_proveedor": r.get("descripcion_proveedor"),
            "ejemplos": r["ejemplos"],
        })
    
    # Determinar si debe preguntar por marca (consulta ambigua)
    debe_preguntar_marca = len(marcas_disponibles) >= 2 and nivel_relevancia == "alta"
    
    if debe_preguntar_marca:
        mensaje = (
            f"IMPORTANTE: Hay {len(marcas_disponibles)} marcas diferentes disponibles para '{product}'. "
            f"DEBES preguntar al usuario por su preferencia de marca ANTES de mostrar proveedores."
        )
    elif nivel_relevancia == "media":
        mensaje = f"El producto '{product}' no está en nuestro registro, pero encontré {len(rows)} productos similares."
    else:
        mensaje = f"Encontré {len(rows)} proveedores para '{product}'."
    
    # Detectar si debemos sugerir la plataforma
    platform_suggestion = ""
    metadata_transition = {
        "proveedores_ocultos": len(rows_ocultos),
        "marcas_disponibles": len(marcas_disponibles)
    }
    
    # Sugerir plataforma después de mostrar proveedores
    if transition_service.should_suggest_transition(
        TransitionContext.AFTER_PROVIDER_LIST,
        metadata_transition
    ):
        platform_suggestion = transition_service.generate_transition_message(
            TransitionContext.AFTER_PROVIDER_LIST,
            metadata_transition
        )
    # O si hay muchas marcas disponibles
    elif transition_service.should_suggest_transition(
        TransitionContext.MULTIPLE_BRANDS_AVAILABLE,
        metadata_transition
    ):
        platform_suggestion = transition_service.generate_transition_message(
            TransitionContext.MULTIPLE_BRANDS_AVAILABLE,
            metadata_transition
        )
    
    resultado = {
        "nivel_relevancia": nivel_relevancia,
        "mensaje": mensaje,
        "debe_preguntar_marca": debe_preguntar_marca,  # Nueva señal explícita
        "proveedores_mostrados": len(rows_mostrados),
        "proveedores_ocultos": len(rows_ocultos),
        "proveedores": meta,
        "marcas_disponibles": marcas_disponibles,
        "platform_suggestion": platform_suggestion
    }
    
    logger.info(f"✅ Retornando {len(meta)} proveedores al LLM (debe_preguntar_marca={debe_preguntar_marca})")
    logger.debug(f"📤 JSON resultado: {json.dumps(resultado, ensure_ascii=False)[:200]}...")
    
    return json.dumps(resultado, ensure_ascii=False)


# Crear la tool
buscar_proveedores_tool = StructuredTool.from_function(
    func=_tool_buscar_proveedores,
    name="buscar_proveedores",
    description=(
        "Busca y lista los 2-3 proveedores TOP que venden un producto específico. "
        "Requiere el parámetro 'product'. Devuelve una lista breve con nombre y ejemplos. "
        "Si hay más proveedores, indica que el usuario puede solicitar verlos."
    ),
    args_schema=ProductArgs,
)
