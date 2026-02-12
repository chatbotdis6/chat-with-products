# search.py
"""
DEPRECATED: Este archivo se mantiene por compatibilidad hacia atrás.

Nueva arquitectura (refactorizada con principios SOLID):
- chat.services.search_service.SearchService
- chat.services.database_service.DatabaseService
- chat.services.data_transformer.DataTransformer
- chat.services.product_filter_service.ProductFilterService
- chat.services.whatsapp_formatter.WhatsAppFormatter

Para nuevos desarrollos, importar directamente desde chat.services
"""
import warnings
from typing import Tuple, List, Optional

# Nueva arquitectura refactorizada
from chat.services.search_service import SearchService

# Crear instancia global del servicio para compatibilidad
_search_service = SearchService()

# Deprecation warning (comentado para no molestar en producción)
# warnings.warn(
#     "El módulo chat.search está deprecado y se mantiene solo por compatibilidad. "
#     "Usa chat.services.search_service.SearchService para nuevos desarrollos.",
#     DeprecationWarning,
#     stacklevel=2
# )


# =====================================================
# Funciones de compatibilidad (wrappers)
# =====================================================

def buscar_productos_mejorado(
    search_query: str,
    top_k: int = 20,
    knn_limit: int = 200,
    threshold_trgm: float = 0.40,
    threshold_vector: float = 0.75,
    w_trgm: float = 0.6,
    w_vec: float = 0.4,
) -> Tuple[List[dict], List[dict]]:
    """
    DEPRECATED: Usar SearchService.buscar_productos_mejorado()
    
    Búsqueda híbrida de productos (trigram + vector).
    Wrapper de compatibilidad hacia la nueva arquitectura.
    """
    return _search_service.buscar_productos_mejorado(
        search_query=search_query,
        top_k=top_k,
        knn_limit=knn_limit,
        threshold_trgm=threshold_trgm,
        threshold_vector=threshold_vector,
        w_trgm=w_trgm,
        w_vec=w_vec,
    )


def buscar_proveedores_por_producto(
    product: str,
    top_k: int = 25,
    threshold_trgm: float = 0.55,
    threshold_vector: float = 0.75,
) -> List[dict]:
    """
    DEPRECATED: Usar SearchService directamente.
    
    Vista "básica" para el chat.
    Wrapper de compatibilidad hacia la nueva arquitectura.
    """
    productos, proveedores = _search_service.buscar_productos_mejorado(
        search_query=product,
        top_k=top_k,
        threshold_trgm=threshold_trgm,
        threshold_vector=threshold_vector,
    )
    
    # Formatear como en la versión anterior
    salida = []
    for i, p in enumerate(proveedores, 1):
        ejemplos = ", ".join(p["ejemplos"]) if p["ejemplos"] else "—"
        salida.append({
            "rank": i,
            "proveedor_id": p["proveedor_id"],
            "proveedor": p["proveedor"],
            "coincidencias": p["matches"],
            "mejor_score": round(p["best_score"], 3),
            "ejemplos": ejemplos,
            "contacto_detallado": {
                "nombre_ejecutivo_ventas": p["ejecutivo_ventas"],
                "whatsapp_ventas_list": p["whatsapp_ventas_list"],
                "whatsapp_links": p["whatsapp_links"],
                "pagina_web": p["pagina_web"],
            },
        })
    return salida


def buscar_proveedores_con_relevancia(
    product: str,
    top_k: int = 25,
    marca_filtro: Optional[str] = None
) -> Tuple[List[dict], str, List[str]]:
    """
    DEPRECATED: Usar SearchService.buscar_proveedores_con_relevancia()
    
    Búsqueda con sistema de umbrales escalonados + filtrado LLM.
    Wrapper de compatibilidad hacia la nueva arquitectura.
    """
    return _search_service.buscar_proveedores_con_relevancia(
        product=product,
        top_k=top_k,
        marca_filtro=marca_filtro
    )


def obtener_detalle_proveedor(proveedor_id: int) -> Optional[dict]:
    """
    DEPRECATED: Usar SearchService.obtener_detalle_proveedor()
    
    Obtiene el detalle de contacto de un proveedor por id.
    Wrapper de compatibilidad hacia la nueva arquitectura.
    """
    return _search_service.obtener_detalle_proveedor(proveedor_id)


