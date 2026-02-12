"""
Capa de compatibilidad para mantener funcionalidad de search.py original.
Este módulo exporta las funciones principales para uso externo.
"""
from chat.services.search_service import SearchService
from chat.services.whatsapp_formatter import WhatsAppFormatter

# Instancia global del servicio (Singleton pattern)
_search_service = None


def _get_search_service():
    """Obtiene o crea la instancia del servicio de búsqueda."""
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service


# ===== FUNCIONES PÚBLICAS (compatibilidad con código legacy) =====

def buscar_productos_mejorado(
    search_query: str,
    top_k: int = 20,
    knn_limit: int = 200,
    threshold_trgm: float = 0.40,
    threshold_vector: float = 0.75,
    w_trgm: float = 0.6,
    w_vec: float = 0.4,
):
    """
    Búsqueda híbrida de productos (trigram + vector).
    
    Wrapper de compatibilidad para SearchService.buscar_productos_mejorado()
    """
    service = _get_search_service()
    return service.buscar_productos_mejorado(
        search_query=search_query,
        top_k=top_k,
        knn_limit=knn_limit,
        threshold_trgm=threshold_trgm,
        threshold_vector=threshold_vector,
        w_trgm=w_trgm,
        w_vec=w_vec,
    )


def buscar_proveedores_con_relevancia(product: str, top_k: int = 25, marca_filtro: str = None):
    """
    Búsqueda con sistema de umbrales escalonados + filtrado inteligente con LLM.
    
    Wrapper de compatibilidad para SearchService.buscar_proveedores_con_relevancia()
    """
    service = _get_search_service()
    return service.buscar_proveedores_con_relevancia(
        product=product,
        top_k=top_k,
        marca_filtro=marca_filtro
    )


def obtener_detalle_proveedor(proveedor_id: int):
    """
    Obtiene el detalle de contacto de un proveedor por id.
    
    Wrapper de compatibilidad para SearchService.obtener_detalle_proveedor()
    """
    service = _get_search_service()
    return service.obtener_detalle_proveedor(proveedor_id)


def obtener_marcas_disponibles(product: str, top_k: int = 50):
    """
    Obtiene las marcas disponibles para un producto dado.
    
    Wrapper de compatibilidad para SearchService.obtener_marcas_disponibles()
    """
    service = _get_search_service()
    return service.obtener_marcas_disponibles(product, top_k)


# ===== FUNCIONES AUXILIARES (ahora usan WhatsAppFormatter) =====

def _wa_links_multi(raw: str, default_cc: str = "52"):
    """
    Wrapper de compatibilidad para WhatsAppFormatter.format_numbers()
    """
    return WhatsAppFormatter.format_numbers(raw, default_cc)


# Exportar para compatibilidad
__all__ = [
    "buscar_productos_mejorado",
    "buscar_proveedores_con_relevancia",
    "obtener_detalle_proveedor",
    "obtener_marcas_disponibles",
]
