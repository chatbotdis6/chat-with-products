"""
Batería de pruebas de integración — replica el flujo WhatsApp/Streamlit.

Usa LLM real + DB real. Requiere .env con credenciales.

Ejecutar:
    .venv/bin/python -m pytest test_battery.py -v -s --tb=short

Por bloque:
    .venv/bin/python -m pytest test_battery.py -v -s -k "bloque1"

Un solo test:
    .venv/bin/python -m pytest test_battery.py -v -s -k "test_saludo"
"""
import re
import pytest
from chat.agent.chatbot import Chatbot
from chat.config.settings import settings


# ── Helpers ─────────────────────────────────────────────────────────

def _new_bot() -> Chatbot:
    """Fresh bot for each test — equivalent to /reset."""
    return Chatbot(session_id="battery-test")


def _chat(bot: Chatbot, message: str) -> str:
    """Chat + apply WhatsApp formatting, same as whatsapp_server."""
    if bot.state.get("platform_exhausted", False):
        return (
            f"Ya te hemos derivado a nuestra Plataforma donde encontrarás "
            f"todo lo que necesitas:\n\n"
            f"👉 {settings.PLATFORM_URL}\n\n"
            f"Si necesitas ayuda adicional, escríbenos por ahí. ¡Gracias! 😊"
        )
    response = bot.chat(message)
    # Same markdown_to_whatsapp as whatsapp_server
    response = re.sub(r'\*\*(.+?)\*\*', r'*\1*', response)
    response = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', response)
    response = re.sub(r'^#{1,6}\s+', '', response, flags=re.MULTILINE)
    response = re.sub(r'^-{3,}$', '', response, flags=re.MULTILINE)
    response = re.sub(r'\n{3,}', '\n\n', response)
    return response.strip()


def _print_exchange(user: str, bot_response: str):
    print(f"\n  👤 {user}")
    print(f"  🤖 {bot_response[:300]}{'…' if len(bot_response) > 300 else ''}")


# ── BLOQUE 1 — Conversacional básico ────────────────────────────────

class TestBloque1Conversacional:
    """Saludos, preguntas sobre el servicio, confirmaciones, despedidas."""

    def test_b1_saludo(self):
        bot = _new_bot()
        r = _chat(bot, "Hola")
        _print_exchange("Hola", r)
        r_lower = r.lower()
        assert any(w in r_lower for w in ["hola", "bienvenid", "asistente", "ayud"]), \
            f"Se esperaba saludo/presentación, got: {r}"

    def test_b1_que_productos_manejas(self):
        bot = _new_bot()
        _chat(bot, "Hola")
        r = _chat(bot, "Qué productos manejas?")
        _print_exchange("Qué productos manejas?", r)
        r_lower = r.lower()
        # Must explain the service — NOT say "fuera del sector"
        assert "sector" not in r_lower or "gastronóm" in r_lower, \
            f"No debe decir 'fuera del sector', got: {r}"
        assert any(w in r_lower for w in ["proveedor", "insumo", "producto", "gastronóm", "aliment"]), \
            f"Debe explicar el servicio, got: {r}"

    def test_b1_confirmacion_sin_contexto(self):
        bot = _new_bot()
        _chat(bot, "Hola")
        _chat(bot, "Qué productos manejas?")
        r = _chat(bot, "Sí por favor")
        _print_exchange("Sí por favor", r)
        r_lower = r.lower()
        # Must ask what product, NOT repeat the greeting
        assert "hola" not in r_lower or "product" in r_lower, \
            f"No debe repetir saludo sin contexto, got: {r}"
        assert any(w in r_lower for w in ["product", "busca", "qué", "cuál", "ayud"]), \
            f"Debe pedir especificar producto, got: {r}"

    def test_b1_despedida(self):
        bot = _new_bot()
        _chat(bot, "Hola")
        r = _chat(bot, "Gracias")
        _print_exchange("Gracias", r)
        r_lower = r.lower()
        assert any(w in r_lower for w in ["graci", "placer", "hasta", "suerte", "ayud", "dispon"]), \
            f"Se esperaba despedida cordial, got: {r}"


# ── BLOQUE 2 — Búsqueda + filtro + precio + más + detalle ───────────