def obtener_marcas_disponibles(product: str, top_k: int = 50) -> List[str]:
    """
    DEPRECATED: Usar SearchService.obtener_marcas_disponibles()
    
    Obtiene las marcas disponibles para un producto dado.
    Wrapper de compatibilidad hacia la nueva arquitectura.
    """
    return _search_service.obtener_marcas_disponibles(product, top_k)


def filtrar_productos_con_llm(productos: List[dict], consulta_original: str) -> List[dict]:
    """
    DEPRECATED: Usar ProductFilterService.filter_with_llm()
    
    Filtra productos usando LLM para evaluar relevancia real.
    Wrapper de compatibilidad hacia la nueva arquitectura.
    """
    from chat.services.product_filter_service import ProductFilterService
    
    filter_service = ProductFilterService()
    return filter_service.filter_with_llm(productos, consulta_original)


# Funciones auxiliares internas (también disponibles a través de WhatsAppFormatter)
def _wa_links_multi(raw: str | None, default_cc: str = "52") -> Tuple[List[str], List[str]]:
    """
    DEPRECATED: Usar WhatsAppFormatter.format_numbers()
    
    Wrapper de compatibilidad hacia la nueva arquitectura.
    """
    from chat.services.whatsapp_formatter import WhatsAppFormatter
    
    return WhatsAppFormatter.format_numbers(raw, default_cc)


def _agrupar_proveedores_con_precios(productos: List[dict]) -> List[dict]:
    """
    DEPRECATED: Usar DataTransformer.proveedores_con_precios()
    
    Wrapper de compatibilidad hacia la nueva arquitectura.
    """
    from chat.services.data_transformer import DataTransformer
    
    transformer = DataTransformer()
    proveedores = transformer.proveedores_con_precios(productos)
    
    # Formatear salida como en versión anterior
    salida = []
    for i, p in enumerate(proveedores, 1):
        ejemplos = ", ".join(p["ejemplos"]) if p["ejemplos"] else "—"
        salida.append({
            "rank": i,
            "proveedor_id": p["proveedor_id"],
            "proveedor": p["proveedor"],
            "coincidencias": p["matches"],
            "mejor_score": round(p["best_score"], 3),
            "ejemplos": ejemplos,
            "contexto_precios": p.get("contexto_precios", []),
            "contacto_detallado": {
                "nombre_ejecutivo_ventas": p["ejecutivo_ventas"],
                "whatsapp_ventas_list": p["whatsapp_ventas_list"],
                "whatsapp_links": p["whatsapp_links"],
                "pagina_web": p["pagina_web"],
            },
        })
    
    return salida


# Re-exportar funciones auxiliares para compatibilidad completa
def _split_phones(raw: str | None) -> List[str]:
    """DEPRECATED: Usar WhatsAppFormatter"""
    from chat.services.whatsapp_formatter import WhatsAppFormatter
    return WhatsAppFormatter._split_phones(raw)


def _only_digits(s: str) -> str:
    """DEPRECATED: Usar WhatsAppFormatter"""
    from chat.services.whatsapp_formatter import WhatsAppFormatter
    return WhatsAppFormatter._only_digits(s)


def _normalize_with_cc(digits: str, default_cc: str = "52") -> str:
    """DEPRECATED: Usar WhatsAppFormatter"""
    from chat.services.whatsapp_formatter import WhatsAppFormatter
    return WhatsAppFormatter._normalize_with_cc(digits, default_cc)


# =====================================================
# Exports para compatibilidad total
# =====================================================

__all__ = [
    # Funciones principales
    "buscar_productos_mejorado",
    "buscar_proveedores_por_producto",
    "buscar_proveedores_con_relevancia",
    "obtener_detalle_proveedor",
    "obtener_marcas_disponibles",
    "filtrar_productos_con_llm",
    # Funciones auxiliares
    "_wa_links_multi",
    "_agrupar_proveedores_con_precios",
    "_split_phones",
    "_only_digits",
    "_normalize_with_cc",
]
