"""
Agent Tools — wrappers over existing query/specialist/unregistered logic.

Each tool is a LangChain @tool that the agent LLM can choose to call.
"""
import logging
import re
from typing import Optional, Literal

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from chat.config.settings import settings
from chat.services.data_transformer import DataTransformer
from chat.services.whatsapp_formatter import WhatsAppFormatter
from chat.services.email_service import email_service
from chat.graph.state import RelevanciaLevel, SearchResults, ProveedorResult
from chat.graph.nodes.query import QueryNode

logger = logging.getLogger(__name__)

# ── Shared singleton ────────────────────────────────────────────────
_qn = QueryNode()
_transformer = DataTransformer()

# ── Relevance threshold (same as query.py) ──────────────────────────
_RELEVANCE_THRESHOLD = 0.55


# ─────────────────────────────────────────────────────────────────────
# Tool 1 – Product / provider search
# ─────────────────────────────────────────────────────────────────────
@tool
def buscar_productos(
    producto: str,
    marca: Optional[str] = None,
) -> str:
    """Busca productos y proveedores en la base de datos gastronómica.

    Usa esta herramienta cuando el usuario busca un producto, ingrediente
    o proveedor. Por ejemplo: "busco aceite de oliva", "queso panela",
    "proveedores de café".

    Args:
        producto: Nombre del producto a buscar (ej: "aceite de oliva").
        marca: Marca específica si el usuario la menciona (ej: "Capullo").
    """
    logger.info(f"🔧 TOOL buscar_productos: producto='{producto}', marca={marca}")

    # 1) Intentar Text-to-SQL
    entities = {"producto": producto}
    if marca:
        entities["marca"] = marca

    rows = []
    used_llm_sql = False

    result = _qn._generate_sql_with_llm(producto, entities)
    if result:
        sql, params = result
        rows = _qn._execute_llm_sql(sql, params)
        if rows:
            rows = [r for r in rows if hasattr(r, "score") and float(r.score) >= _RELEVANCE_THRESHOLD]
            if rows:
                used_llm_sql = True

    # 2) Fallback: hybrid search
    if not rows:
        rows = _qn._execute_hybrid_search(search_query=producto, marca=marca)
        if rows:
            rows = [r for r in rows if hasattr(r, "score") and float(r.score) >= _RELEVANCE_THRESHOLD]
        # If no results with brand filter, retry without
        if not rows and marca:
            rows = _qn._execute_hybrid_search(search_query=producto, marca=None)
            if rows:
                rows = [r for r in rows if hasattr(r, "score") and float(r.score) >= _RELEVANCE_THRESHOLD]

    if not rows:
        return f"NO_RESULTS: No se encontraron proveedores de '{producto}' en la base de datos."

    # 3) Format results
    productos_list = [_transformer.row_to_producto(r) for r in rows]
    proveedores = _transformer.proveedores_con_precios(productos_list)
    marcas = _transformer.extract_marcas(productos_list)

    total = len(proveedores)
    show_max = min(3, total)
    shown = proveedores[:show_max]
    hidden_count = total - show_max

    lines = [f"Se encontraron {total} proveedores de '{producto}'."]
    if marcas:
        lines.append(f"Marcas disponibles: {', '.join(marcas[:8])}")
    lines.append("")

    for p in shown:
        ejemplos = p.get("ejemplos", "—")
        desc = p.get("descripcion_proveedor") or p.get("descripcion") or ""
        precios_ctx = p.get("contexto_precios", [])
        precio_str = ""
        if precios_ctx:
            first = precios_ctx[0]
            precio_val = first.get("precio")
            moneda = first.get("moneda", "MXN")
            if moneda and moneda.upper() == "PMX":
                moneda = "MXN"
            if precio_val:
                precio_str = f" | ${precio_val:,.2f} {moneda}"

        lines.append(
            f"- Proveedor: {p['proveedor']} (ID {p['proveedor_id']})"
            f"{precio_str}"
        )
        if desc and desc != "—":
            lines.append(f"  Descripción: {desc[:120]}")
        if ejemplos and ejemplos != "—":
            lines.append(f"  Productos: {ejemplos}")

    if hidden_count > 0:
        lines.append(f"\nHay {hidden_count} proveedores más disponibles.")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# Tool 2 – Price search / filter
