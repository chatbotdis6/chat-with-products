"""Servicio de router para detectar intenciones - Strategy Pattern."""
import logging
from typing import Tuple
from langchain_openai import ChatOpenAI

from chat.models.types import IntentType
from chat.config.settings import settings
from chat.prompts.system_prompts import system_prompts
from chat.services.difficult_user_service import difficult_user_service
from chat.agents import (
    ChefAgent,
    NutriologoAgent,
    BartenderAgent,
    BaristaAgent,
    IngenieroAgent,
)

logger = logging.getLogger(__name__)


class IntentRouter:
    """
    Router que detecta la intención del usuario y delega a agentes especializados.
    Aplica Strategy Pattern para routing dinámico.
    """
    
    def __init__(self):
        """Inicializa el router con todos los agentes especializados."""
        # Usar modelo más capaz para el router (mejor comprensión contextual)
        self.router_llm = ChatOpenAI(model=settings.ROUTER_MODEL)
        logger.info(f"🧠 Router usando modelo: {settings.ROUTER_MODEL}")
        
        # Instanciar agentes (lazy loading también sería válido)
        self.chef = ChefAgent()
        self.nutriologo = NutriologoAgent()
        self.bartender = BartenderAgent()
        self.barista = BaristaAgent()
        self.ingeniero = IngenieroAgent()
        
        logger.info("✅ IntentRouter inicializado con todos los agentes")
    
    def detectar_intencion(self, mensaje_usuario: str, history: list = None) -> str:
        """
        Usa el LLM como router para clasificar la intención del usuario.
        Considera el contexto de la conversación para mejor clasificación.
        
        Args:
            mensaje_usuario: Mensaje del usuario
            history: Historial de conversación (opcional, mejora la clasificación)
            
        Returns:
            Intención detectada (valor de IntentType)
        """
        logger.info(f"🔍 ══════════════════════════════════════════════════════")
        logger.info(f"🔍 DETECTANDO INTENCIÓN")
        logger.info(f"💬 Mensaje: '{mensaje_usuario[:80]}...'")
        
        # Construir contexto de conversación (últimos 4 mensajes máximo)
        context_messages = []
        if history:
            # Filtrar solo mensajes de usuario y asistente (no system ni tools)
            recent_history = []
            for msg in history[-6:]:  # Últimos 6 mensajes
                if hasattr(msg, 'type'):
                    if msg.type in ('human', 'ai') and hasattr(msg, 'content') and msg.content:
                        recent_history.append((msg.type, msg.content))
                elif isinstance(msg, tuple) and len(msg) == 2:
                    role, content = msg
                    if role in ('user', 'assistant', 'human', 'ai') and content:
                        recent_history.append((role, content))
            
            # Convertir a formato para el prompt
            for role, content in recent_history[-4:]:  # Últimos 4
                role_name = "Usuario" if role in ('user', 'human') else "Asistente"
                # Truncar contenido largo
                content_short = content[:200] + "..." if len(content) > 200 else content
                context_messages.append(f"{role_name}: {content_short}")
        
        # Construir el mensaje para el router
        if context_messages:
            context_str = "\n".join(context_messages)
            user_prompt = f"CONTEXTO DE CONVERSACIÓN RECIENTE:\n{context_str}\n\nMENSAJE ACTUAL A CLASIFICAR:\n{mensaje_usuario}"
            logger.debug(f"📜 Contexto incluido: {len(context_messages)} mensajes")
        else:
            user_prompt = mensaje_usuario
        
        response = self.router_llm.invoke([
            ("system", system_prompts.get_router_prompt()),
            ("user", user_prompt)
        ])
        
        intencion = response.content.strip().lower()
        logger.info(f"🎯 Intención detectada: '{intencion}'")
        logger.info(f"🔍 ══════════════════════════════════════════════════════")
        
        return intencion
    
    def route_to_agent(
        self,
        intencion: str,
        mensaje: str,
        history: list
    ) -> Tuple[str, list, str]:
        """
        Rutea a agente especializado según la intención.
        
        Args:
            intencion: Intención detectada
            mensaje: Mensaje del usuario
            history: Historial de conversación
            
        Returns:
            Tuple de (respuesta, nuevo_historial, route_name)
        """
        route_name = "unknown"
        
        try:
            # Mapear intenciones a agentes
            if intencion == IntentType.CHEF.value:
                logger.info(f"👨‍🍳 Ruta: CHEF (recetas y preparación)")
                respuesta, history = self.chef.respond(mensaje, history)
                route_name = "chef"
                
            elif intencion == IntentType.NUTRIOLOGO.value:
                logger.info(f"🥗 Ruta: NUTRIÓLOGO (información nutricional)")
                respuesta, history = self.nutriologo.respond(mensaje, history)
                route_name = "nutriologo"
                
            elif intencion == IntentType.BARTENDER.value:
                logger.info(f"🍹 Ruta: BARTENDER (cócteles y bebidas)")
                respuesta, history = self.bartender.respond(mensaje, history)
                route_name = "bartender"
                
            elif intencion == IntentType.BARISTA.value:
                logger.info(f"☕ Ruta: BARISTA (técnicas de café)")
                respuesta, history = self.barista.respond(mensaje, history)
                route_name = "barista"
                
            elif intencion == IntentType.INGENIERO_ALIMENTOS.value:
                logger.info(f"🔬 Ruta: INGENIERO EN ALIMENTOS (conservación)")
                respuesta, history = self.ingeniero.respond(mensaje, history)
                route_name = "ingeniero"
                
            elif intencion == IntentType.FUERA_ALCANCE.value:
                logger.warning(f"⚠️  Ruta: FUERA DE ALCANCE")
                respuesta = self._responder_fuera_alcance(mensaje, history)
                history = history + [
                    ("user", mensaje),
                    ("assistant", respuesta)
                ]
                route_name = "fuera_alcance"
                
            else:
                # Fallback para intenciones desconocidas
                logger.error(f"❌ Intención desconocida: '{intencion}'")
                respuesta = "Disculpa, no entendí tu consulta. ¿Puedes reformularla? 😊"
                history = history + [
                    ("user", mensaje),
                    ("assistant", respuesta)
                ]
                route_name = "unknown"
            
            return respuesta, history, route_name
            
        except Exception as e:
            logger.error(f"❌ Error en routing: {e}", exc_info=True)
            respuesta = "Lo siento, hubo un error procesando tu solicitud. ¿Puedes intentarlo de nuevo? 😊"
            history = history + [
                ("user", mensaje),
                ("assistant", respuesta)
            ]
            return respuesta, history, "error"
    
    def _responder_fuera_alcance(self, mensaje: str, history: list = None) -> str:
        """
        Responde cuando la pregunta está fuera de alcance.
        Usa el servicio de usuarios difíciles para dar respuestas apropiadas.
        
        Args:
            mensaje: Mensaje del usuario
            history: Historial para detectar insistencia
        """
        logger.warning(f"⚠️ ══════════════════════════════════════════════════════")
        logger.warning(f"⚠️  PREGUNTA FUERA DE ALCANCE - Clasificando tipo...")
        
        # Contar insistencia en temas fuera del sector
        insistencia_count = self._contar_insistencia_fuera_alcance(history)
        
        # Clasificar tipo de mensaje difícil
        message_type = difficult_user_service.classify_difficult_message(
            mensaje, 
            insistencia_count
        )
        
        # Obtener respuesta apropiada
        respuesta = difficult_user_service.get_response(message_type, mensaje)
        
        logger.info(f"✅ Respuesta para mensaje tipo '{message_type.value}' enviada")
        logger.warning(f"⚠️ ══════════════════════════════════════════════════════")
        
        return respuesta
    
    def _contar_insistencia_fuera_alcance(self, history: list) -> int:
        """
        Cuenta cuántas veces consecutivas el usuario ha insistido en temas fuera del sector.
        
        Args:
            history: Historial de conversación
            
        Returns:
            Número de insistencias consecutivas
        """
        if not history:
            return 0
        
        count = 0
        # Revisar los últimos mensajes del asistente buscando respuestas de fuera_alcance
        for msg in reversed(history):
            role = ""
            content = ""
            
            # Extraer rol y contenido según el tipo de mensaje
            if hasattr(msg, 'type') and hasattr(msg, 'content'):
                role = msg.type
                content = msg.content or ""
            elif isinstance(msg, tuple) and len(msg) == 2:
                role, content = msg
                content = content or ""
            
            # Solo contar respuestas del asistente
            if role in ('assistant', 'ai'):
                # Detectar si la respuesta fue de tipo "fuera de alcance"
                indicadores = [
                    "sector gastronómico" in content.lower(),
                    "fuera de mi área" in content.lower(),
                    "buzón de quejas" in content.lower(),
                    "100% enfocado" in content.lower(),
                ]
                if any(indicadores):
                    count += 1
                else:
                    break  # Si encontramos una respuesta normal, dejamos de contar
                    
        logger.debug(f"📊 Insistencia fuera de alcance contada: {count}")
        return count
