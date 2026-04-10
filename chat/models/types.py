"""Modelos de tipos y enums - Type Safety."""
from typing import TypedDict, List, Dict, Any, Optional
from enum import Enum


class IntentType(Enum):
    """Tipos de intención del usuario (3 macro-categorías)."""
    NEEDS_DB_ACTION = "needs_db_action"
    SPECIALIST = "specialist"
    CONVERSATIONAL = "conversational"


class RelevanciaLevel(Enum):
    """Niveles de relevancia de búsqueda."""
    ALTA = "alta"
    MEDIA = "media"
    NULA = "nula"


class ProveedorInfo(TypedDict, total=False):
    """Información de un proveedor."""
    rank: int
    proveedor_id: int
    proveedor: str
    ejemplos: str
    coincidencias: int
    mejor_score: float
    contexto_precios: List[Dict[str, Any]]
    contacto_detallado: Dict[str, Any]


class ProductoInfo(TypedDict, total=False):
    """Información de un producto."""
    score: float
    similaridad_trgm: float
    similaridad_vector: float
    producto: str
    marca: Optional[str]
    presentacion_venta: Optional[str]
    unidad: Optional[str]
    precio: Optional[float]
    moneda: Optional[str]
    impuesto: Optional[str]  # "más IVA", "Exento de IVA", etc.
    proveedor_id: int
    proveedor: str
    descripcion_proveedor: Optional[str]
    ejecutivo_ventas: Optional[str]
    whatsapp_ventas_raw: Optional[str]
    whatsapp_ventas_list: List[str]
    whatsapp_links: List[str]
    pagina_web: Optional[str]
    nivel_membresia: Optional[float]
    calificacion_usuarios: Optional[float]
    id: int
    id_producto_csv: int


class SearchResult(TypedDict):
    """Resultado de búsqueda."""
    nivel_relevancia: str
    mensaje: str
    proveedores_mostrados: int
    proveedores_ocultos: int
    proveedores: List[ProveedorInfo]
    marcas_disponibles: List[str]


class ContactoDetallado(TypedDict, total=False):
    """Información de contacto detallada."""
    proveedor_id: int
    proveedor: str
    nombre_ejecutivo_ventas: Optional[str]
    whatsapp_ventas_list: List[str]
    whatsapp_links: List[str]
    pagina_web: Optional[str]
