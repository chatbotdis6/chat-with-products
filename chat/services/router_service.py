"""Servicio de routing para detectar intenciones y dirigir a agentes."""
import logging
from langchain_openai import ChatOpenAI

from chat.models.types import IntentType
from chat.agents.base_agent import BaseAgent
from chat.agents import (
    ChefAgent,
    NutriologoAgent,
    BartenderAgent,
    BaristaAgent,
    IngenieroAgent,
)
from chat.prompts import system_prompts
from chat.config import settings

logger = logging.getLogger(__name__)


class RouterService:
    """Servicio para detectar intenciones y routear a agentes apropiados."""
    
    def __init__(self):
        """Inicializa el servicio de routing."""
        self.llm = ChatOpenAI(model=settings.CHAT_MODEL)
        logger.info("✅ RouterService inicializado")
    
    def detect_intent(self, mensaje: str) -> IntentType:
        """
        Detecta la intención del usuario usando LLM.
        
        Args:
            mensaje: Mensaje del usuario
            
        Returns:
            IntentType correspondiente a la intención detectada
        """
        logger.info(f"🔍 Detectando intención para: '{mensaje[:50]}...'")
        
        response = self.llm.invoke([
            ("system", system_prompts.get_router_prompt()),
            ("user", mensaje)
        ])
        
        intencion_str = response.content.strip().lower()
        logger.info(f"🎯 Intención detectada: '{intencion_str}'")
        
        # Mapear string a enum
        try:
            intent = IntentType(intencion_str)
        except ValueError:
            logger.warning(f"⚠️  Intención desconocida: '{intencion_str}', usando BUSQUEDA_PROVEEDORES")
            intent = IntentType.BUSQUEDA_PROVEEDORES
        
        return intent
    
    def get_agent_for_intent(self, intent: IntentType) -> BaseAgent:
        """
        Obtiene el agente apropiado para la intención detectada.
        
        Args:
            intent: Intención del usuario
            
        Returns:
            Agente especializado correspondiente
        """
        logger.info(f"🤖 Obteniendo agente para intención: {intent.value}")
        
        if intent == IntentType.CHEF:
            return ChefAgent()
        elif intent == IntentType.NUTRIOLOGO:
            return NutriologoAgent()
        elif intent == IntentType.BARTENDER:
            return BartenderAgent()
        elif intent == IntentType.BARISTA:
            return BaristaAgent()
        elif intent == IntentType.INGENIERO_ALIMENTOS:
            return IngenieroAgent()
        else:
            # Por defecto, retornar None (se manejará búsqueda de proveedores)
            logger.warning(f"⚠️  No hay agente específico para {intent.value}")
            return None
    
    def route_message(self, mensaje: str) -> tuple[IntentType, BaseAgent | None]:
        """
        Detecta intención y retorna el agente apropiado.
        
        Args:
            mensaje: Mensaje del usuario
            
        Returns:
            Tuple de (intención detectada, agente o None)
        """
        intent = self.detect_intent(mensaje)
        agent = self.get_agent_for_intent(intent)
        
        return intent, agent
