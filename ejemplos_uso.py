"""
Ejemplos de uso de la nueva arquitectura refactorizada.

Este archivo muestra cómo usar los diferentes componentes de la arquitectura.
"""

# ============================================================
# EJEMPLO 1: Usar el Chatbot Refactorizado (Recomendado)
# ============================================================

def ejemplo_chatbot_basico():
    """Ejemplo básico usando el chatbot refactorizado."""
    from chat.chatbot_refactored import Chatbot
    
    # Crear instancia del chatbot
    bot = Chatbot()
    
    # Procesar mensajes
    response1 = bot.process_message("Busco mantequilla Anchor")
    print("Respuesta 1:", response1)
    
    response2 = bot.process_message("¿Cómo hacer fresas Dubai?")
    print("Respuesta 2:", response2)
    
    response3 = bot.process_message("¿Cuántas calorías tiene la quinoa?")
    print("Respuesta 3:", response3)


# ============================================================
# EJEMPLO 2: Usar Servicios Directamente
# ============================================================

def ejemplo_busqueda_productos():
    """Ejemplo de búsqueda de productos usando SearchService."""
    from chat.services import SearchService
    
    # Crear instancia del servicio
    search = SearchService()
    
    # Búsqueda básica
    productos, proveedores = search.buscar_productos_mejorado(
        search_query="aceite de oliva",
        top_k=20
    )
    
    print(f"Encontrados {len(productos)} productos")
    print(f"De {len(proveedores)} proveedores")
    
    # Mostrar primeros 3 productos
    for i, p in enumerate(productos[:3], 1):
        print(f"{i}. {p['producto']} - {p['proveedor']} (Score: {p['score']:.3f})")


def ejemplo_busqueda_con_relevancia():
    """Ejemplo de búsqueda con umbrales escalonados."""
    from chat.services import SearchService
    
    search = SearchService()
    
    # Búsqueda con relevancia y filtrado LLM
    proveedores, nivel, marcas = search.buscar_proveedores_con_relevancia(
        product="mantequilla",
        marca_filtro="Anchor"  # Opcional: filtrar por marca
    )
    
    print(f"Nivel de relevancia: {nivel}")
    print(f"Marcas disponibles: {marcas[:5]}")
    print(f"Proveedores encontrados: {len(proveedores)}")
    
    # Mostrar proveedores
    for prov in proveedores[:3]:
        print(f"- {prov['proveedor']}: {prov['ejemplos']}")


def ejemplo_obtener_detalle_proveedor():
    """Ejemplo de obtener detalles de contacto de un proveedor."""
    from chat.services import SearchService
    
    search = SearchService()
    
    # Obtener detalle por ID
    detalle = search.obtener_detalle_proveedor(proveedor_id=123)
    
    if detalle:
        print(f"Proveedor: {detalle['proveedor']}")
        print(f"Ejecutivo: {detalle['nombre_ejecutivo_ventas']}")
        print(f"WhatsApp: {detalle['whatsapp_links']}")
        print(f"Web: {detalle['pagina_web']}")


# ============================================================
# EJEMPLO 3: Usar Agentes Especializados
# ============================================================

def ejemplo_agentes_especializados():
    """Ejemplo de usar agentes especializados directamente."""
    from chat.agents import (
        ChefAgent,
        NutriologoAgent,
        BartenderAgent,
        BaristaAgent,
        IngenieroAgent
    )
    
    # Agente Chef
    chef = ChefAgent()
    respuesta_chef = chef.respond("¿Cómo hacer tiramisú?")
    print("Chef:", respuesta_chef)
    
    # Agente Nutriólogo
    nutri = NutriologoAgent()
    respuesta_nutri = nutri.respond("¿Cuántas calorías tiene el aguacate?")
    print("Nutriólogo:", respuesta_nutri)
    
    # Agente Bartender
    bartender = BartenderAgent()
    respuesta_bartender = bartender.respond("Cóctel con mezcal")
    print("Bartender:", respuesta_bartender)
    
    # Agente Barista
    barista = BaristaAgent()
    respuesta_barista = barista.respond("¿Cómo hacer cold brew?")
    print("Barista:", respuesta_barista)
    
    # Agente Ingeniero en Alimentos
    ingeniero = IngenieroAgent()
    respuesta_ing = ingeniero.respond("¿Cuánto dura el salmón refrigerado?")
    print("Ingeniero:", respuesta_ing)