class TestBloque2BusquedaCompleta:
    """Flujo completo: buscar → filtrar marca → precios → más → detalle."""

    def test_b2_buscar_aceite_oliva(self):
        bot = _new_bot()
        r = _chat(bot, "Busco aceite de oliva")
        _print_exchange("Busco aceite de oliva", r)
        r_lower = r.lower()
        assert "aceite" in r_lower, f"Debe mostrar resultados de aceite, got: {r}"
        assert any(w in r_lower for w in ["proveedor", "marca", "carbonell", "carapelli", "filippo"]), \
            f"Debe mostrar marcas/proveedores, got: {r}"
        # Store bot for chained tests
        self.__class__._bot = bot

    def test_b2_filtrar_marca_carbonell(self):
        if not hasattr(self.__class__, "_bot"):
            pytest.skip("Requires test_b2_buscar_aceite_oliva to run first")
        bot = self.__class__._bot
        r = _chat(bot, "De la marca Carbonell")
        _print_exchange("De la marca Carbonell", r)
        r_lower = r.lower()
        # Must NOT say "producto no registrado"
        assert "no registrado" not in r_lower, \
            f"No debe decir 'producto no registrado' para Carbonell, got: {r}"
        assert "carbonell" in r_lower or "proveedor" in r_lower, \
            f"Debe filtrar por Carbonell, got: {r}"

    def test_b2_precios_aceite_carbonell(self):
        if not hasattr(self.__class__, "_bot"):
            pytest.skip("Requires previous tests to run first")
        bot = self.__class__._bot
        r = _chat(bot, "A qué precios?")
        _print_exchange("A qué precios?", r)
        r_lower = r.lower()
        assert any(w in r_lower for w in ["precio", "$", "mxn", "costo", "pesos"]), \
            f"Debe mostrar precios, got: {r}"

    def test_b2_mostrar_mas_proveedores(self):
        if not hasattr(self.__class__, "_bot"):
            pytest.skip("Requires previous tests to run first")
        bot = self.__class__._bot
        r = _chat(bot, "Quiero ver más proveedores")
        _print_exchange("Quiero ver más proveedores", r)
        r_lower = r.lower()
        # Must either show more OR clearly say there are no more
        assert any(w in r_lower for w in ["proveedor", "más", "adicional", "no hay más", "todos"]), \
            f"Debe responder sobre más proveedores, got: {r}"

    def test_b2_detalle_proveedor(self):
        if not hasattr(self.__class__, "_bot"):
            pytest.skip("Requires previous tests to run first")
        bot = self.__class__._bot
        r = _chat(bot, "Dame el detalle del primero")
        _print_exchange("Dame el detalle del primero", r)
        r_lower = r.lower()
        assert any(w in r_lower for w in ["contacto", "whatsapp", "teléfono", "web", "ejecutivo",
                                           "descripción", "proveedor", "ventas"]), \
            f"Debe mostrar datos de contacto del proveedor, got: {r}"


# ── BLOQUE 3 — Producto no registrado ───────────────────────────────

class TestBloque3ProductoNoRegistrado:
    """Producto que no existe en la BD."""

    def test_b3_producto_inexistente(self):
        bot = _new_bot()
        r = _chat(bot, "Busco caviar beluga")
        _print_exchange("Busco caviar beluga", r)
        r_lower = r.lower()
        assert any(w in r_lower for w in ["no", "encontr", "registr", "tenemos", "hora", "aviso", "notific"]), \
            f"Debe informar que no tiene el producto, got: {r}"
        self.__class__._bot = bot

    def test_b3_confirmacion_aviso(self):
        if not hasattr(self.__class__, "_bot"):
            pytest.skip("Requires test_b3_producto_inexistente to run first")
        bot = self.__class__._bot
        r = _chat(bot, "Sí, avísame")
        _print_exchange("Sí, avísame", r)
        r_lower = r.lower()
        # Must NOT search "sí" as a product
        assert "proveedor" not in r_lower or "aviso" in r_lower or "whatsapp" in r_lower or "avis" in r_lower, \
            f"No debe buscar 'sí' como producto, got: {r}"
        assert any(w in r_lower for w in ["avis", "notific", "contac", "pronto", "equipo", "enviado"]), \
            f"Debe confirmar el aviso, got: {r}"


# ── BLOQUE 4 — Especialistas ─────────────────────────────────────────

