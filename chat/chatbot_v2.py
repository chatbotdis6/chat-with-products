"""
Chatbot V2 - LangGraph-based conversational agent.

This is the new entry point for the chatbot that uses LangGraph
for state management and conversation flow.
"""
import logging
import uuid
from typing import Optional, Dict, Any, List, Tuple

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from chat.graph.state import ConversationState, create_initial_state
from chat.graph.graph import (
    create_conversation_graph, 
    get_conversation_graph
)

logger = logging.getLogger(__name__)


class ChatbotV2:
    """
    LangGraph-based chatbot for The Hap & D Company.
    
    Features:
    - Unified state management through LangGraph
    - Single LLM call for routing (intent + entities + difficult detection)
    - Text-to-SQL for flexible database queries
    - Session persistence with PostgreSQL (WhatsApp ready)
    - Specialized roles (Chef, Nutriólogo, Bartender, Barista, Ingeniero)
    
    Usage:
        # Simple usage (no persistence)
        bot = ChatbotV2()
        response = bot.chat("Busco aceite de oliva")
        
        # With session persistence (for WhatsApp)
        bot = ChatbotV2(session_id="+5255XXXXXXXX", use_persistence=True)
        response = bot.chat("Busco aceite de oliva")
    """
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        user_phone: Optional[str] = None,
        use_persistence: bool = False,
    ):
        """
        Initialize the chatbot.
        
        Args:
            session_id: Unique session identifier. If None, generates a UUID.
                       For WhatsApp, use the phone number.
            user_phone: Phone number of the user (for notifications)
            use_persistence: Whether to use PostgreSQL for session persistence
        """
        self.session_id = session_id or str(uuid.uuid4())
        self.user_phone = user_phone
        self.use_persistence = use_persistence
        
        # Initialize state
        self.state = create_initial_state(
            session_id=self.session_id,
            user_phone=user_phone
        )
        
        # Always use in-memory graph (no PostgreSQL checkpointer)
        # State is maintained in self.state and in the whatsapp_server _sessions dict
        # The PostgresSaver checkpointer was adding 15-25s of latency per request
        # due to serializing state to Heroku PostgreSQL after EVERY node execution
        self.graph = get_conversation_graph()
        logger.info(f"✅ ChatbotV2 initialized (session: {self.session_id[:8]}...)")
    
    def chat(self, message: str) -> str:
        """
        Process a user message and return the response.
        
        Args:
            message: The user's message
            
        Returns:
            The bot's response as a string
        """
        logger.info(f"💬 ══════════════════════════════════════════════════")
        logger.info(f"💬 USER MESSAGE: '{message[:80]}...'")
        logger.info(f"💬 Session: {self.session_id[:8]}... | Turn: {self.state.get('turn_number', 0)}")
        logger.info(f"💬 self.state search_filters={self.state.get('search_filters', 'MISSING')}, "
                    f"last_search_query={self.state.get('last_search_query', 'MISSING')}")
        
        # Add user message to state
        user_message = HumanMessage(content=message)
        
        # Prepare input state
        input_state = {
            **self.state,
            "messages": self.state.get("messages", []) + [user_message],
        }
        
        try:
            # Run the graph (no checkpointer — state lives in memory)
            config = {"configurable": {"thread_id": self.session_id}}
            
            result = self.graph.invoke(input_state, config)
            
            # Update internal state
            self.state = result
            
            # Debug: log critical state fields for troubleshooting
            logger.info(f"💾 STATE after invoke: search_filters={result.get('search_filters', 'MISSING')}, "
                       f"last_search_query={result.get('last_search_query', 'MISSING')}")
            logger.info(f"💾 STATE keys: {sorted(result.keys())}")
            
            # Get response
            response = result.get("response", "Lo siento, hubo un problema. ¿Puedes repetir?")
            
            logger.info(f"🤖 RESPONSE: '{response[:100]}...'")
            logger.info(f"💬 ══════════════════════════════════════════════════")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Chat error: {e}", exc_info=True)
            return "Lo siento, hubo un error procesando tu mensaje. ¿Puedes intentar de nuevo? 😊"
    
    def chat_with_metadata(self, message: str) -> Tuple[str, Dict[str, Any]]:
        """
        Process a user message and return response with metadata.
        
        Args:
            message: The user's message
            
        Returns:
            Tuple of (response, metadata dict)
        """
        response = self.chat(message)
        
        metadata = {
            "session_id": self.session_id,
            "turn_number": self.state.get("turn_number", 0),
            "intent": self.state.get("intent", ""),
            "nivel_relevancia": self.state.get("nivel_relevancia", ""),
            "is_difficult_user": self.state.get("is_difficult_user", False),
            "response_metadata": self.state.get("response_metadata", {}),
        }
        
        return response, metadata
    
    def get_history(self) -> List[Tuple[str, str]]:
        """
        Get the conversation history as a list of (role, content) tuples.
        
        Returns:
            List of (role, content) tuples
        """
        history = []
        messages = self.state.get("messages", [])
        
        for msg in messages:
            if isinstance(msg, HumanMessage):
                history.append(("user", msg.content))
            elif isinstance(msg, AIMessage):
                history.append(("assistant", msg.content))
            elif hasattr(msg, 'type') and hasattr(msg, 'content'):
                role = "user" if msg.type == "human" else "assistant"
                history.append((role, msg.content))
        
        return history
    
    def get_messages(self) -> List[BaseMessage]:
        """Get raw LangChain messages."""
        return self.state.get("messages", [])
    
    def reset(self):
        """Reset the conversation state."""
        logger.info(f"🔄 Resetting conversation for session: {self.session_id[:8]}...")
        self.state = create_initial_state(
            session_id=self.session_id,
            user_phone=self.user_phone
        )
    
    @property
    def turn_number(self) -> int:
        """Get the current turn number."""
        return self.state.get("turn_number", 0)
    
    @property
    def last_intent(self) -> str:
        """Get the last detected intent."""
        return self.state.get("intent", "")
    
    @property
    def last_search_results(self) -> Optional[Dict]:
        """Get the last search results."""
        return self.state.get("search_results")


# Convenience function for simple usage
def create_chatbot(
    session_id: Optional[str] = None,
    user_phone: Optional[str] = None,
    use_persistence: bool = False,
) -> ChatbotV2:
    """
    Create a new chatbot instance.
    
    Args:
        session_id: Unique session identifier (for WhatsApp: phone number)
        user_phone: Phone number for notifications
        use_persistence: Enable PostgreSQL persistence
        
    Returns:
        ChatbotV2 instance
    """
    return ChatbotV2(
        session_id=session_id,
        user_phone=user_phone,
        use_persistence=use_persistence,
    )


# Legacy compatibility: expose the main chat function
def chat(message: str, session_id: Optional[str] = None) -> str:
    """
    Simple chat function for backwards compatibility.
    
    Note: This creates a new chatbot for each call, so no conversation
    history is maintained. For persistent conversations, use ChatbotV2 directly.
    """
    bot = ChatbotV2(session_id=session_id)
    return bot.chat(message)
