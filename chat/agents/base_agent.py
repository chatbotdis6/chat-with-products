"""Clase base para agentes - Template Method Pattern."""
import logging
from typing import Tuple, List
from abc import ABC, abstractmethod
from langchain_openai import ChatOpenAI

from chat.config.settings import settings

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Clase base para todos los agentes especializados."""
    
    def __init__(self):
        """Inicializa el agente con un LLM."""
        self.llm = ChatOpenAI(model=settings.CHAT_MODEL)
        self.agent_name = self.__class__.__name__
        logger.info(f"✅ {self.agent_name} inicializado")
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Retorna el system prompt del agente."""
        pass
    
    def respond(self, mensaje: str, history: list) -> Tuple[str, list]:
        """
        Responde al usuario y actualiza el historial.
        
        Args:
            mensaje: Mensaje del usuario
            history: Historial de conversación
            
        Returns:
            Tuple de (respuesta, nuevo_historial)
        """
        logger.info(f"{'═' * 60}")
        logger.info(f"{self.get_emoji()} AGENTE: {self.agent_name}")
        logger.debug(f"📝 Mensaje: '{mensaje[:80]}...'")
        
        response = self.llm.invoke([
            ("system", self.get_system_prompt()),
            ("user", mensaje)
        ])
        
        logger.info(f"✅ {self.agent_name} respondió: {len(response.content)} caracteres")
        logger.info(f"{'═' * 60}")
        
        # Actualizar historial
        new_history = history + [
            ("user", mensaje),
            ("assistant", response.content)
        ]
        
        return response.content, new_history
    
    @abstractmethod
    def get_emoji(self) -> str:
        """Retorna el emoji representativo del agente."""
        pass