class TestBloque4Especialistas:
    """Cada especialista responde a su dominio."""

    def test_b4_chef_bechamel(self):
        bot = _new_bot()
        r = _chat(bot, "¿Cómo hago una salsa bechamel?")
        _print_exchange("¿Cómo hago una salsa bechamel?", r)
        r_lower = r.lower()
        assert any(w in r_lower for w in ["mantequilla", "harina", "leche", "bechamel", "mezcl", "cocin"]), \
            f"Chef debe dar receta de bechamel, got: {r}"

    def test_b4_nutri_calorias_aceite(self):
        bot = _new_bot()
        r = _chat(bot, "¿Cuántas calorías tiene el aceite de oliva?")
        _print_exchange("¿Cuántas calorías tiene el aceite de oliva?", r)
        r_lower = r.lower()
        assert any(w in r_lower for w in ["caloría", "kcal", "gramo", "grasa", "energía"]), \
            f"Nutriólogo debe dar info calórica, got: {r}"

    def test_b4_bartender_mojito(self):
        bot = _new_bot()
        r = _chat(bot, "¿Cómo preparo un mojito?")
        _print_exchange("¿Cómo preparo un mojito?", r)
        r_lower = r.lower()
        assert any(w in r_lower for w in ["ron", "menta", "limón", "azúcar", "hielo", "mojito"]), \
            f"Bartender debe dar receta de mojito, got: {r}"

    def test_b4_barista_cafe_especialidad(self):
        bot = _new_bot()
        r = _chat(bot, "¿Cuál es el mejor método para preparar café de especialidad?")
        _print_exchange("¿Cuál es el mejor método para preparar café de especialidad?", r)
        r_lower = r.lower()
        assert any(w in r_lower for w in ["café", "extracción", "método", "temperatura", "molido",
                                           "prensa", "filtro", "espresso", "pour"]), \
            f"Barista debe hablar de métodos de café, got: {r}"

    def test_b4_ingeniero_conservacion_carne(self):
        bot = _new_bot()
        r = _chat(bot, "¿Cómo conservo la carne fresca más tiempo?")
        _print_exchange("¿Cómo conservo la carne fresca más tiempo?", r)
        r_lower = r.lower()
        assert any(w in r_lower for w in ["temperatura", "refriger", "°c", "frío", "conserv",
                                           "cadena", "envas", "higien"]), \
            f"Ingeniero debe hablar de conservación, got: {r}"


# ── BLOQUE 5 — Derivación a plataforma ──────────────────────────────

class TestBloque5Plataforma:
    """Las sugerencias de plataforma aparecen en los turnos correctos."""

    def test_b5_turno0_sin_sugerencia(self):
        bot = _new_bot()
        r = _chat(bot, "Busco harina")
        _print_exchange("Busco harina [turno 0]", r)
        assert settings.PLATFORM_URL not in r, \
            f"Turno 0 NO debe incluir URL de plataforma, got: {r}"

    def test_b5_turno2_sugerencia_suave(self):
        bot = _new_bot()
        _chat(bot, "Busco harina")           # turno 0
        _chat(bot, "Busco azúcar")           # turno 1
        r = _chat(bot, "Busco mantequilla")  # turno 2 → sugerencia suave
        _print_exchange("Busco mantequilla [turno 2 — sugerencia suave]", r)
        assert settings.PLATFORM_URL in r, \
            f"Turno {settings.CONSULTAS_ANTES_SUGERENCIA} debe incluir URL de plataforma, got: {r}"

    def test_b5_turno4_derivacion_firme(self):
        bot = _new_bot()
        _chat(bot, "Busco harina")           # turno 0
        _chat(bot, "Busco azúcar")           # turno 1
        _chat(bot, "Busco mantequilla")      # turno 2
        _chat(bot, "Busco leche")            # turno 3
        r = _chat(bot, "Busco café")         # turno 4 → derivación firme
        _print_exchange("Busco café [turno 4 — derivación firme]", r)
        assert settings.PLATFORM_URL in r, \
            f"Turno {settings.CONSULTAS_ANTES_DERIVACION} debe incluir URL de plataforma, got: {r}"

    def test_b5_turno5_plantilla_fija(self):
        bot = _new_bot()
        _chat(bot, "Busco harina")           # turno 0
        _chat(bot, "Busco azúcar")           # turno 1
        _chat(bot, "Busco mantequilla")      # turno 2
        _chat(bot, "Busco leche")            # turno 3
        _chat(bot, "Busco café")             # turno 4
        r = _chat(bot, "Busco aceite")       # turno 5 → plantilla fija sin LLM
        _print_exchange("Busco aceite [turno 5 — plantilla fija]", r)
        assert bot.state.get("platform_exhausted", False), \
            "platform_exhausted debe ser True en turno 5+"
        assert settings.PLATFORM_URL in r, \
            f"Turno {settings.CONSULTAS_ANTES_PLANTILLA} debe tener URL en plantilla, got: {r}"

    def test_b5_turno6_sin_llm(self):
        """Turno 6+ usa el check de platform_exhausted — 0 tokens."""
        bot = _new_bot()
        for msg in ["Busco harina", "Busco azúcar", "Busco mantequilla",
                    "Busco leche", "Busco café", "Busco aceite"]:
            _chat(bot, msg)
        assert bot.state.get("platform_exhausted", False), \
            "platform_exhausted debe ser True"
        r = _chat(bot, "Busco queso")        # turno 6 → no llama LLM
        _print_exchange("Busco queso [turno 6 — sin LLM]", r)
        assert settings.PLATFORM_URL in r, \
            f"Turno 6+ debe usar mensaje fijo con URL, got: {r}"