# ─────────────────────────────────────────────────────────────────────
@tool
def filtrar_por_precio(
    producto: str,
    marca: Optional[str] = None,
    precio_max: Optional[float] = None,
) -> str:
    """Busca y ordena proveedores por precio para un producto.

    Usa cuando el usuario pregunta "cuánto cuesta", "el más barato",
    "precios de X", o menciona un rango de precio.

    Args:
        producto: Producto a buscar.
        marca: Marca específica (opcional).
        precio_max: Precio máximo si el usuario lo menciona.
    """
    logger.info(f"🔧 TOOL filtrar_por_precio: '{producto}', marca={marca}, max={precio_max}")

    precios = _qn._execute_price_search(producto, marca)
    if precio_max is not None:
        precios = [p for p in precios if p["precio_unidad"] <= precio_max]

    if not precios:
        return f"No encontré precios para '{producto}'. Prueba buscando el producto primero con buscar_productos."

    lines = [f"Precios de '{producto}' (ordenados de menor a mayor):"]
    for p in precios:
        prod_name = p.get("producto", "")
        marca_p = p.get("marca", "")
        pres = p.get("presentacion", "")
        detail = f"{prod_name} {marca_p}".strip()
        if pres:
            detail += f" ({pres})"
        lines.append(f"- {detail}: {p['precio_formateado']} — {p['proveedor']}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# Tool 3 – Provider detail
# ─────────────────────────────────────────────────────────────────────
@tool
def detalle_proveedor(nombre_proveedor: str) -> str:
    """Obtiene información detallada y contacto de un proveedor específico.

    Usa cuando el usuario pide más info, contacto o datos de un proveedor.
    Ejemplo: "info de La Ranita", "contacto de Distribuidora López".

    Args:
        nombre_proveedor: Nombre del proveedor tal como lo conoce el usuario.
    """
    logger.info(f"🔧 TOOL detalle_proveedor: '{nombre_proveedor}'")

    from sqlalchemy import text as sa_text

    sql = sa_text("""
        SELECT pr.id_proveedor, pr.nombre_comercial, pr.descripcion,
               pr.nombre_ejecutivo_ventas, pr.whatsapp_ventas, pr.pagina_web,
               pr.nivel_membresia, pr.calificacion_usuarios,
               similarity(pr.nombre_comercial, :nombre) as sim
        FROM proveedores pr
        WHERE similarity(pr.nombre_comercial, :nombre) > 0.3
        ORDER BY similarity(pr.nombre_comercial, :nombre) DESC
        LIMIT 1
    """)

    try:
        with _qn.engine.connect() as conn:
            row = conn.execute(sql, {"nombre": nombre_proveedor}).fetchone()

        if not row:
            return f"No encontré un proveedor llamado '{nombre_proveedor}'. Verifica el nombre."

        whatsapp_list, whatsapp_links = WhatsAppFormatter.format_numbers(row.whatsapp_ventas)

        def _fmt_phone(num: str) -> str:
            if len(num) >= 12 and num.startswith("52"):
                return f"+{num[:2]} {num[2:4]} {num[4:8]} {num[8:]}"
            return num

        lines = [
            f"Proveedor: {row.nombre_comercial}",
            f"Descripción: {row.descripcion or 'Sin descripción'}",
            f"Ejecutivo de ventas: {row.nombre_ejecutivo_ventas or 'No especificado'}",
        ]
        if whatsapp_list:
            lines.append(f"WhatsApp: {', '.join(_fmt_phone(n) for n in whatsapp_list)}")
            lines.append(f"Link contacto: {whatsapp_links[0]}")
        if row.pagina_web:
            lines.append(f"Web: {row.pagina_web}")
        if row.calificacion_usuarios and row.calificacion_usuarios > 0:
            lines.append(f"Calificación: {row.calificacion_usuarios}/5")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ detalle_proveedor error: {e}")
        return f"Error al buscar información del proveedor: {e}"


# ─────────────────────────────────────────────────────────────────────
# Tool 4 – Show more providers
# ─────────────────────────────────────────────────────────────────────
@tool
def mostrar_mas_proveedores(producto: str) -> str:
    """Muestra proveedores adicionales para un producto ya buscado.

    Usa cuando el usuario dice "muéstrame más", "hay más proveedores?",
    "otros proveedores" o similares.

    Args:
        producto: El producto de la búsqueda original.
    """
    logger.info(f"🔧 TOOL mostrar_mas_proveedores: '{producto}'")

    rows = _qn._execute_hybrid_search(search_query=producto, marca=None)
    if rows:
        rows = [r for r in rows if hasattr(r, "score") and float(r.score) >= _RELEVANCE_THRESHOLD]

    if not rows:
        return f"No encontré más proveedores de '{producto}'."

    productos_list = [_transformer.row_to_producto(r) for r in rows]
    proveedores = _transformer.proveedores_con_precios(productos_list)

    if not proveedores:
        return f"No hay más proveedores de '{producto}' disponibles."

    # Show up to 10
    show_max = min(10, len(proveedores))
    shown = proveedores[:show_max]

    lines = [f"Todos los proveedores de '{producto}' ({len(proveedores)} total):"]
    for p in shown:
        ejemplos = p.get("ejemplos", "—")
        lines.append(f"- {p['proveedor']} (ID {p['proveedor_id']}): {ejemplos}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# Tool 5 – Specialist consultation
# ─────────────────────────────────────────────────────────────────────

# Prompts reutilizados de specialist.py
_SPECIALIST_PROMPTS = {
    "chef": (
        "Eres un chef profesional. Da recetas e ideas de preparación BREVES "
        "(máximo 3-4 líneas). Sé práctico, incluye ingredientes principales y "
        "pasos ultra-resumidos. SIEMPRE termina preguntando si quiere proveedores "
        "del ingrediente clave. Usa emojis de comida 🍓🍫🥑."
    ),
    "nutriologo": (
        "Eres un nutriólogo profesional. Da información nutricional BREVE (2-3 líneas): "
        "calorías, 1-2 macros o beneficios clave. SIEMPRE ofrece proveedores al final. "
        "Usa emojis 🥗🥑🌾."
    ),
    "bartender": (
        "Eres un bartender profesional. Da recetas de cócteles BREVES (3-4 líneas) "
        "con medidas precisas (ml, oz). SIEMPRE ofrece proveedores al final. "
        "Usa emojis 🍹🍸🥃."
    ),
    "barista": (
        "Eres un barista profesional. Explica técnicas de café BREVES (3-4 líneas). "
        "Sé técnico pero accesible. SIEMPRE ofrece proveedores de café. Usa emoji ☕."
    ),
    "ingeniero_alimentos": (
        "Eres un ingeniero en alimentos. Explica conservación e inocuidad BREVE "
        "(3-4 líneas) con temperaturas y tiempos específicos. SIEMPRE ofrece "
        "proveedores al final. Usa emojis 🧈🥛🍖."
    ),
}


@tool
def consultar_especialista(
    pregunta: str,
    especialista: Literal[
        "chef", "nutriologo", "bartender", "barista", "ingeniero_alimentos"
    ],
) -> str:
    """Consulta a un especialista gastronómico.

    Usa para preguntas sobre recetas, nutrición, cócteles, café,
    o conservación/inocuidad de alimentos.

    Args:
        pregunta: La pregunta del usuario.
        especialista: Tipo de especialista: chef, nutriologo, bartender,
                      barista o ingeniero_alimentos.
    """
    logger.info(f"🔧 TOOL consultar_especialista: tipo={especialista}")

    system_prompt = _SPECIALIST_PROMPTS.get(especialista, _SPECIALIST_PROMPTS["chef"])

    try:
        llm = ChatOpenAI(model=settings.CHAT_MODEL, temperature=0.7)
        response = llm.invoke([("system", system_prompt), ("user", pregunta)])
        text = response.content.strip()
        # Clean bracket artifacts
        text = re.sub(r"\[([^\]]+)\]:\s*", r"\1: ", text)
        text = re.sub(r"\[([^\]]+)\]", r"\1", text)
        return text
    except Exception as e:
        logger.error(f"❌ consultar_especialista error: {e}")
        return "Tuve un problema consultando al especialista. ¿Puedo ayudarte a encontrar proveedores?"


# ─────────────────────────────────────────────────────────────────────
# Tool 6 – Report unregistered product
# ─────────────────────────────────────────────────────────────────────

_CLASSIFICATION_PROMPT = (
    "Eres un experto en el sector gastronómico. Clasifica si el producto "
    "'{producto}' pertenece al sector gastronómico/hospitalidad.\n\n"
    "Gastronómico: ingredientes, bebidas, equipo de cocina, vajilla, empaques "
    "para alimentos, productos gourmet.\n"
    "No gastronómico: cosméticos, medicamentos, electrónica, ropa, automotriz, "
    "construcción, juguetes, mascotas.\n\n"
    "Responde SOLO: GASTRONOMICO o NO_GASTRONOMICO"
)


@tool
def reportar_producto_no_encontrado(
    producto: str,
    telefono_usuario: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """Reporta un producto que no se encontró en la base de datos.

    Usa SOLO cuando buscar_productos retorna NO_RESULTS.
    Clasifica si el producto es gastronómico y envía email al equipo.

    Args:
        producto: El producto que no se encontró.
        telefono_usuario: Teléfono del usuario si se conoce.
        session_id: ID de sesión si se conoce.
    """
    logger.info(f"🔧 TOOL reportar_producto_no_encontrado: '{producto}'")

    # 1) Classify
    try:
        llm = ChatOpenAI(model=settings.ROUTER_MODEL, temperature=0)
        resp = llm.invoke([("user", _CLASSIFICATION_PROMPT.format(producto=producto))])
        raw = resp.content.strip().upper()
        es_gastro = "NO_GASTRONOMICO" not in raw and "NO GASTRONOMICO" not in raw
    except Exception:
        es_gastro = True  # Assume gastronomic on error

    # 2) Send email
    resumen = f"Cliente preguntó por: {producto}"
    email_service.enviar_solicitud_producto(
        producto_solicitado=producto,
        telefono_usuario=telefono_usuario,
        resumen_conversacion=resumen,
        es_gastronomico=es_gastro,
        session_id=session_id or "unknown",
    )

    # 3) Return message for agent to incorporate
    if es_gastro:
        return (
            f"GASTRONOMICO: '{producto}' es del sector gastronómico pero no lo tenemos "
            f"en la base de datos todavía. Se envió un reporte al equipo. "
            f"Informa al usuario que en hasta 12 horas le tendremos una sugerencia "
            f"y pregunta si quiere que le avisen por WhatsApp."
        )
    else:
        return (
            f"NO_GASTRONOMICO: '{producto}' no pertenece al sector gastronómico. "
            f"Informa al usuario que solo trabajamos con insumos gastronómicos "
            f"y pregunta si busca algún producto de cocina o abasto."
        )


# ── Export all tools ────────────────────────────────────────────────
ALL_TOOLS = [
    buscar_productos,
    filtrar_por_precio,
    detalle_proveedor,
    mostrar_mas_proveedores,
    consultar_especialista,
    reportar_producto_no_encontrado,
]
