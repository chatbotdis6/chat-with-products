"""
Specialist Node - Handles specialized role responses (Chef, Nutriólogo, etc.)

Each specialist provides domain-specific advice while redirecting to providers.
"""
import logging
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage

from chat.graph.state import ConversationState, NodeOutput
from chat.config.settings import settings

logger = logging.getLogger(__name__)

# Specialist prompts - compact version for faster responses
SPECIALIST_PROMPTS = {
    "chef": """Eres un chef profesional de The Hap & D Company.
Tu rol: Dar recetas e ideas de preparación BREVES (máximo 3-4 líneas).

Formato obligatorio:
'[Ingredientes principales breves] + [Pasos ultra-resumidos en 1-2 líneas]. 
¿Quieres que te conecte con proveedores de [ingrediente clave]? 😊'

IMPORTANTE:
- Máximo 3-4 líneas de respuesta
- SIEMPRE termina preguntando si quiere proveedores
- Usa emojis relacionados con la comida 🍓🍫🥑
- Sé práctico y directo, sin teoría extensa""",

    "nutriologo": """Eres un nutriólogo profesional de The Hap & D Company.
Tu rol: Dar información nutricional BREVE y práctica.

Formato obligatorio:
'[Alimento] aporta [calorías] kcal [porción], [dato relevante de macros/beneficios]. 
¿Quieres proveedores de [alimento]? 😊'

IMPORTANTE:
- Máximo 2-3 líneas
- SIEMPRE ofrece proveedores al final
- Datos concisos (calorías + 1-2 macros o beneficios clave)
- Usa emojis relacionados 🥗🥑🌾""",

    "bartender": """Eres un bartender profesional de The Hap & D Company.
Tu rol: Dar recetas de cócteles y maridajes BREVES.

Formato obligatorio:
'[Ingredientes con medidas] + [Preparación breve]. 🍹 
¿Quieres proveedores de [ingrediente principal]?'

IMPORTANTE:
- Máximo 3-4 líneas
- SIEMPRE ofrece proveedores al final
- Incluye medidas precisas (ml, oz)
- Usa emojis de bebidas 🍹🍸🥃""",

    "barista": """Eres un barista profesional de The Hap & D Company.
Tu rol: Explicar técnicas de café BREVES y prácticas.

Formato obligatorio:
'[Técnica resumida en 2-3 pasos clave]. ☕ 
¿Quieres proveedores de café [tipo de café]?'

IMPORTANTE:
- Máximo 3-4 líneas
- SIEMPRE ofrece proveedores de café
- Sé técnico pero accesible
- Usa emoji de café ☕""",

    "ingeniero_alimentos": """Eres un ingeniero en alimentos de The Hap & D Company.
Tu rol: Explicar conservación e inocuidad de forma BREVE.

Formato obligatorio:
'[Producto] se conserva [tiempo] en [condiciones]. [Dato adicional de seguridad]. 
¿Quieres proveedores de [producto]? 😊'

IMPORTANTE:
- Máximo 3-4 líneas
- SIEMPRE ofrece proveedores al final
- Incluye temperaturas y tiempos específicos
- Usa emojis relacionados 🧈🥛🍖""",
}


def specialist_node(state: ConversationState) -> NodeOutput:
    """
    Specialist node that handles domain-specific questions.
    
    Specialists:
    - chef: Recipes and cooking techniques
    - nutriologo: Nutritional information
    - bartender: Cocktails and beverages
    - barista: Coffee techniques
    - ingeniero_alimentos: Food preservation and safety
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state with specialist response
    """
    logger.info("👨‍🍳 ════════════════════════════════════════════════════")
    logger.info("👨‍🍳 SPECIALIST NODE")
    
    role = state.get("specialist_role", "chef")
    messages = state.get("messages", [])
    
    logger.info(f"🎭 Role: {role}")
    
    # Get the prompt for this specialist
    system_prompt = SPECIALIST_PROMPTS.get(role, SPECIALIST_PROMPTS["chef"])
    
    # Find the last user message
    last_user_message = ""
    for msg in reversed(messages):
        if hasattr(msg, 'type') and msg.type == "human":
            last_user_message = msg.content
            break
        elif isinstance(msg, HumanMessage):
            last_user_message = msg.content
            break
    
    if not last_user_message:
        logger.warning("⚠️  No user message found for specialist")
        return {
            "response": "¿En qué te puedo ayudar hoy? 😊",
            "response_metadata": {"specialist": role}
        }
    
    logger.info(f"💬 User question: '{last_user_message[:80]}...'")
    
    try:
        # Use the chat model for specialist responses (Chef, Nutriólogo, etc.)
        llm = ChatOpenAI(
            model=settings.CHAT_MODEL,
            temperature=0.7,  # Slightly creative for recipes
        )
        
        response = llm.invoke([
            ("system", system_prompt),
            ("user", last_user_message)
        ])
        
        specialist_response = response.content.strip()
        
        # Clean up bracket artifacts that LLMs sometimes generate
        import re
        specialist_response = re.sub(r'\[([^\]]+)\]:\s*', r'\1: ', specialist_response)
        specialist_response = re.sub(r'\[([^\]]+)\]', r'\1', specialist_response)
        
        logger.info(f"✅ Specialist response generated ({len(specialist_response)} chars)")
        logger.info("👨‍🍳 ════════════════════════════════════════════════════")
        
        return {
            "response": specialist_response,
            "response_metadata": {
                "specialist": role,
                "tokens": response.usage_metadata if hasattr(response, 'usage_metadata') else None
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Specialist error: {e}", exc_info=True)
        return {
            "response": f"Lo siento, tuve un problema procesando tu consulta. ¿Puedo ayudarte a encontrar proveedores de algo específico? 😊",
            "error": str(e),
            "error_node": "specialist",
            "response_metadata": {"specialist": role}
        }
