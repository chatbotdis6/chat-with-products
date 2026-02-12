# chat_streamlit_v2.py
"""
Streamlit chat interface using the new LangGraph-based chatbot.

This interface provides:
- Visual chat interface with message bubbles
- Session persistence simulation for WhatsApp testing
- Debug information in sidebar
"""
import streamlit as st
from typing import Any, Tuple
import json

# Import the new LangGraph-based chatbot
from chat.chatbot_v2 import ChatbotV2, create_chatbot
from chat.config.settings import settings


# -------------------------------
# Helpers for roles and content
# -------------------------------
def _role_and_content(msg: Any) -> Tuple[str, str]:
    """
    Adapts different message types to ('user'|'assistant', content).
    """
    # Case 1: simple tuple
    if isinstance(msg, tuple) and len(msg) == 2:
        role, content = msg
        if role == "ai":
            role = "assistant"
        elif role == "human":
            role = "user"
        return role, str(content)

    # Case 2: LangChain messages
    role = getattr(msg, "type", None) or getattr(msg, "role", None) or "assistant"
    content = getattr(msg, "content", "")

    mapping = {"ai": "assistant", "human": "user"}
    role = mapping.get(role, role)

    if not isinstance(content, str):
        try:
            content = json.dumps(content, ensure_ascii=False, indent=2)
        except Exception:
            content = str(content)

    return role, content


def _render_role_swap(original_role: str) -> Tuple[str, str]:
    """
    Swap visual sides for chat bubbles:
      - user -> left (we use 'assistant' for Streamlit)
      - assistant -> right (we use 'user' for Streamlit)
    """
    if original_role == "user":
        return "assistant", "🧑‍💻"
    if original_role == "assistant":
        return "user", "🤖"
    return original_role, "ℹ️"


def _init_session_state():
    """Initialize Streamlit session state."""
    if "chatbot" not in st.session_state:
        # Create chatbot with a unique session ID
        import uuid
        session_id = str(uuid.uuid4())[:8]
        st.session_state.chatbot = create_chatbot(
            session_id=session_id,
            use_persistence=False,  # Set to True for PostgreSQL persistence
        )
        st.session_state.session_id = session_id
    
    if "display_history" not in st.session_state:
        st.session_state.display_history = []


# -------------------------------
# UI Configuration
# -------------------------------
st.set_page_config(
    page_title="The Hap & D Company - Chat V2 (LangGraph)",
    page_icon="🛒",
)

st.title("🛒 The Hap & D Company — Chat V2")
st.caption("Arquitectura LangGraph con Text-to-SQL y agentes especializados.")

# Sidebar with agent information
with st.sidebar:
    st.header("🎭 Agentes Disponibles")
    st.markdown("""
    **🔍 Búsqueda de Proveedores**
    - Buscar productos y proveedores
    - Información de contacto
    - Comparar opciones
    
    **👨‍🍳 Chef** - Recetas y técnicas
    
    **🥗 Nutriólogo** - Info nutricional
    
    **🍹 Bartender** - Cócteles y bebidas
    
    **☕ Barista** - Técnicas de café
    
    **🔬 Ing. Alimentos** - Conservación
    """)
    
    st.divider()
    st.caption(f"📧 Buzón de quejas: {settings.BUZON_QUEJAS}")
    
    # Show session info
    if "chatbot" in st.session_state:
        chatbot = st.session_state.chatbot
        st.divider()
        st.subheader("📊 Estado de la Sesión")
        st.caption(f"🆔 Session: {st.session_state.session_id}")
        st.caption(f"💬 Turno: {chatbot.turn_number}")
        
        if chatbot.last_intent:
            intent_icons = {
                "busqueda_proveedores": "🔍",
                "chef": "👨‍🍳",
                "nutriologo": "🥗",
                "bartender": "🍹",
                "barista": "☕",
                "ingeniero_alimentos": "🔬",
                "saludo": "👋",
                "despedida": "👋",
                "fuera_alcance": "⚠️"
            }
            icon = intent_icons.get(chatbot.last_intent, "❓")
            st.info(f"{icon} Última intención: **{chatbot.last_intent}**")
        
        if chatbot.state.get("nivel_relevancia"):
            relevancia = chatbot.state.get("nivel_relevancia")
            color = {"alta": "🟢", "media": "🟡", "nula": "🔴"}.get(relevancia, "⚪")
            st.caption(f"{color} Relevancia: {relevancia}")

# Reset button
col1, col2 = st.columns([1, 1])
with col1:
    if st.button("🧹 Reiniciar conversación"):
        st.session_state.clear()
        _init_session_state()
        st.rerun()
with col2:
    st.write("")

_init_session_state()

# Render chat history
for role, content in st.session_state.display_history:
    display_role, avatar = _render_role_swap(role)
    with st.chat_message(display_role, avatar=avatar):
        st.markdown(content)

# User input
user_text = st.chat_input(
    "Escribe tu mensaje… (ej: 'busco mantequilla', 'receta de fresas Dubai', '¿calorías del aguacate?')"
)

if user_text:
    # 1) Show user message immediately
    display_role, avatar = _render_role_swap("user")
    with st.chat_message(display_role, avatar=avatar):
        st.markdown(user_text)
    
    # Add to display history
    st.session_state.display_history.append(("user", user_text))
    
    # 2) Process with LangGraph chatbot
    with st.spinner("🤖 Procesando con IA..."):
        try:
            chatbot = st.session_state.chatbot
            response, metadata = chatbot.chat_with_metadata(user_text)
            
            # 3) Render bot response
            display_role, avatar = _render_role_swap("assistant")
            with st.chat_message(display_role, avatar=avatar):
                st.markdown(response)
            
            # Add to display history
            st.session_state.display_history.append(("assistant", response))
            
            # Update sidebar (force rerun to update)
            st.rerun()
            
        except Exception as e:
            st.error(f"Error al procesar mensaje: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
            
            error_msg = "Disculpa, hubo un error procesando tu mensaje. ¿Puedes intentar de nuevo? 😊"
            st.session_state.display_history.append(("assistant", error_msg))
            
            display_role, avatar = _render_role_swap("assistant")
            with st.chat_message(display_role, avatar=avatar):
                st.markdown(error_msg)
