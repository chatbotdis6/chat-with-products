"""Agente Bartender - Single Responsibility Principle."""
from chat.agents.base_agent import BaseAgent
from chat.prompts.system_prompts import system_prompts


class BartenderAgent(BaseAgent):
    """Agente especializado en cócteles y bebidas."""
    
    def get_system_prompt(self) -> str:
        """Retorna el system prompt del bartender."""
        return system_prompts.get_bartender_prompt()
    
    def get_emoji(self) -> str:
        """Emoji del bartender."""
        return "🍹"
