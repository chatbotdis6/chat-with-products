"""
Chatbot principal refactorizado - Facade Pattern.

Este módulo orquesta todos los componentes del sistema siguiendo principios SOLID:
- Single Responsibility: Cada componente tiene una única responsabilidad
- Open/Closed: Extensible mediante nuevos agentes sin modificar código existente
- Liskov Substitution: Todos los agentes heredan de BaseAgent
- Interface Segregation: Servicios específicos para cada funcionalidad
- Dependency Inversion: Dependencias sobre abstracciones, no implementaciones concretas
"""
import logging
from typing import Annotated, TypedDict, List
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages, AnyMessage
from langgraph.prebuilt import ToolNode

# Importaciones locales refactorizadas
from chat.config.settings import settings
from chat.prompts.system_prompts import system_prompts
from chat.models.types import IntentType
from chat.tools import TOOLS
from chat.services.intent_router import IntentRouter

# Configurar logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format=settings.LOG_FORMAT,
    datefmt=settings.LOG_DATE_FORMAT
)
logger = logging.getLogger(__name__)


# ========== ESTADO ==========
class MessagesState(TypedDict):
    """Estado de mensajes para el grafo de conversación."""
    messages: Annotated[List[AnyMessage], add_messages]


logger.info("📦 MessagesState definido")


# ========== GRAFO DE CONVERSACIÓN (BÚSQUEDA DE PROVEEDORES) ==========
class ConversationGraph:
    """
    Grafo de conversación para búsqueda de proveedores con tools.
    Aplica Facade Pattern para simplificar la interfaz del grafo.
    """
    
    def __init__(self):
        """Inicializa el grafo de conversación."""
        logger.info("📊 Construyendo grafo de conversación...")
        
        # Modelo LLM con tools
        self.llm = ChatOpenAI(model=settings.CHAT_MODEL).bind_tools(TOOLS)
        logger.info(f"🤖 Usando modelo LLM: {settings.CHAT_MODEL}")
        logger.info(f"✅ LLM inicializado con {len(TOOLS)} tools vinculadas")
        
        # Tool node
        self.tool_node = ToolNode(TOOLS)
        logger.info("🔧 ToolNode creado con las tools disponibles")
        
        # Construir grafo
        graph = StateGraph(MessagesState)
        graph.add_node("assistant", self._assistant_node)
        logger.debug("   ✓ Nodo 'assistant' agregado")
        graph.add_node("tools", self.tool_node)
        logger.debug("   ✓ Nodo 'tools' agregado")
        
        graph.set_entry_point("assistant")
        logger.debug("   ✓ Entry point configurado: 'assistant'")
        graph.add_conditional_edges("assistant", self._router)
        logger.debug("   ✓ Conditional edges agregadas: assistant -> router")
        graph.add_edge("tools", "assistant")
        logger.debug("   ✓ Edge agregada: tools -> assistant")
        
        self.app = graph.compile()
        logger.info("✅ Grafo compilado exitosamente")
    
    def _assistant_node(self, state: MessagesState) -> dict:
        """Llama al modelo y retorna el siguiente mensaje."""
        logger.info("🤖 ═══════════════════════════════════════════════════════")
        logger.info("🤖 NODO: assistant_node - Invocando LLM...")
        logger.debug(f"📥 Estado recibido con {len(state['messages'])} mensaje(s)")
        
        # Log del último mensaje del usuario
        if state['messages']:
            last_user_msg = None
            for msg in reversed(state['messages']):
                if hasattr(msg, 'type') and msg.type == 'human':
                    last_user_msg = msg
                    break
            if last_user_msg:
                logger.info(f"💬 Último mensaje del usuario: '{last_user_msg.content}'")
        
        ai_msg = self.llm.invoke(state["messages"])
        
        logger.info(f"✅ LLM respondió")
        logger.debug(f"📝 Tipo de respuesta: {type(ai_msg).__name__}")
        
        # Log de tool calls si existen
        tool_calls = getattr(ai_msg, "tool_calls", None)
        if tool_calls:
            tool_names = [tc.get("name", "unknown") for tc in tool_calls]
            logger.info(f"🛠️  LLM solicitó {len(tool_calls)} tool(s): {tool_names}")
            for idx, tc in enumerate(tool_calls, 1):
                logger.debug(f"   {idx}. Tool: {tc.get('name', 'unknown')}")
                logger.debug(f"      Args: {tc.get('args', {})}")
        else:
            logger.info(f"💬 LLM generó respuesta final (sin tool calls)")
            logger.info(f"📄 Respuesta completa del asistente:")
            logger.info(f"{'─' * 60}")
            logger.info(f"{ai_msg.content}")
            logger.info(f"{'─' * 60}")
        
        logger.info("🤖 ═══════════════════════════════════════════════════════")
        return {"messages": [ai_msg]}
    
    def _router(self, state: MessagesState):
        """Si el último mensaje pide tools, vamos a 'tools'; si no, terminamos."""
        logger.info("🔀 ═══════════════════════════════════════════════════════")
        logger.info("🔀 ROUTER: Determinando siguiente nodo...")
        logger.debug(f"📥 Estado con {len(state['messages'])} mensaje(s)")
        
        last = state["messages"][-1]
        logger.debug(f"🔍 Último mensaje: {type(last).__name__}")
        
        tool_calls = getattr(last, "tool_calls", None)
        if tool_calls:
            logger.info(f"🔧 Router: dirigiendo a nodo 'tools' ({len(tool_calls)} tool call(s))")
            logger.debug(f"   Tools a ejecutar: {[tc.get('name', 'unknown') for tc in tool_calls]}")
            logger.info("🔀 ═══════════════════════════════════════════════════════")
            return "tools"
        
        logger.info("🏁 Router: finalizando conversación (END)")
        logger.debug("✅ No hay tool calls pendientes - conversación completa")
        logger.info("🔀 ═══════════════════════════════════════════════════════")
        return END
    
    def invoke(self, messages: list) -> dict:
        """Ejecuta el grafo con los mensajes dados."""
        return self.app.invoke({"messages": messages})