# ============================================================
# EJEMPLO 4: Usar Router para Detectar Intenciones
# ============================================================

def ejemplo_router_service():
    """Ejemplo de usar el RouterService para clasificar intenciones."""
    from chat.services.router_service import RouterService
    from chat.models import IntentType
    
    router = RouterService()
    
    # Detectar intención
    mensaje = "Busco proveedores de aceite"
    intent = router.detect_intent(mensaje)
    
    print(f"Mensaje: {mensaje}")
    print(f"Intención detectada: {intent}")
    
    # Obtener agente apropiado
    if intent != IntentType.BUSQUEDA_PROVEEDORES:
        agent = router.get_agent_for_intent(intent)
        response = agent.respond(mensaje)
        print(f"Respuesta: {response}")


# ============================================================
# EJEMPLO 5: Usar Filtrado con LLM
# ============================================================

def ejemplo_filtrado_llm():
    """Ejemplo de filtrar productos usando LLM."""
    from chat.services import SearchService, ProductFilterService
    
    search = SearchService()
    filter_service = ProductFilterService()
    
    # Búsqueda inicial
    productos, _ = search.buscar_productos_mejorado("vino")
    
    print(f"Productos antes del filtrado: {len(productos)}")
    
    # Filtrar con LLM para eliminar irrelevantes
    productos_filtrados = filter_service.filter_with_llm(
        productos=productos,
        consulta_original="vino tinto"
    )
    
    print(f"Productos después del filtrado: {len(productos_filtrados)}")
    
    # Mostrar productos filtrados
    for p in productos_filtrados[:5]:
        print(f"- {p['producto']} ({p['marca']})")


# ============================================================
# EJEMPLO 6: Usar Configuración Centralizada
# ============================================================

def ejemplo_configuracion():
    """Ejemplo de acceder a la configuración centralizada."""
    from chat.config import settings
    
    # Acceder a configuración
    print(f"Modelo LLM: {settings.CHAT_MODEL}")
    print(f"Buzón de quejas: {settings.BUZON_QUEJAS}")
    print(f"Threshold TRGM (alta): {settings.THRESHOLD_TRGM_HIGH}")
    print(f"Threshold Vector (alta): {settings.THRESHOLD_VEC_HIGH}")
    print(f"Top K por defecto: {settings.DEFAULT_TOP_K}")
    print(f"Proveedores mostrados: {settings.MAX_PROVEEDORES_MOSTRADOS}")


# ============================================================
# EJEMPLO 7: Trabajar con Tipos (Type Safety)
# ============================================================

def ejemplo_tipos():
    """Ejemplo de usar los tipos definidos."""
    from chat.models import IntentType, RelevanciaLevel, ProductoInfo
    from typing import List
    
    # Usar enums
    intent = IntentType.CHEF
    print(f"Intención: {intent.value}")
    
    nivel = RelevanciaLevel.ALTA
    print(f"Nivel: {nivel.value}")
    
    # Type hints en funciones
    def procesar_productos(productos: List[ProductoInfo]) -> int:
        """Función con type hints usando tipos personalizados."""
        return len(productos)
    
    # Crear ProductoInfo (TypedDict)
    producto: ProductoInfo = {
        "score": 0.95,
        "similaridad_trgm": 0.85,
        "similaridad_vector": 0.90,
        "producto": "Aceite de Oliva Extra Virgen",
        "marca": "Bertolli",
        "precio": 150.0,
        "moneda": "MXN",
        "proveedor_id": 1,
        "proveedor": "Proveedor ABC",
        "id": 123,
        "id_producto_csv": 456,
    }
    
    print(f"Producto: {producto['producto']}")


