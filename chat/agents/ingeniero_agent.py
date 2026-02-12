"""Agente Ingeniero en Alimentos - Single Responsibility Principle."""
from chat.agents.base_agent import BaseAgent
from chat.prompts.system_prompts import system_prompts


class IngenieroAgent(BaseAgent):
    """Agente especializado en conservación e inocuidad alimentaria."""
    
    def get_system_prompt(self) -> str:
        """Retorna el system prompt del ingeniero."""
        return system_prompts.get_ingeniero_prompt()
    
    def get_emoji(self) -> str:
        """Emoji del ingeniero."""
        return "🔬"
