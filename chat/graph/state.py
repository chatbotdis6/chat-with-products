"""
Unified conversation state for LangGraph.

This module defines the state schema that flows through all graph nodes.
Uses TypedDict for type safety and LangGraph compatibility.
"""
from typing import TypedDict, List, Dict, Any, Optional, Literal, Annotated
from enum import Enum
from operator import add
from langchain_core.messages import BaseMessage


class IntentCategory(str, Enum):
    """Categorías de intención del usuario."""
    # Búsqueda de proveedores/productos
    BUSQUEDA_PROVEEDORES = "busqueda_proveedores"
    MOSTRAR_MAS = "mostrar_mas"
    DETALLE_PROVEEDOR = "detalle_proveedor"
    FILTRAR_MARCA = "filtrar_marca"
    FILTRAR_PRECIO = "filtrar_precio"
    
    # Roles especializados
    CHEF = "chef"
    NUTRIOLOGO = "nutriologo"
    BARTENDER = "bartender"
    BARISTA = "barista"
    INGENIERO_ALIMENTOS = "ingeniero_alimentos"
    
    # Conversación general
    SALUDO = "saludo"
    DESPEDIDA = "despedida"
    AGRADECIMIENTO = "agradecimiento"
    
    # Casos especiales
    FUERA_ALCANCE = "fuera_alcance"
    UNKNOWN = "unknown"


class DifficultUserType(str, Enum):
    """Tipos de comportamiento difícil del usuario."""
    NONE = "none"
    QUEJA_SERVICIO = "queja_servicio"
    DESCALIFICACION = "descalificacion" 
    INSULTO_AGRESION = "insulto_agresion"
    INSISTENCIA_FUERA = "insistencia_fuera"


class RelevanciaLevel(str, Enum):
    """Niveles de relevancia de búsqueda."""
    ALTA = "alta"
    MEDIA = "media"
    NULA = "nula"


class RouterOutput(TypedDict):
    """Output estructurado del router node."""
    intent: str
    entities: Dict[str, Any]
    is_difficult: bool
    difficult_type: str
    requires_search: bool
    confidence: float


class SearchFilters(TypedDict, total=False):
    """Filtros extraídos para la búsqueda."""
    producto: Optional[str]
    marca: Optional[str]
    precio_max: Optional[float]
    precio_min: Optional[float]
    proveedor_id: Optional[int]
    categoria: Optional[str]


class ProveedorResult(TypedDict, total=False):
    """Resultado de un proveedor de la búsqueda."""
    rank: int
    proveedor_id: int
    proveedor: str
    descripcion: str  # Descripción del proveedor
    ejemplos: str     # Ejemplos de productos que ofrece
    coincidencias: int
    mejor_score: float
    contexto_precios: List[Dict[str, Any]]
    contacto_detallado: Optional[Dict[str, Any]]


class SearchResults(TypedDict, total=False):
    """Resultados de búsqueda estructurados."""
    nivel_relevancia: str
    mensaje: str
    proveedores_mostrados: int
    proveedores_ocultos: int
    proveedores: List[ProveedorResult]
    marcas_disponibles: List[str]
    sql_query: Optional[str]  # Para debug/logging


class UnregisteredProductInfo(TypedDict, total=False):
    """Información sobre producto no registrado."""
    producto: str
    es_gastronomico: bool
    email_enviado: bool
    mensaje_usuario: str


class ConversationState(TypedDict, total=False):
    """
    Estado unificado de la conversación que fluye a través de todos los nodos.
    
    Este estado es inmutable entre llamadas - cada nodo retorna un nuevo estado
    con los campos actualizados.
    
    Attributes:
        messages: Historial de mensajes LangChain
        session_id: Identificador único de sesión (para WhatsApp: phone number)
        turn_number: Número de turno actual en la conversación
        
        # Router output
        intent: Intención detectada del usuario
        entities: Entidades extraídas (producto, marca, precio, etc.)
        is_difficult_user: Si el usuario mostró comportamiento difícil
        difficult_type: Tipo de comportamiento difícil
        requires_search: Si requiere búsqueda en DB
        
        # Search state
        search_filters: Filtros para la búsqueda SQL
        search_results: Resultados de la búsqueda
        nivel_relevancia: Nivel de relevancia de resultados
        pending_providers: IDs de proveedores ocultos para "mostrar más"
        
        # Response state  
        response: Respuesta generada para el usuario
        response_metadata: Metadatos de la respuesta (tokens, tiempo, etc.)
        
        # Unregistered product state
        unregistered_product: Info de producto no encontrado
        
        # Platform transition
        should_suggest_platform: Si debe sugerir transición a web
        platform_suggestion: Mensaje de sugerencia de plataforma
        
        # Error handling
        error: Mensaje de error si algo falla
        error_node: Nodo donde ocurrió el error
    """
    # Core conversation state
    messages: Annotated[List[BaseMessage], add]
    session_id: str
    turn_number: int
    user_phone: Optional[str]  # Para WhatsApp
    
    # Router output
    intent: str
    entities: Dict[str, Any]
    is_difficult_user: bool
    difficult_type: str
    requires_search: bool
    router_confidence: float
    
    # Search state
    search_filters: SearchFilters
    search_results: Optional[SearchResults]
    nivel_relevancia: str
    pending_providers: List[int]
    last_search_query: str
    
    # Specialist role context
    specialist_role: Optional[str]
    
    # Response state
    response: str
    response_metadata: Dict[str, Any]
    
    # Unregistered product handling (Task 6)
    unregistered_product: Optional[UnregisteredProductInfo]
    
    # Platform transition (Task 8)
    should_suggest_platform: bool
    platform_suggestion: Optional[str]
    platform_exhausted: bool  # True when max free turns reached — block further use
    
    # Error handling
    error: Optional[str]
    error_node: Optional[str]


def create_initial_state(
    session_id: str,
    user_phone: Optional[str] = None
) -> ConversationState:
    """
    Crea el estado inicial para una nueva conversación.
    
    Args:
        session_id: ID único de la sesión
        user_phone: Teléfono del usuario (opcional, para WhatsApp)
        
    Returns:
        Estado inicial de conversación
    """
    return ConversationState(
        messages=[],
        session_id=session_id,
        turn_number=0,
        user_phone=user_phone,
        
        intent=IntentCategory.UNKNOWN.value,
        entities={},
        is_difficult_user=False,
        difficult_type=DifficultUserType.NONE.value,
        requires_search=False,
        router_confidence=0.0,
        
        search_filters={},
        search_results=None,
        nivel_relevancia="",
        pending_providers=[],
        last_search_query="",
        
        specialist_role=None,
        
        response="",
        response_metadata={},
        
        unregistered_product=None,
        
        should_suggest_platform=False,
        platform_suggestion=None,
        platform_exhausted=False,
        
        error=None,
        error_node=None,
    )


# Type alias for node return type
NodeOutput = Dict[str, Any]
