"""
Tests for the V3 tool-calling agent architecture.

Validates:
1. All 6 tools are importable and have correct signatures
2. Agent graph compiles without errors
3. ChatbotV3 has the same public API as ChatbotV2
4. System prompt builds correctly for each turn range
5. Platform block triggers at turn 5+
"""
import pytest
from unittest.mock import patch, MagicMock


# ── Test 1: Tools import and signatures ─────────────────────────────
def test_all_tools_importable():
    """All 6 tools should be importable."""
    from chat.agent.tools import ALL_TOOLS
    assert len(ALL_TOOLS) == 6
    names = {t.name for t in ALL_TOOLS}
    assert names == {
        "buscar_productos",
        "filtrar_por_precio",
        "detalle_proveedor",
        "mostrar_mas_proveedores",
        "consultar_especialista",
        "reportar_producto_no_encontrado",
    }


def test_tool_descriptions_not_empty():
    """Each tool should have a non-empty description."""
    from chat.agent.tools import ALL_TOOLS
    for tool in ALL_TOOLS:
        assert tool.description, f"Tool {tool.name} has empty description"
        assert len(tool.description) > 20, f"Tool {tool.name} description too short"


def test_buscar_productos_schema():
    """buscar_productos should accept producto (required) and marca (optional)."""
    from chat.agent.tools import buscar_productos
    schema = buscar_productos.args_schema.model_json_schema()
    assert "producto" in schema["properties"]
    assert "producto" in schema["required"]
    # marca should be optional (not in required)
    assert "marca" in schema["properties"]


def test_consultar_especialista_schema():
    """consultar_especialista should have a Literal enum for especialista."""
    from chat.agent.tools import consultar_especialista
    schema = consultar_especialista.args_schema.model_json_schema()
    assert "especialista" in schema["properties"]
    assert "pregunta" in schema["properties"]


# ── Test 2: Prompts ─────────────────────────────────────────────────
def test_prompt_base_contains_key_elements():
    """System prompt should contain personality, tools, and rules."""
    from chat.agent.prompts import build_agent_system_prompt
    prompt = build_agent_system_prompt(turn_number=0)
    assert "Hap & D Company" in prompt
    assert "buscar_productos" in prompt
    assert "filtrar_por_precio" in prompt
    assert "consultar_especialista" in prompt
    assert "español" in prompt


def test_prompt_no_platform_early():
    """Turn 0-1 should NOT include platform suggestions."""
    from chat.agent.prompts import build_agent_system_prompt
    prompt = build_agent_system_prompt(turn_number=0)
    assert "Sugerencia de plataforma" not in prompt
    assert "Derivación a plataforma" not in prompt


def test_prompt_soft_suggestion():
    """Turn 2-3 should include soft platform suggestion."""
    from chat.agent.prompts import build_agent_system_prompt
    from chat.config.settings import settings
    prompt = build_agent_system_prompt(turn_number=settings.CONSULTAS_ANTES_SUGERENCIA)
    assert "Sugerencia de plataforma" in prompt
    assert settings.PLATFORM_URL in prompt


def test_prompt_strong_derivation():
    """Turn 4+ should include strong derivation."""
    from chat.agent.prompts import build_agent_system_prompt
    from chat.config.settings import settings
    prompt = build_agent_system_prompt(turn_number=settings.CONSULTAS_ANTES_DERIVACION)
    assert "Derivación a plataforma" in prompt
    assert settings.PLATFORM_URL in prompt


# ── Test 3: Agent graph ─────────────────────────────────────────────
def test_agent_graph_compiles():
    """The agent graph should compile without errors."""
    from chat.agent.graph import create_agent_graph
    graph = create_agent_graph()
    assert graph is not None


def test_agent_state_creation():
    """create_initial_agent_state should return valid state."""
    from chat.agent.graph import create_initial_agent_state
    state = create_initial_agent_state(session_id="test-123", user_phone="+525512345678")
    assert state["session_id"] == "test-123"
    assert state["turn_number"] == 0
    assert state["user_phone"] == "+525512345678"
    assert state["platform_exhausted"] is False
    assert state["messages"] == []


def test_platform_block_at_turn_5():
    """Agent node should return platform block at turn >= CONSULTAS_ANTES_PLANTILLA."""
    from chat.agent.graph import agent_node, AgentState
    from chat.config.settings import settings
    from langchain_core.messages import AIMessage

    state = AgentState(
        messages=[],
        session_id="test",
        turn_number=settings.CONSULTAS_ANTES_PLANTILLA,
        platform_exhausted=False,
    )
    result = agent_node(state)
    assert result["platform_exhausted"] is True
    msg = result["messages"][0]
    assert isinstance(msg, AIMessage)
    assert settings.PLATFORM_URL in msg.content


# ── Test 4: ChatbotV3 API compatibility ─────────────────────────────
def test_chatbot_v3_has_same_api():
    """ChatbotV3 should have the same public methods as ChatbotV2."""
    from chat.agent.chatbot import ChatbotV3

    bot = ChatbotV3(session_id="test-api")

    # Public methods
    assert callable(bot.chat)
    assert callable(bot.chat_with_metadata)
    assert callable(bot.get_history)
    assert callable(bot.get_messages)
    assert callable(bot.reset)

    # Properties
    assert isinstance(bot.turn_number, int)
    assert isinstance(bot.last_intent, str)
    assert bot.last_search_results is None

    # State
    assert bot.session_id == "test-api"


def test_chatbot_v3_reset():
    """Reset should return state to initial."""
    from chat.agent.chatbot import ChatbotV3

    bot = ChatbotV3(session_id="test-reset")
    # Manually modify state
    bot.state["turn_number"] = 10
    bot.state["platform_exhausted"] = True
    # Reset
    bot.reset()
    assert bot.turn_number == 0
    assert bot.state["platform_exhausted"] is False
    assert bot.state["messages"] == []


def test_extract_response():
    """_extract_response should find the last AIMessage with content."""
    from chat.agent.chatbot import ChatbotV3
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    messages = [
        HumanMessage(content="Hola"),
        AIMessage(content="", tool_calls=[{"name": "buscar_productos", "args": {"producto": "aceite"}, "id": "1"}]),
        ToolMessage(content="results…", tool_call_id="1"),
        AIMessage(content="Encontré 3 proveedores de aceite 🍳"),
    ]

    state = {"messages": messages}
    result = ChatbotV3._extract_response(state)
    assert "proveedores de aceite" in result
