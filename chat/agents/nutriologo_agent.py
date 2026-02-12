"""Agente Nutriólogo - Single Responsibility Principle."""
from chat.agents.base_agent import BaseAgent
from chat.prompts.system_prompts import system_prompts


class NutriologoAgent(BaseAgent):
    """Agente especializado en información nutricional."""
    
    def get_system_prompt(self) -> str:
        """Retorna el system prompt del nutriólogo."""
        return system_prompts.get_nutriologo_prompt()
    
    def get_emoji(self) -> str:
        """Emoji del nutriólogo."""
        return "🥗"