# ========== ORCHESTRATOR PRINCIPAL ==========
class Chatbot:
    """
    Orquestador principal del chatbot multi-agente.
    Aplica Facade Pattern para simplificar la interfaz.
    """
    
    def __init__(self):
        """Inicializa el chatbot con todos sus componentes."""
        logger.info("=" * 60)
        logger.info("🚀 Inicializando Chatbot - The Hap & D Company")
        logger.info("=" * 60)
        
        # Componentes
        self.graph = ConversationGraph()
        self.router = IntentRouter()
        
        # Historial inicial con system prompt
        self.initial_history = [("system", system_prompts.get_main_prompt())]
        logger.info("📋 Historial inicializado con system prompt")
        
        logger.info(f"🤖 Modelo: {settings.CHAT_MODEL}")
        logger.info(f"🔧 Tools disponibles: {len(TOOLS)}")
        logger.info(f"📧 Buzón de quejas: {settings.BUZON_QUEJAS}")
        logger.info(f"🎭 Roles disponibles: Buscador, Chef, Nutriólogo, Bartender, Barista, Ingeniero")
        logger.info("=" * 60)
        logger.info("✅ Chatbot inicializado exitosamente")
    
    def process_message(self, mensaje: str, history: list, turn_number: int = 0) -> tuple[str, list]:
        """
        Procesa un mensaje del usuario y retorna la respuesta.
        
        Args:
            mensaje: Mensaje del usuario
            history: Historial de conversación
            turn_number: Número de turno (para logging)
            
        Returns:
            Tuple de (respuesta, nuevo_historial)
        """
        from chat.services.platform_transition_service import PlatformTransitionService
        transition_service = PlatformTransitionService()
        
        if turn_number > 0:
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.info(f"💬 TURNO {turn_number} - Usuario: {mensaje}")
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        # PASO 0: Verificar si se debe usar plantilla fija (turno 6+)
        if turn_number > settings.CONSULTAS_ANTES_PLANTILLA:
            logger.warning(f"🚨 PLANTILLA FIJA: Turno {turn_number} > {settings.CONSULTAS_ANTES_PLANTILLA}")
            respuesta = transition_service.get_mandatory_redirect_message()
            # Agregar al historial sin procesar con LLM
            history = list(history)
            history.append(("user", mensaje))
            history.append(("assistant", respuesta))
            logger.info(f"✅ TURNO {turn_number} completado (plantilla fija)")
            return respuesta, history
        
        # PASO 0.5: Verificar si se debe derivar con LLM (turno 5)
        if turn_number > settings.CONSULTAS_ANTES_DERIVACION:
            logger.warning(f"🚀 DERIVACIÓN CON LLM: Turno {turn_number} = derivar a plataforma")
            # Usar LLM pero con instrucciones de derivar, no responder
            derivation_prompt = transition_service.get_llm_derivation_prompt(mensaje)
            history = list(history)
            history.append(("user", derivation_prompt))
            
            out = self.graph.invoke(history)
            last = out["messages"][-1]
            respuesta = last.content
            # Reemplazar el prompt de derivación por el mensaje original en el historial
            history = out["messages"]
            logger.info(f"✅ TURNO {turn_number} completado (derivación con LLM)")
            return respuesta, history
        
        # PASO 1: Detectar intención (pasando contexto de conversación)
        intencion = self.router.detectar_intencion(mensaje, history)
        
        # PASO 2: Rutear según la intención
        if intencion == IntentType.BUSQUEDA_PROVEEDORES.value:
            # Flujo normal con tools (búsqueda de proveedores)
            logger.info(f"🔍 Ruta: BÚSQUEDA DE PROVEEDORES (con tools)")
            history = list(history)  # Asegurar que es mutable
            history.append(("user", mensaje))
            
            out = self.graph.invoke(history)
            last = out["messages"][-1]
            respuesta = last.content
            history = out["messages"]
        else:
            # Agentes especializados
            respuesta, history, _ = self.router.route_to_agent(intencion, mensaje, history)
        
        # PASO 3: Agregar sugerencia suave de plataforma si corresponde
        if turn_number >= settings.CONSULTAS_ANTES_SUGERENCIA and turn_number <= settings.CONSULTAS_ANTES_DERIVACION:
            sugerencia = transition_service.get_soft_suggestion_message(turn_number)
            if sugerencia and sugerencia not in respuesta:
                respuesta += sugerencia
                logger.info(f"💡 Sugerencia de plataforma añadida (turno {turn_number})")
        
        if turn_number > 0:
            logger.info(f"✅ TURNO {turn_number} completado")
            logger.debug(f"📚 Historial actualizado: {len(history)} mensajes totales")
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        return respuesta, history


# ========== CLI DEMO ==========
def main():
    """Función principal para demo CLI."""
    chatbot = Chatbot()
    
    print("Chat demo. Escribe 'salir' para terminar.")
    history = chatbot.initial_history.copy()
    
    turn_number = 0
    while True:
        q = input("> ").strip()
        if not q:
            continue
        if q.lower() in {"salir", "exit", "quit"}:
            logger.info("👋 Usuario finalizó la sesión")
            logger.info("=" * 60)
            break
        
        turn_number += 1
        respuesta, history = chatbot.process_message(q, history, turn_number)
        print(respuesta)


logger.info("📦 Módulo chatbot_refactored.py cargado completamente")

if __name__ == "__main__":
    main()