# ============================================================
# EJEMPLO 8: Usar Formateo de WhatsApp
# ============================================================

def ejemplo_whatsapp_formatter():
    """Ejemplo de formatear números de WhatsApp."""
    from chat.services import WhatsAppFormatter
    
    # Números en diferentes formatos
    raw_phones = "5512345678, 52 55 8765 4321, +52 1 55 1111 2222"
    
    # Formatear
    numeros, links = WhatsAppFormatter.format_numbers(raw_phones)
    
    print("Números normalizados:")
    for num in numeros:
        print(f"  - {num}")
    
    print("\nEnlaces de WhatsApp:")
    for link in links:
        print(f"  - {link}")


# ============================================================
# EJEMPLO 9: Compatibilidad con Código Antiguo
# ============================================================

def ejemplo_compatibilidad():
    """Ejemplo de usar la capa de compatibilidad."""
    # Importar funciones antiguas (wrappers hacia nueva arquitectura)
    from chat.search import (
        buscar_productos_mejorado,
        buscar_proveedores_con_relevancia,
        obtener_detalle_proveedor
    )
    
    # Usar como antes (funciona igual)
    productos, proveedores = buscar_productos_mejorado("aceite")
    print(f"Productos: {len(productos)}")
    
    # Búsqueda con relevancia
    provs, nivel, marcas = buscar_proveedores_con_relevancia("mantequilla")
    print(f"Nivel: {nivel}, Marcas: {len(marcas)}")
    
    # Detalle de proveedor
    detalle = obtener_detalle_proveedor(1)
    if detalle:
        print(f"Proveedor: {detalle['proveedor']}")


# ============================================================
# EJEMPLO 10: Extender la Arquitectura (Agregar Nuevo Agente)
# ============================================================

def ejemplo_agregar_nuevo_agente():
    """
    Ejemplo de cómo agregar un nuevo agente especializado.
    
    Pasos:
    1. Crear archivo: chat/agents/sommelier_agent.py
    2. Heredar de BaseAgent
    3. Implementar método respond()
    4. Agregar prompt en system_prompts.py
    5. Registrar en RouterService
    """
    
    # Código de ejemplo del nuevo agente:
    """
    # chat/agents/sommelier_agent.py
    from chat.agents.base_agent import BaseAgent
    from chat.prompts import system_prompts
    
    class SommelierAgent(BaseAgent):
        def respond(self, message: str) -> str:
            prompt = system_prompts.get_sommelier_prompt()
            return self._llm_call(prompt, message)
    """
    
    # Agregar enum en models/types.py:
    """
    class IntentType(Enum):
        # ... existentes ...
        SOMMELIER = "sommelier"
    """
    
    # Registrar en RouterService:
    """
    def get_agent_for_intent(self, intent: IntentType) -> BaseAgent:
        # ... casos existentes ...
        elif intent == IntentType.SOMMELIER:
            return SommelierAgent()
    """
    
    print("Ver código de ejemplo arriba para agregar nuevo agente")


# ============================================================
# MAIN: Ejecutar Ejemplos
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("EJEMPLOS DE USO - NUEVA ARQUITECTURA")
    print("=" * 60)
    
    # Descomentar el ejemplo que quieras probar:
    
    # ejemplo_chatbot_basico()
    # ejemplo_busqueda_productos()
    # ejemplo_busqueda_con_relevancia()
    # ejemplo_obtener_detalle_proveedor()
    # ejemplo_agentes_especializados()
    # ejemplo_router_service()
    # ejemplo_filtrado_llm()
    ejemplo_configuracion()
    # ejemplo_tipos()
    # ejemplo_whatsapp_formatter()
    # ejemplo_compatibilidad()
    # ejemplo_agregar_nuevo_agente()
    
    print("\n" + "=" * 60)
    print("Para más información, ver ARCHITECTURE.md")
    print("=" * 60)