# ── BLOQUE 6 — Usuario difícil ───────────────────────────────────────

class TestBloque6UsuarioDificil:
    """Manejo de usuarios problemáticos."""

    def test_b6_insulto(self):
        bot = _new_bot()
        r = _chat(bot, "Esto es una mierda de servicio")
        _print_exchange("Esto es una mierda de servicio", r)
        r_lower = r.lower()
        # Should NOT crash, should be empathetic
        assert len(r) > 10, "Debe responder algo"
        assert any(w in r_lower for w in ["entend", "sentim", "lament", "ayud",
                                           "mejorar", "queja", "atend", "disculp"]), \
            f"Debe responder con empatía, got: {r}"

    def test_b6_inutil(self):
        bot = _new_bot()
        r = _chat(bot, "Eres un inútil")
        _print_exchange("Eres un inútil", r)
        assert len(r) > 10, "Debe responder algo"
        r_lower = r.lower()
        assert any(w in r_lower for w in ["entend", "sentim", "lament", "ayud",
                                           "mejorar", "disculp", "atend"]), \
            f"Debe responder con calma/empatía, got: {r}"

    def test_b6_quiere_humano(self):
        bot = _new_bot()
        r = _chat(bot, "Quiero hablar con un humano")
        _print_exchange("Quiero hablar con un humano", r)
        r_lower = r.lower()
        assert any(w in r_lower for w in ["equipo", "atend", "contact", "whatsapp",
                                           "human", "person", "ayud", "soport"]), \
            f"Debe ofrecer alternativa de atención, got: {r}"


# ── BLOQUE 7 — Edge cases ────────────────────────────────────────────

class TestBloque7EdgeCases:
    """Casos borde para robustez."""

    def test_b7_mensaje_muy_largo(self):
        bot = _new_bot()
        msg = "Busco aceite de oliva extra virgen de primera prensada " * 10
        r = _chat(bot, msg)
        _print_exchange(f"[{len(msg)} chars]", r)
        assert len(r) > 10, "Debe procesar mensajes largos sin crash"

    def test_b7_emoji_solo(self):
        bot = _new_bot()
        r = _chat(bot, "👍")
        _print_exchange("👍", r)
        assert len(r) > 10, "Debe responder coherentemente a emoji"

    def test_b7_numero_suelto(self):
        bot = _new_bot()
        r = _chat(bot, "3")
        _print_exchange("3", r)
        assert len(r) > 10, "Debe responder coherentemente a número suelto"

    def test_b7_producto_generico(self):
        bot = _new_bot()
        r = _chat(bot, "Busco algo")
        _print_exchange("Busco algo", r)
        r_lower = r.lower()
        assert any(w in r_lower for w in ["especif", "qué", "cuál", "product",
                                           "busca", "qué tipo", "ayud"]), \
            f"Debe pedir especificar, got: {r}"
