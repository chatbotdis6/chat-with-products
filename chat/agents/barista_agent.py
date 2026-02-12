"""Agente Barista - Single Responsibility Principle."""
from chat.agents.base_agent import BaseAgent
from chat.prompts.system_prompts import system_prompts


class BaristaAgent(BaseAgent):
    """Agente especializado en técnicas de café."""
    
    def get_system_prompt(self) -> str:
        """Retorna el system prompt del barista."""
        return system_prompts.get_barista_prompt()
    
    def get_emoji(self) -> str:
        """Emoji del barista."""
        return "☕"
