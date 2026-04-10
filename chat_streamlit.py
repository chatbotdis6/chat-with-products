"""
Streamlit demo for the chatbot.

Run: streamlit run chat_streamlit.py
"""
import streamlit as st

from chat.agent.chatbot import Chatbot

st.set_page_config(page_title="Hap & D — Chat", page_icon="🤖")
st.title("🤖 The Hap & D Company")
st.caption("Asistente de búsqueda de proveedores gastronómicos")

# ── Session state ───────────────────────────────────────────────────
if "bot" not in st.session_state:
    st.session_state.bot = Chatbot(session_id="streamlit")
if "messages" not in st.session_state:
    st.session_state.messages = []

# ── Sidebar ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("ℹ️ Info")
    st.write(f"**Turno:** {st.session_state.bot.turn_number}")
    st.divider()
    if st.button("🔄 Reiniciar conversación"):
        st.session_state.bot.reset()
        st.session_state.messages = []
        st.rerun()

# ── Chat history ────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── User input ──────────────────────────────────────────────────────
if prompt := st.chat_input("Escribe tu mensaje…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Pensando…"):
            response = st.session_state.bot.chat(prompt)
        st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})
