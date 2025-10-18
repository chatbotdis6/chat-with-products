# chat_streamlit.py
import streamlit as st
from typing import Any, Tuple
import json

# Importa el grafo, prompts y funciones multi-agente del archivo chatbot.py
from chatbot import (
    app, SYSTEM_PROMPT, BUZON_QUEJAS,
    detectar_intencion, responder_como_chef, responder_como_nutriologo,
    responder_como_bartender, responder_como_barista, responder_como_ingeniero,
    responder_fuera_alcance
)


# -------------------------------
# Helpers para roles y contenido
# -------------------------------
def _role_and_content(msg: Any) -> Tuple[str, str]:
    """
    Adapta distintos tipos de mensajes (tuplas ('role', 'content') o
    LangChain Messages) a ('user'|'assistant'|'system'|'tool', content).
    """
    # Caso 1: tupla simple
    if isinstance(msg, tuple) and len(msg) == 2:
        role, content = msg
        if role == "ai":
            role = "assistant"
        elif role == "human":
            role = "user"
        return role, str(content)

    # Caso 2: mensajes tipo LangChain
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
    Invierte el lado visual:
      - user (tú)  -> izquierda  (usamos 'assistant' para que Streamlit lo ponga a la izq)
      - assistant  -> derecha    (usamos 'user' para que Streamlit lo ponga a la dcha)
    Devolvemos (display_role, avatar).
    """
    if original_role == "user":
        return "assistant", "🧑‍💻"  # tú, a la izquierda
    if original_role == "assistant":
        return "user", "🤖"        # IA, a la derecha
    if original_role == "tool":
        return "assistant", "🛠️"   # opcional: mostrar herramientas a la izq
    return original_role, "ℹ️"      # system u otros (normalmente ocultos)


def _init_session_state():
    if "history" not in st.session_state:
        st.session_state.history = [("system", SYSTEM_PROMPT)]
    if "last_response" not in st.session_state:
        st.session_state.last_response = ""


def _procesar_mensaje_multi_agente(user_text: str, history: list) -> Tuple[str, list]:
    """
    Procesa el mensaje del usuario usando el sistema multi-agente.
    Retorna: (respuesta, nuevo_historial)
    """
    # PASO 1: Detectar intención del usuario
    intencion = detectar_intencion(user_text)
    
    # Mostrar en sidebar qué agente se activó
    agente_icons = {
        "busqueda_proveedores": "🔍 Búsqueda de Proveedores",
        "chef": "👨‍🍳 Chef",
        "nutriologo": "🥗 Nutriólogo", 
        "bartender": "🍹 Bartender",
        "barista": "☕ Barista",
        "ingeniero_alimentos": "🔬 Ingeniero en Alimentos",
        "fuera_alcance": "⚠️ Fuera de Alcance"
    }
    
    with st.sidebar:
        st.info(f"**Agente activo:** {agente_icons.get(intencion, intencion)}")
    
    # PASO 2: Rutear según la intención detectada
    if intencion == "busqueda_proveedores":
        # Flujo normal con tools (búsqueda de proveedores)
        history.append(("user", user_text))
        out = app.invoke({"messages": history})
        respuesta_content = out["messages"][-1].content
        return respuesta_content, out["messages"]
        
    elif intencion == "chef":
        # Agente Chef
        respuesta, nuevo_history = responder_como_chef(user_text, history)
        return respuesta, nuevo_history
        
    elif intencion == "nutriologo":
        # Agente Nutriólogo
        respuesta, nuevo_history = responder_como_nutriologo(user_text, history)
        return respuesta, nuevo_history
        
    elif intencion == "bartender":
        # Agente Bartender
        respuesta, nuevo_history = responder_como_bartender(user_text, history)
        return respuesta, nuevo_history
        
    elif intencion == "barista":
        # Agente Barista
        respuesta, nuevo_history = responder_como_barista(user_text, history)
        return respuesta, nuevo_history
        
    elif intencion == "ingeniero_alimentos":
        # Agente Ingeniero en Alimentos
        respuesta, nuevo_history = responder_como_ingeniero(user_text, history)
        return respuesta, nuevo_history
        
    elif intencion == "fuera_alcance":
        # Respuesta para temas fuera del sector gastronómico
        respuesta, nuevo_history = responder_fuera_alcance(user_text, history)
        return respuesta, nuevo_history
        
    else:
        # Fallback si el router devuelve algo inesperado
        respuesta = "Disculpa, no entendí tu consulta. ¿Puedes reformularla? 😊"
        nuevo_history = history + [
            ("user", user_text),
            ("assistant", respuesta)
        ]
        return respuesta, nuevo_history


# -------------------------------
# UI
# -------------------------------
st.set_page_config(
    page_title="The Hap & D Company - Chat Multi-Agente",
    page_icon="🛒",
)

st.title("🛒 The Hap & D Company — Chat Multi-Agente")
st.caption("Busca proveedores, recetas, información nutricional, cócteles, técnicas de café y consejos de conservación.")

# Sidebar con información de agentes
with st.sidebar:
    st.header("🎭 Agentes Disponibles")
    st.markdown("""
    **🔍 Búsqueda de Proveedores**
    - Buscar productos y proveedores
    - Información de contacto
    - Comparar opciones
    
    **👨‍🍳 Chef**
    - Recetas paso a paso
    - Técnicas de cocina
    - Ideas de preparación
    
    **🥗 Nutriólogo**
    - Información nutricional
    - Calorías y macros
    - Beneficios de alimentos
    
    **🍹 Bartender**
    - Recetas de cócteles
    - Maridajes
    - Técnicas de mixología
    
    **☕ Barista**
    - Métodos de preparación de café
    - Técnicas de extracción
    - Tips profesionales
    
    **🔬 Ingeniero en Alimentos**
    - Conservación y almacenamiento
    - Vida útil de productos
    - Inocuidad alimentaria
    """)
    
    st.divider()
    st.caption(f"📧 Buzón de quejas: {BUZON_QUEJAS}")

col1, col2 = st.columns([1, 1])
with col1:
    if st.button("🧹 Reiniciar conversación"):
        st.session_state.clear()
        _init_session_state()
        st.rerun()
with col2:
    st.write("")

_init_session_state()

# Render del historial (ocultando el system prompt)
for msg in st.session_state.history:
    role, content = _role_and_content(msg)
    if role == "system":
        continue
    # Si no quieres mostrar mensajes de herramientas, descomenta:
    # if role == "tool":
    #     continue

    display_role, avatar = _render_role_swap(role)
    with st.chat_message(display_role, avatar=avatar):
        st.markdown(content)

# Entrada del usuario
user_text = st.chat_input("Escribe tu mensaje… (ej: 'busco mantequilla', 'receta de fresas Dubai', '¿calorías del aguacate?')")
if user_text:
    # 1) Mostrar inmediatamente TU mensaje (lado izquierdo)
    display_role, avatar = _render_role_swap("user")
    with st.chat_message(display_role, avatar=avatar):
        st.markdown(user_text)

    # 2) Procesar con sistema multi-agente
    with st.spinner("🤖 Procesando con IA..."):
        try:
            respuesta, nuevo_historial = _procesar_mensaje_multi_agente(
                user_text, 
                st.session_state.history.copy()
            )
            
            # 3) Actualizar historial
            st.session_state.history = nuevo_historial
            
            # 4) Renderizar la respuesta de la IA (lado derecho)
            display_role, avatar = _render_role_swap("assistant")
            with st.chat_message(display_role, avatar=avatar):
                st.markdown(respuesta)
                
        except Exception as e:
            st.error(f"Error al procesar mensaje: {str(e)}")
            # Agregar mensaje de error al historial
            error_msg = "Disculpa, hubo un error procesando tu mensaje. ¿Puedes intentar de nuevo? 😊"
            st.session_state.history.extend([
                ("user", user_text),
                ("assistant", error_msg)
            ])
            
            display_role, avatar = _render_role_swap("assistant")
            with st.chat_message(display_role, avatar=avatar):
                st.markdown(error_msg)
