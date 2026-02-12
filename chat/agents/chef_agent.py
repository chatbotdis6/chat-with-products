"""Agente Chef - Single Responsibility Principle."""
from chat.agents.base_agent import BaseAgent
from chat.prompts.system_prompts import system_prompts


class ChefAgent(BaseAgent):
    """Agente especializado en recetas y preparación de alimentos."""
    
    def get_system_prompt(self) -> str:
        """Retorna el system prompt del chef."""
        return system_prompts.get_chef_prompt()
    
    def get_emoji(self) -> str:
        """Emoji del chef."""
        return "👨‍🍳"
