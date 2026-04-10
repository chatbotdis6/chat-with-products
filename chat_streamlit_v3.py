"""
Streamlit demo — V3 Tool-Calling Agent.

Run: streamlit run chat_streamlit_v3.py
"""
import streamlit as st

from chat.agent.chatbot import ChatbotV3

st.set_page_config(page_title="Hap & D — Agent V3", page_icon="🤖")
st.title("🤖 The Hap & D Company — Agent V3")
st.caption("Tool-calling agent: el LLM decide qué herramienta usar")

# ── Session state ───────────────────────────────────────────────────
if "bot_v3" not in st.session_state:
    st.session_state.bot_v3 = ChatbotV3(session_id="streamlit-v3")
if "messages_v3" not in st.session_state:
    st.session_state.messages_v3 = []

# ── Sidebar ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("ℹ️ Info")
    st.write(f"**Turno:** {st.session_state.bot_v3.turn_number}")
    st.write(f"**Modelo:** gpt-4o (agent) + o3-mini (SQL)")
    st.write(f"**Arquitectura:** 2 nodos (agent → tools → agent)")
    st.divider()
    if st.button("🔄 Reiniciar conversación"):
        st.session_state.bot_v3.reset()
        st.session_state.messages_v3 = []
        st.rerun()

# ── Chat history ────────────────────────────────────────────────────
for msg in st.session_state.messages_v3:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── User input ──────────────────────────────────────────────────────
if prompt := st.chat_input("Escribe tu mensaje…"):
    # Show user message
    st.session_state.messages_v3.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Get bot response
    with st.chat_message("assistant"):
        with st.spinner("Pensando…"):
            response = st.session_state.bot_v3.chat(prompt)
        st.markdown(response)

    st.session_state.messages_v3.append({"role": "assistant", "content": response})
