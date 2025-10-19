# chatbot.py
import os
import json
import logging
from typing import Annotated, TypedDict, List
from dotenv import load_dotenv

load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# LangChain / LangGraph
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages, AnyMessage
from langgraph.prebuilt import ToolNode

# Herramientas de búsqueda
from search import (
    buscar_proveedores_con_relevancia,  # Nueva función con umbrales escalonados
    obtener_detalle_proveedor,  # para la vista de detalle
    obtener_marcas_disponibles,  # para preguntar por marca cuando hay ambigüedad
)

# Variable de entorno para buzón de quejas
BUZON_QUEJAS = os.getenv("BUZON_QUEJAS", "fake_buzon@gmail.com")
logger.info(f"📧 Buzón de quejas configurado: {BUZON_QUEJAS}")

# ========== SYSTEM PROMPT ==========
SYSTEM_PROMPT = (
    "Eres **The Hap & D Company**, un asistente de compras para la industria de "
    "alimentos y bebidas en el Valle de México.\n\n"
    "Objetivo: ayudar a encontrar proveedores confiables según lo que pida el usuario.\n"
    "Estilo: profesional, claro, proactivo y amable. Usa emojis con moderación y contexto "
    "(p. ej., 🫒 si hablan de aceite de oliva; 😉 o 😊 para cercanía; nunca abuses).\n"
    "\n"
    "**FORMATO DE ENLACES DE WHATSAPP (MUY IMPORTANTE):**\n"
    "Cuando la tool 'detalle_proveedor' devuelva enlaces de WhatsApp en formato Markdown:\n"
    "[+52 XX XXXX XXXX](https://wa.me/52XXXXXXXXXX)\n"
    "DEBES copiarlos EXACTAMENTE como vienen, SIN modificar el formato.\n"
    "NO conviertas los enlaces a texto plano.\n"
    "NO uses el formato: +52 XX XXXX XXXX / XXXX XXXX\n"
    "SIEMPRE usa el formato de enlace Markdown: [número visible](https://wa.me/...)\n\n"
    
    "Ejemplo CORRECTO de respuesta con WhatsApp:\n"
    "- **WhatsApp:** [+52 55 5489 9155](https://wa.me/5255489155), [+52 55 5489 9192](https://wa.me/5255489192)\n\n"
    
    "Ejemplo INCORRECTO (NO hagas esto):\n"
    "- **WhatsApp:** +52 55 5489 9155 / 5489 9192\n\n"
    
    "**MANEJO DE USUARIOS DIFÍCILES:**\n"
    "Si el usuario es agresivo, sarcástico, solicita productos ilegales/fuera del sector, "
    "o descalifica el servicio sin fundamento:\n"
    "1. Mantén calma y profesionalismo absoluto (NUNCA confrontes ni uses sarcasmo)\n"
    "2. Reconoce su comentario sin juzgar: 'Entiendo tu comentario/frustración 😊'\n"
    "3. Redirige al tema gastronómico: '¿Qué producto del sector gastronómico buscas?'\n"
    f"4. Ofrece el buzón de quejas como opción: 'Puedes enviarnos tu feedback a {BUZON_QUEJAS}'\n"
    "5. Si insiste en temas inapropiados: 'Nuestro enfoque es exclusivamente el sector gastronómico'\n\n"
    
    "**MANEJO DE CONSULTAS AMBIGUAS:**\n"
    "Cuando el usuario busque un producto de forma genérica/ambigua (ej: 'mantequilla', 'aceite', 'queso'), "
    "NO muestres inmediatamente la lista completa de proveedores. En su lugar:\n"
    "1. Pregunta si tiene preferencia por alguna **marca específica** (ej: Anchor, Lyncott, Presidente)\n"
    "2. El JSON devuelto por `buscar_proveedores` incluye `marcas_disponibles` - úsalas para sugerir opciones\n"
    "3. Si el usuario especifica marca, llama a `buscar_proveedores_marca` con product y marca\n"
    "4. Si el usuario dice 'no importa la marca' o 'dame cualquiera', procede con la búsqueda sin filtro\n\n"
    
    "Ejemplo de flujo:\n"
    "Usuario: 'Busco mantequilla'\n"
    "Bot: 'Tenemos varias marcas de mantequilla: Anchor, Lyncott, Président. ¿Tienes preferencia por alguna? 😊'\n"
    "Usuario: 'Sí, Anchor'\n"
    "Bot: [llama buscar_proveedores_marca(product='mantequilla', marca='Anchor')]\n\n"
    
    "**FORMATO DE RESPUESTA ESTRICTO:**\n"
    "Al mostrar proveedores (con buscar_proveedores o mostrar_mas_proveedores), usa ESTE formato:\n\n"
    "[Introducción breve]\n\n"
    "1. **[Nombre Proveedor]**\n"
    "   - Ejemplos de productos: [ejemplos]\n\n"
    "2. **[Nombre Proveedor]**\n"
    "   - Ejemplos de productos: [ejemplos]\n\n"
    "[Si hay más proveedores: 'Hay X proveedores más disponibles. ¿Quieres que te los muestre? 😊']\n"
    "[Siempre al final: '¿Quieres más información de algún proveedor en particular? 😉']\n\n"
    
    "**NO INCLUYAS (a menos que el usuario pida 'según precio' o 'más barato'):**\n"
    "- Precios\n"
    "- WhatsApp, teléfonos, emails\n"
    "- Nombre de ejecutivos/vendedores\n"
    "- Páginas web, enlaces\n"
    "- Direcciones o ubicaciones\n\n"
    
    "**CONTEXTO DE PRECIOS:**\n"
    "El JSON incluye `contexto_precios` con: producto, marca, precio, unidad (presentación), moneda.\n"
    "- NO muestres precios por defecto (ordenamiento por membresía/reputación)\n"
    "- SOLO usa precios si el usuario EXPLÍCITAMENTE pide:\n"
    "  * 'según precio', 'el más barato', 'opciones económicas', 'mejor relación calidad-precio'\n"
    "- Cuando uses precios, menciona: precio + presentación (ej: '$45 MXN por kg')\n"
    "- Recuerda: la presentación está en 'unidad' (ej: '1kg', '500g', '1L')\n\n"
    
    "**MANEJO DE RELEVANCIA DE PRODUCTOS:**\n"
    "La tool `buscar_proveedores` devuelve un JSON con `nivel_relevancia`:\n\n"
    
    "1. **'alta'**: Producto encontrado.\n"
    "   → Verifica si hay múltiples marcas (`marcas_disponibles`)\n"
    "   → Si hay 3+ marcas Y el usuario no especificó marca: pregunta por marca\n"
    "   → Si hay pocas marcas o usuario ya especificó: muestra proveedores TOP\n\n"
    
    "2. **'media'**: Producto no registrado pero hay similares.\n"
    "   → 'Ese producto no lo tenemos en nuestro registro todavía, pero te puedo ofrecer estos similares' + lista\n\n"
    
    "3. **'nula'**: Fuera del sector.\n"
    "   → 'Ese producto no forma parte del sector gastronómico en el que nos especializamos. "
    "Trabajamos únicamente con insumos para cocinas profesionales y negocios de hospitalidad gastronómica. "
    "¿Quieres buscar algún producto de cocina o abasto?'\n\n"
    
    "**IMPORTANTE:**\n"
    "- Llama a `buscar_proveedores` UNA SOLA VEZ por producto (sin filtro de marca inicialmente)\n"
    "- Si usuario especifica marca, usa `buscar_proveedores_marca`\n"
    "- NO inventes información de contacto o precios\n"
    "- Ordenamiento por defecto: membresía/reputación (no precio)\n"
    "- Respeta el formato de lista simple: solo nombre + ejemplos (sin precios ni contactos)\n"
    "\n"
    "**RESUMEN:**\n"
    "- Ambiguo → pregunta marca\n"
    "- Lista simple → solo nombre y ejemplos\n"
    "- Precios → solo si se piden explícitamente\n"
    "- Contactos → solo con detalle_proveedor\n"
    "- Usuarios difíciles → empatía, profesionalismo, redirección y buzón de quejas"
)

logger.info("📋 System prompt cargado con éxito")
logger.debug(f"📝 Longitud del system prompt: {len(SYSTEM_PROMPT)} caracteres")

# ========== SYSTEM PROMPTS PARA ROLES ESPECIALIZADOS ==========

SYSTEM_PROMPT_ROUTER = (
    "Eres un clasificador de intenciones para The Hap & D Company.\n"
    "Tu ÚNICA tarea: determinar qué tipo de consulta hace el usuario.\n\n"
    "Categorías válidas:\n"
    "1. 'busqueda_proveedores' - Usuario busca proveedores, productos, contactos\n"
    "2. 'chef' - Pide recetas, técnicas de cocina, preparación de platillos\n"
    "3. 'nutriologo' - Pregunta sobre calorías, nutrición, información nutricional\n"
    "4. 'bartender' - Busca cócteles, recetas de bebidas, maridajes\n"
    "5. 'barista' - Técnicas de café, preparación de café, métodos de extracción\n"
    "6. 'ingeniero_alimentos' - Conservación, almacenamiento, inocuidad, vida útil\n"
    "7. 'fuera_alcance' - Pregunta completamente fuera del sector gastronómico\n\n"
    "Responde SOLO con el nombre de la categoría, nada más.\n"
    "Ejemplos:\n"
    "Usuario: 'Busco mantequilla' → busqueda_proveedores\n"
    "Usuario: 'Quiero contacto de proveedores de aceite' → busqueda_proveedores\n"
    "Usuario: '¿Cómo hacer fresas Dubai?' → chef\n"
    "Usuario: 'Dame una receta de tiramisú' → chef\n"
    "Usuario: '¿Cuántas calorías tiene la quinoa?' → nutriologo\n"
    "Usuario: '¿Es nutritivo el aguacate?' → nutriologo\n"
    "Usuario: 'Coctel con mezcal y frutos rojos' → bartender\n"
    "Usuario: 'Receta de margarita' → bartender\n"
    "Usuario: '¿Cómo se hace cold brew?' → barista\n"
    "Usuario: 'Mejor método para espresso' → barista\n"
    "Usuario: '¿Cuánto dura la mantequilla sin refrigerar?' → ingeniero_alimentos\n"
    "Usuario: '¿Cómo conservar el salmón?' → ingeniero_alimentos\n"
    "Usuario: '¿Quién ganó el mundial?' → fuera_alcance\n"
    "Usuario: 'Dame el clima de hoy' → fuera_alcance"
)

SYSTEM_PROMPT_CHEF = (
    "Eres un chef profesional de The Hap & D Company.\n"
    "Tu rol: Dar recetas e ideas de preparación BREVES (máximo 3-4 líneas).\n\n"
    "Formato obligatorio:\n"
    "'[Ingredientes principales breves] + [Pasos ultra-resumidos en 1-2 líneas]. "
    "¿Quieres que te conecte con proveedores de [ingrediente clave]? 😊'\n\n"
    "Ejemplo:\n"
    "Usuario: 'Receta de Fresas Dubai'\n"
    "Tú: 'Para Fresas Dubai necesitas: fresas frescas, chocolate semiamargo y pistache troceado. "
    "Derrite el chocolate, baña las fresas, decora con pistache y refrigera 30 min. 🍓 "
    "¿Quieres proveedores de fresas o chocolate?'\n\n"
    "IMPORTANTE:\n"
    "- Máximo 3-4 líneas de respuesta\n"
    "- SIEMPRE termina preguntando si quiere proveedores\n"
    "- Usa emojis relacionados con la comida 🍓🍫🥑\n"
    "- Sé práctico y directo, sin teoría extensa"
)

SYSTEM_PROMPT_NUTRIOLOGO = (
    "Eres un nutriólogo profesional de The Hap & D Company.\n"
    "Tu rol: Dar información nutricional BREVE y práctica.\n\n"
    "Formato obligatorio:\n"
    "'[Alimento] aporta [calorías] kcal [porción], [dato relevante de macros/beneficios]. "
    "¿Quieres proveedores de [alimento]? 😊'\n\n"
    "Ejemplo:\n"
    "Usuario: '¿Cuántas calorías tiene la quinoa?'\n"
    "Tú: 'Una taza cocida de quinoa (185g) aporta aprox. 220 kcal, "
    "rica en proteína (8g) y fibra (5g), además es libre de gluten. 🌾 "
    "¿Quieres proveedores de quinoa?'\n\n"
    "IMPORTANTE:\n"
    "- Máximo 2-3 líneas\n"
    "- SIEMPRE ofrece proveedores al final\n"
    "- Datos concisos (calorías + 1-2 macros o beneficios clave)\n"
    "- Usa emojis relacionados 🥗🥑🌾"
)

SYSTEM_PROMPT_BARTENDER = (
    "Eres un bartender profesional de The Hap & D Company.\n"
    "Tu rol: Dar recetas de cócteles y maridajes BREVES.\n\n"
    "Formato obligatorio:\n"
    "'[Ingredientes con medidas] + [Preparación breve]. 🍹 "
    "¿Quieres proveedores de [ingrediente principal]?'\n\n"
    "Ejemplo:\n"
    "Usuario: 'Coctel con mezcal y frutos rojos'\n"
    "Tú: 'Prueba este: 60ml mezcal, 30ml jugo de arándano, 15ml jarabe natural, "
    "hielo y rodaja de naranja. Agita con hielo y sirve en vaso corto. 🍹 "
    "¿Quieres proveedores de mezcal o frutos rojos?'\n\n"
    "IMPORTANTE:\n"
    "- Máximo 3-4 líneas\n"
    "- SIEMPRE ofrece proveedores al final\n"
    "- Incluye medidas precisas (ml, oz)\n"
    "- Usa emojis de bebidas 🍹🍸🥃"
)

SYSTEM_PROMPT_BARISTA = (
    "Eres un barista profesional de The Hap & D Company.\n"
    "Tu rol: Explicar técnicas de café BREVES y prácticas.\n\n"
    "Formato obligatorio:\n"
    "'[Técnica resumida en 2-3 pasos clave]. ☕ "
    "¿Quieres proveedores de café [tipo de café]?'\n\n"
    "Ejemplo:\n"
    "Usuario: '¿Cómo hacer cold brew para cafetería?'\n"
    "Tú: 'Usa café molido grueso y agua fría en proporción 1:5. "
    "Deja reposar 12-18 horas en refrigeración, filtra con malla fina "
    "y sirve sobre hielo. ☕ ¿Quieres proveedores de café en grano?'\n\n"
    "IMPORTANTE:\n"
    "- Máximo 3-4 líneas\n"
    "- SIEMPRE ofrece proveedores de café\n"
    "- Sé técnico pero accesible\n"
    "- Usa emoji de café ☕"
)

SYSTEM_PROMPT_INGENIERO = (
    "Eres un ingeniero en alimentos de The Hap & D Company.\n"
    "Tu rol: Explicar conservación e inocuidad de forma BREVE.\n\n"
    "Formato obligatorio:\n"
    "'[Producto] se conserva [tiempo] en [condiciones]. [Dato adicional de seguridad]. "
    "¿Quieres proveedores de [producto]? 😊'\n\n"
    "Ejemplo:\n"
    "Usuario: '¿Cuánto dura la mantequilla sin refrigerar?'\n"
    "Tú: 'Mantequilla a temperatura ambiente (20-25°C) dura hasta 2 días máximo. "
    "En refrigeración (4°C) se conserva hasta 4 semanas bien sellada. "
    "Fuera del frío puede oxidarse y desarrollar sabor rancio. 🧈 "
    "¿Quieres proveedores de mantequilla?'\n\n"
    "IMPORTANTE:\n"
    "- Máximo 3-4 líneas\n"
    "- SIEMPRE ofrece proveedores al final\n"
    "- Incluye temperaturas y tiempos específicos\n"
    "- Usa emojis relacionados 🧈🥛🍖"
)

logger.info("📋 System prompts especializados cargados")

# ========== ESTADO GLOBAL PARA PROVEEDORES PENDIENTES ==========
# Usamos un dict global para mantener los proveedores ocultos por sesión de búsqueda
_proveedores_pendientes = {}
logger.info("💾 Diccionario global de proveedores pendientes inicializado")

# ========== TOOLS ==========
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.tools import StructuredTool


class ProductArgs(BaseModel):
    product: str = Field(
        ...,
        description="Nombre del producto a buscar (ej. 'aceite de oliva', 'queso manchego').",
    )


def _tool_buscar_proveedores(product: str) -> str:
    """
    Llama a la búsqueda con umbrales escalonados y devuelve un JSON estructurado.
    Según el nivel de relevancia:
    - alta: muestra 2-3 proveedores TOP + marcas disponibles (para detectar ambigüedad)
    - media: informa que el producto no está registrado pero ofrece similares
    - nula: informa que el producto está fuera del sector gastronómico
    
    Incluye contexto_precios para que el LLM pueda usarlo si el usuario lo solicita.
    """
    global _proveedores_pendientes  # Declarar global al inicio de la función
    
    logger.info(f"🔧 TOOL LLAMADA: buscar_proveedores(product='{product}')")
    logger.debug(f"🔍 Iniciando búsqueda de proveedores para producto: '{product}'")
    
    rows, nivel_relevancia, marcas_disponibles = buscar_proveedores_con_relevancia(product=product)
    
    logger.info(f"📊 Nivel de relevancia detectado: '{nivel_relevancia}'")
    logger.info(f"📈 Total de proveedores encontrados: {len(rows)}")
    if marcas_disponibles:
        logger.info(f"🏷️  Marcas disponibles: {marcas_disponibles[:5]}" + (f" (y {len(marcas_disponibles)-5} más)" if len(marcas_disponibles) > 5 else ""))
        logger.debug(f"🔖 Total de marcas únicas: {len(marcas_disponibles)}")
    
    # CASO 3: Producto fuera del sector gastronómico
    if nivel_relevancia == "nula":
        logger.warning(f"❌ Producto '{product}' fuera del sector gastronómico")
        logger.debug("⚠️  Retornando respuesta de nivel 'nula' al LLM")
        resultado = {
            "nivel_relevancia": "nula",
            "mensaje": f"El producto '{product}' parece estar fuera del sector gastronómico.",
            "proveedores": [],
            "marcas_disponibles": []
        }
        logger.debug(f"📤 JSON resultado: {json.dumps(resultado, ensure_ascii=False)}")
        return json.dumps(resultado, ensure_ascii=False)
    
    # CASO 2: Producto gastronómico pero no registrado (ofrecer similares)
    if nivel_relevancia == "media":
        logger.info(f"⚡ Producto '{product}' no registrado, ofreciendo {len(rows)} similares")
        
        # Mostrar solo los primeros 2-3
        max_inicial = 3
        rows_mostrados = rows[:max_inicial]
        rows_ocultos = rows[max_inicial:]
        
        logger.debug(f"✂️  Dividiendo resultados: {len(rows_mostrados)} mostrados, {len(rows_ocultos)} ocultos")
        
        # Guardar ocultos para "mostrar más"
        _proveedores_pendientes[product.lower()] = rows_ocultos
        
        if rows_ocultos:
            logger.info(f"💾 Guardados {len(rows_ocultos)} proveedores similares para 'mostrar_mas'")
            logger.debug(f"🗃️  Key en dict pendientes: '{product.lower()}'")
        
        # Construir metadata con contexto de precios
        meta = []
        for idx, r in enumerate(rows_mostrados):
            logger.debug(f"📦 Proveedor {idx+1}: {r['proveedor']} (ID: {r['proveedor_id']}, Rank: {r['rank']})")
            logger.debug(f"   └─ Ejemplos: {r['ejemplos'][:50]}..." if len(r.get('ejemplos', '')) > 50 else f"   └─ Ejemplos: {r.get('ejemplos', 'N/A')}")
            if r.get("contexto_precios"):
                logger.debug(f"   └─ Precios disponibles: {len(r['contexto_precios'])} items")
            meta.append({
                "rank": r["rank"],
                "proveedor_id": r["proveedor_id"],
                "proveedor": r["proveedor"],
                "ejemplos": r["ejemplos"],
                "contexto_precios": r.get("contexto_precios", []),
            })
        
        resultado = {
            "nivel_relevancia": "media",
            "mensaje": f"El producto '{product}' no está en nuestro registro, pero encontré {len(rows)} productos similares.",
            "proveedores_mostrados": len(rows_mostrados),
            "proveedores_ocultos": len(rows_ocultos),
            "proveedores": meta,
            "marcas_disponibles": marcas_disponibles
        }
        logger.info(f"✅ Retornando {len(meta)} proveedores similares al LLM")
        logger.debug(f"📤 JSON resultado: {json.dumps(resultado, ensure_ascii=False)[:200]}...")
        return json.dumps(resultado, ensure_ascii=False)
    
    # CASO 1: Alta relevancia (producto encontrado)
    if nivel_relevancia == "alta":
        logger.info(f"✅ Producto '{product}' encontrado con alta relevancia: {len(rows)} proveedores")
        
        # Mostrar solo los primeros 2-3
        max_inicial = 3
        rows_mostrados = rows[:max_inicial]
        rows_ocultos = rows[max_inicial:]
        
        logger.debug(f"✂️  Dividiendo resultados: {len(rows_mostrados)} mostrados, {len(rows_ocultos)} ocultos")
        
        # Guardar ocultos
        _proveedores_pendientes[product.lower()] = rows_ocultos
        
        if rows_ocultos:
            logger.info(f"💾 Guardados {len(rows_ocultos)} proveedores para 'mostrar_mas'")
            logger.debug(f"🗃️  Key en dict pendientes: '{product.lower()}'")
        
        # Construir metadata con contexto de precios
        meta = []
        for idx, r in enumerate(rows_mostrados):
            logger.debug(f"📦 Proveedor {idx+1}: {r['proveedor']} (ID: {r['proveedor_id']}, Rank: {r['rank']})")
            logger.debug(f"   └─ Ejemplos: {r['ejemplos'][:50]}..." if len(r.get('ejemplos', '')) > 50 else f"   └─ Ejemplos: {r.get('ejemplos', 'N/A')}")
            if r.get("contexto_precios"):
                logger.debug(f"   └─ Precios disponibles: {len(r['contexto_precios'])} items")
            meta.append({
                "rank": r["rank"],
                "proveedor_id": r["proveedor_id"],
                "proveedor": r["proveedor"],
                "ejemplos": r["ejemplos"],
                "contexto_precios": r.get("contexto_precios", []),
            })
        
        resultado = {
            "nivel_relevancia": "alta",
            "mensaje": f"Encontré {len(rows)} proveedores para '{product}'.",
            "proveedores_mostrados": len(rows_mostrados),
            "proveedores_ocultos": len(rows_ocultos),
            "proveedores": meta,
            "marcas_disponibles": marcas_disponibles  # Para detectar si hay que preguntar por marca
        }
        logger.info(f"✅ Retornando {len(meta)} proveedores TOP al LLM")
        logger.debug(f"📤 JSON resultado: {json.dumps(resultado, ensure_ascii=False)[:200]}...")
        return json.dumps(resultado, ensure_ascii=False)
    
    # Fallback (no debería llegar aquí)
    logger.error(f"⚠️  Fallback alcanzado - nivel_relevancia inesperado: '{nivel_relevancia}'")
    resultado = {
        "nivel_relevancia": "nula",
        "mensaje": "No se encontraron resultados.",
        "proveedores": [],
        "marcas_disponibles": []
    }
    return json.dumps(resultado, ensure_ascii=False)


buscar_proveedores_tool = StructuredTool.from_function(
    func=_tool_buscar_proveedores,
    name="buscar_proveedores",
    description=(
        "Busca y lista los 2-3 proveedores TOP que venden un producto específico. "
        "Requiere el parámetro 'product'. Devuelve una lista breve con nombre y ejemplos. "
        "Si hay más proveedores, indica que el usuario puede solicitar verlos."
    ),
    args_schema=ProductArgs,
)
logger.info("🔧 Tool 'buscar_proveedores' registrada")


class MostrarMasArgs(BaseModel):
    product: str = Field(
        ...,
        description="Nombre del producto sobre el que se hizo la búsqueda anterior.",
    )


def _tool_mostrar_mas_proveedores(product: str) -> str:
    """
    Muestra los proveedores que quedaron ocultos en la búsqueda anterior.
    """
    logger.info(f"🔧 TOOL LLAMADA: mostrar_mas_proveedores(product='{product}')")
    
    global _proveedores_pendientes
    key = product.lower()
    
    logger.debug(f"🔍 Buscando proveedores pendientes con key: '{key}'")
    logger.debug(f"🗂️  Keys disponibles en dict: {list(_proveedores_pendientes.keys())}")
    
    if key not in _proveedores_pendientes or not _proveedores_pendientes[key]:
        logger.warning(f"⚠️  No hay proveedores pendientes para '{product}'")
        logger.debug(f"❌ Key '{key}' no encontrada o lista vacía")
        return (
            f"No hay más proveedores para mostrar de '{product}'. "
            "Puede que ya hayas visto todos los resultados disponibles."
        )
    
    rows_ocultos = _proveedores_pendientes[key]
    logger.info(f"📤 Mostrando {len(rows_ocultos)} proveedores adicionales de '{product}'")
    
    # Render de los proveedores ocultos
    lines = [f"**Proveedores adicionales para '{product}'**:"]
    meta = []
    
    for idx, r in enumerate(rows_ocultos):
        logger.debug(f"📦 Proveedor adicional {idx+1}: {r['proveedor']} (ID: {r['proveedor_id']}, Rank: {r['rank']})")
        ejemplos = f" — ej.: {r['ejemplos']}" if r.get("ejemplos") and r["ejemplos"] != "—" else ""
        lines.append(f"{r['rank']}. **{r['proveedor']}**{ejemplos}")
        
        meta.append(
            {
                "rank": r["rank"],
                "proveedor_id": r["proveedor_id"],
                "proveedor": r["proveedor"],
                "contacto_detallado": r.get("contacto_detallado", {}),
            }
        )
    
    lines.append("\n¿Quieres más información de alguno? 😉")
    
    # Bloque JSON de metadatos
    meta_block = json.dumps(meta, ensure_ascii=False)
    lines.append("\n```json meta_proveedores\n" + meta_block + "\n```")
    
    # Limpiar los proveedores pendientes ya que ya fueron mostrados
    _proveedores_pendientes[key] = []
    logger.info(f"🧹 Limpiados proveedores pendientes de '{product}'")
    logger.debug(f"✅ Key '{key}' ahora tiene lista vacía")
    
    resultado = "\n".join(lines)
    logger.debug(f"📤 Respuesta generada: {len(resultado)} caracteres")
    return resultado


mostrar_mas_proveedores_tool = StructuredTool.from_function(
    func=_tool_mostrar_mas_proveedores,
    name="mostrar_mas_proveedores",
    description=(
        "Muestra SOLO los nombres y ejemplos de productos de los proveedores adicionales "
        "que no se mostraron en la búsqueda inicial. Requiere 'product' (el mismo producto "
        "de la búsqueda anterior). Úsala cuando el usuario pida ver más opciones, más proveedores, "
        "otros resultados, etc. IMPORTANTE: Esta tool NO incluye información de contacto, solo nombres."
    ),
    args_schema=MostrarMasArgs,
)
logger.info("🔧 Tool 'mostrar_mas_proveedores' registrada")


class DetalleArgs(BaseModel):
    proveedor_id: int = Field(
        ..., description="ID del proveedor del que se quiere obtener la información detallada."
    )


def _tool_detalle_proveedor(proveedor_id: int) -> str:
    """
    Devuelve la ficha detallada del proveedor:
    - nombre del vendedor (nombre_ejecutivo_ventas)
    - WhatsApp (posibles múltiples números, cada uno con su enlace wa.me)
    - Sitio web
    """
    logger.info(f"🔧 TOOL LLAMADA: detalle_proveedor(proveedor_id={proveedor_id})")
    logger.debug(f"🔍 Consultando detalles del proveedor con ID: {proveedor_id}")
    
    data = obtener_detalle_proveedor(proveedor_id)
    if not data:
        logger.warning(f"⚠️  No se encontró información para proveedor_id={proveedor_id}")
        logger.debug(f"❌ La función obtener_detalle_proveedor retornó None/vacío")
        return f"No encontré detalle para proveedor_id={proveedor_id}."

    nombre = data.get("proveedor") or "Proveedor"
    logger.info(f"📋 Detalles obtenidos para proveedor: {nombre}")
    logger.debug(f"📊 Datos recibidos: {list(data.keys())}")
    
    ejecutivo = data.get("nombre_ejecutivo_ventas") or "—"
    wa_numbers = data.get("whatsapp_ventas_list") or []  # lista de números normalizados
    wa_links = data.get("whatsapp_links") or []          # lista de enlaces wa.me
    web = data.get("pagina_web") or "—"

    logger.debug(f"👤 Ejecutivo de ventas: {ejecutivo}")
    logger.debug(f"📱 WhatsApp numbers: {len(wa_numbers)} número(s)")
    logger.debug(f"🔗 WhatsApp links: {len(wa_links)} enlace(s)")
    logger.debug(f"🌐 Sitio web: {web}")

    # Render de múltiples WhatsApp como enlaces clickeables
    if wa_links:
        wa_lines = []
        for i, link in enumerate(wa_links):
            # Formato del número para mostrar (con espacios para legibilidad)
            numero_raw = wa_numbers[i] if i < len(wa_numbers) else f"Número {i+1}"
            # Formatear el número: si empieza con 52, mostrar como +52 (XX) XXXX XXXX
            if numero_raw.startswith("52") and len(numero_raw) >= 12:
                numero_formateado = f"+52 {numero_raw[2:4]} {numero_raw[4:8]} {numero_raw[8:]}"
            elif numero_raw.startswith("521") and len(numero_raw) >= 13:
                numero_formateado = f"+52 1 {numero_raw[3:5]} {numero_raw[5:9]} {numero_raw[9:]}"
            else:
                numero_formateado = numero_raw
            
            # Crear enlace clickeable en formato Markdown
            wa_lines.append(f"[{numero_formateado}]({link})")
            logger.debug(f"   └─ WhatsApp {i+1}: {numero_formateado} -> {link}")
        
        # Unir con comas si hay múltiples números
        wa_block = ", ".join(wa_lines)
    else:
        wa_block = "—"
        logger.debug("📱 No hay números de WhatsApp disponibles")

    lines = [
        f"**Detalles de {nombre}:**",
        f"- **Vendedor:** {ejecutivo}",
        f"- **WhatsApp:** {wa_block}",
        f"- **Sitio web:** {web}",
    ]
    resultado = "\n".join(lines)
    logger.info(f"✅ Detalles del proveedor generados exitosamente")
    logger.debug(f"📤 Respuesta: {len(resultado)} caracteres")
    return resultado


detalle_proveedor_tool = StructuredTool.from_function(
    func=_tool_detalle_proveedor,
    name="detalle_proveedor",
    description=(
        "Muestra la información detallada de un proveedor (vendedor, WhatsApp/link y web). "
        "Requiere 'proveedor_id'. Úsala cuando el usuario pida más información de un proveedor concreto."
    ),
    args_schema=DetalleArgs,
)
logger.info("🔧 Tool 'detalle_proveedor' registrada")


class ProductMarcaArgs(BaseModel):
    product: str = Field(
        ...,
        description="Nombre del producto a buscar (ej. 'mantequilla', 'aceite').",
    )
    marca: str = Field(
        ...,
        description="Marca específica a filtrar (ej. 'Anchor', 'Lyncott', 'Président').",
    )


def _tool_buscar_proveedores_marca(product: str, marca: str) -> str:
    """
    Llama a la búsqueda filtrando por marca específica.
    Útil cuando el usuario ha especificado preferencia por una marca.
    """
    global _proveedores_pendientes
    
    logger.info(f"🔧 TOOL LLAMADA: buscar_proveedores_marca(product='{product}', marca='{marca}')")
    logger.debug(f"🔍 Iniciando búsqueda con filtro de marca: '{marca}' para producto: '{product}'")
    
    rows, nivel_relevancia, _ = buscar_proveedores_con_relevancia(
        product=product, 
        marca_filtro=marca
    )
    
    logger.info(f"📊 Nivel de relevancia detectado: '{nivel_relevancia}' | Marca: '{marca}'")
    logger.info(f"📈 Total de proveedores encontrados: {len(rows)}")
    
    # CASO 3: Producto fuera del sector gastronómico
    if nivel_relevancia == "nula":
        logger.warning(f"❌ Producto '{product}' marca '{marca}' fuera del sector o sin resultados")
        resultado = {
            "nivel_relevancia": "nula",
            "mensaje": f"No encontré '{product}' de la marca '{marca}' en nuestro catálogo.",
            "proveedores": [],
            "contexto_precios": []
        }
        logger.debug(f"📤 JSON resultado: {json.dumps(resultado, ensure_ascii=False)}")
        return json.dumps(resultado, ensure_ascii=False)
    
    # Si no hay resultados con esta marca específica
    if not rows:
        logger.warning(f"⚠️ No se encontraron productos de marca '{marca}' para '{product}'")
        resultado = {
            "nivel_relevancia": "nula",
            "mensaje": f"No encontré '{product}' de la marca '{marca}'. ¿Quieres ver otras marcas disponibles?",
            "proveedores": [],
            "contexto_precios": []
        }
        logger.debug(f"📤 JSON resultado: {json.dumps(resultado, ensure_ascii=False)}")
        return json.dumps(resultado, ensure_ascii=False)
    
    # CASO 2: Producto gastronómico pero no registrado (ofrecer similares)
    if nivel_relevancia == "media":
        logger.info(f"⚡ Producto '{product}' marca '{marca}' no registrado, ofreciendo {len(rows)} similares")
        
        max_inicial = 3
        rows_mostrados = rows[:max_inicial]
        rows_ocultos = rows[max_inicial:]
        
        key_pendiente = f"{product}_{marca}".lower()
        logger.debug(f"✂️  Dividiendo resultados: {len(rows_mostrados)} mostrados, {len(rows_ocultos)} ocultos")
        logger.debug(f"🗃️  Key para pendientes: '{key_pendiente}'")
        
        _proveedores_pendientes[key_pendiente] = rows_ocultos
        
        if rows_ocultos:
            logger.info(f"💾 Guardados {len(rows_ocultos)} proveedores similares para 'mostrar_mas'")
        
        # Incluir contexto_precios para que el LLM pueda usarlo si se solicita
        meta = []
        for idx, r in enumerate(rows_mostrados):
            logger.debug(f"📦 Proveedor {idx+1}: {r['proveedor']} (ID: {r['proveedor_id']}, Rank: {r['rank']})")
            if r.get("contexto_precios"):
                logger.debug(f"   └─ Precios disponibles: {len(r['contexto_precios'])} items")
            meta.append({
                "rank": r["rank"],
                "proveedor_id": r["proveedor_id"],
                "proveedor": r["proveedor"],
                "ejemplos": r["ejemplos"],
                "contexto_precios": r.get("contexto_precios", []),
            })
        
        resultado = {
            "nivel_relevancia": "media",
            "mensaje": f"El producto '{product}' marca '{marca}' no está exactamente, pero encontré similares.",
            "proveedores_mostrados": len(rows_mostrados),
            "proveedores_ocultos": len(rows_ocultos),
            "proveedores": meta,
            "marca_solicitada": marca
        }
        logger.info(f"✅ Retornando {len(meta)} proveedores similares al LLM")
        logger.debug(f"📤 JSON resultado: {json.dumps(resultado, ensure_ascii=False)[:200]}...")
        return json.dumps(resultado, ensure_ascii=False)
    
    # CASO 1: Alta relevancia (producto encontrado con marca específica)
    if nivel_relevancia == "alta":
        logger.info(f"✅ Producto '{product}' marca '{marca}' encontrado: {len(rows)} proveedores")
        
        max_inicial = 3
        rows_mostrados = rows[:max_inicial]
        rows_ocultos = rows[max_inicial:]
        
        key_pendiente = f"{product}_{marca}".lower()
        logger.debug(f"✂️  Dividiendo resultados: {len(rows_mostrados)} mostrados, {len(rows_ocultos)} ocultos")
        logger.debug(f"🗃️  Key para pendientes: '{key_pendiente}'")
        
        _proveedores_pendientes[key_pendiente] = rows_ocultos
        
        if rows_ocultos:
            logger.info(f"💾 Guardados {len(rows_ocultos)} proveedores para 'mostrar_mas'")
        
        # Incluir contexto_precios para que el LLM pueda usarlo si se solicita
        meta = []
        for idx, r in enumerate(rows_mostrados):
            logger.debug(f"📦 Proveedor {idx+1}: {r['proveedor']} (ID: {r['proveedor_id']}, Rank: {r['rank']})")
            if r.get("contexto_precios"):
                logger.debug(f"   └─ Precios disponibles: {len(r['contexto_precios'])} items")
            meta.append({
                "rank": r["rank"],
                "proveedor_id": r["proveedor_id"],
                "proveedor": r["proveedor"],
                "ejemplos": r["ejemplos"],
                "contexto_precios": r.get("contexto_precios", []),
            })
        
        resultado = {
            "nivel_relevancia": "alta",
            "mensaje": f"Encontré {len(rows)} proveedores de '{product}' marca '{marca}'.",
            "proveedores_mostrados": len(rows_mostrados),
            "proveedores_ocultos": len(rows_ocultos),
            "proveedores": meta,
            "marca_solicitada": marca
        }
        logger.info(f"✅ Retornando {len(meta)} proveedores de marca específica al LLM")
        logger.debug(f"📤 JSON resultado: {json.dumps(resultado, ensure_ascii=False)[:200]}...")
        return json.dumps(resultado, ensure_ascii=False)
    
    # Fallback
    logger.error(f"⚠️  Fallback alcanzado - nivel_relevancia inesperado: '{nivel_relevancia}'")
    resultado = {
        "nivel_relevancia": "nula",
        "mensaje": "No se encontraron resultados.",
        "proveedores": [],
        "contexto_precios": []
    }
    return json.dumps(resultado, ensure_ascii=False)


buscar_proveedores_marca_tool = StructuredTool.from_function(
    func=_tool_buscar_proveedores_marca,
    name="buscar_proveedores_marca",
    description=(
        "Busca proveedores de un producto FILTRANDO por marca específica. "
        "Requiere 'product' y 'marca'. Úsala cuando el usuario especifique una marca concreta "
        "(ej: 'Anchor', 'Lyncott', 'Président'). Devuelve proveedores con contexto de precios."
    ),
    args_schema=ProductMarcaArgs,
)
logger.info("🔧 Tool 'buscar_proveedores_marca' registrada")

TOOLS = [buscar_proveedores_tool, buscar_proveedores_marca_tool, mostrar_mas_proveedores_tool, detalle_proveedor_tool]
logger.info(f"✅ Total de tools disponibles: {len(TOOLS)}")
for idx, tool in enumerate(TOOLS, 1):
    logger.debug(f"   {idx}. {tool.name}")

# ========== MODELO ==========
MODEL_NAME = os.getenv("CHAT_MODEL", "gpt-4o-mini")
logger.info(f"🤖 Usando modelo LLM: {MODEL_NAME}")

llm = ChatOpenAI(model=MODEL_NAME).bind_tools(TOOLS)
logger.info(f"✅ LLM inicializado con {len(TOOLS)} tools vinculadas")

# ========== STATE ==========
class MessagesState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]

logger.info("📦 MessagesState definido")

# ========== NODOS ==========
def assistant_node(state: MessagesState) -> dict:
    """Llama al modelo (que ya conoce las tools) y retorna el siguiente mensaje."""
    logger.info("🤖 ═══════════════════════════════════════════════════════")
    logger.info("🤖 NODO: assistant_node - Invocando LLM...")
    logger.debug(f"📥 Estado recibido con {len(state['messages'])} mensaje(s)")
    
    # Log del último mensaje del usuario (si existe)
    if state['messages']:
        last_user_msg = None
        for msg in reversed(state['messages']):
            if hasattr(msg, 'type') and msg.type == 'human':
                last_user_msg = msg
                break
        if last_user_msg:
            logger.info(f"💬 Último mensaje del usuario: '{last_user_msg.content}'")
    
    ai_msg = llm.invoke(state["messages"])
    
    logger.info(f"✅ LLM respondió")
    logger.debug(f"📝 Tipo de respuesta: {type(ai_msg).__name__}")
    
    # Log de tool calls si existen
    tool_calls = getattr(ai_msg, "tool_calls", None)
    if tool_calls:
        tool_names = [tc.get("name", "unknown") for tc in tool_calls]
        logger.info(f"🛠️  LLM solicitó {len(tool_calls)} tool(s): {tool_names}")
        for idx, tc in enumerate(tool_calls, 1):
            logger.debug(f"   {idx}. Tool: {tc.get('name', 'unknown')}")
            logger.debug(f"      Args: {tc.get('args', {})}")
    else:
        logger.info(f"💬 LLM generó respuesta final (sin tool calls)")
        logger.info(f"📄 Respuesta completa del asistente:")
        logger.info(f"{'─' * 60}")
        logger.info(f"{ai_msg.content}")
        logger.info(f"{'─' * 60}")
    
    logger.info("🤖 ═══════════════════════════════════════════════════════")
    return {"messages": [ai_msg]}

# ToolNode ejecuta automáticamente cualquier tool_call del último AIMessage
tool_node = ToolNode(TOOLS)
logger.info("🔧 ToolNode creado con las tools disponibles")

# ========== ENRUTADOR ==========
def router(state: MessagesState):
    """Si el último mensaje del asistente pide tools, vamos a 'tools'; si no, terminamos."""
    logger.info("🔀 ═══════════════════════════════════════════════════════")
    logger.info("🔀 ROUTER: Determinando siguiente nodo...")
    logger.debug(f"📥 Estado con {len(state['messages'])} mensaje(s)")
    
    last = state["messages"][-1]
    logger.debug(f"🔍 Último mensaje: {type(last).__name__}")
    
    tool_calls = getattr(last, "tool_calls", None)
    if tool_calls:
        logger.info(f"🔧 Router: dirigiendo a nodo 'tools' ({len(tool_calls)} tool call(s))")
        logger.debug(f"   Tools a ejecutar: {[tc.get('name', 'unknown') for tc in tool_calls]}")
        logger.info("🔀 ═══════════════════════════════════════════════════════")
        return "tools"
    
    logger.info("🏁 Router: finalizando conversación (END)")
    logger.debug("✅ No hay tool calls pendientes - conversación completa")
    logger.info("🔀 ═══════════════════════════════════════════════════════")
    return END

# ========== GRAFO ==========
logger.info("📊 Construyendo grafo de conversación...")
graph = StateGraph(MessagesState)
graph.add_node("assistant", assistant_node)
logger.debug("   ✓ Nodo 'assistant' agregado")
graph.add_node("tools", tool_node)
logger.debug("   ✓ Nodo 'tools' agregado")

graph.set_entry_point("assistant")               # 1) punto de entrada
logger.debug("   ✓ Entry point configurado: 'assistant'")
graph.add_conditional_edges("assistant", router) # 2) salto a tools o END
logger.debug("   ✓ Conditional edges agregadas: assistant -> router")
graph.add_edge("tools", "assistant")             # 3) vuelta tras ejecutar tools
logger.debug("   ✓ Edge agregada: tools -> assistant")

app = graph.compile()
logger.info("✅ Grafo compilado exitosamente")

# ========== FUNCIONES MULTI-AGENTE ==========

def detectar_intencion(mensaje_usuario: str) -> str:
    """
    Usa el LLM como router para clasificar la intención del usuario.
    Retorna: 'busqueda_proveedores', 'chef', 'nutriologo', 'bartender', 
             'barista', 'ingeniero_alimentos', 'fuera_alcance'
    """
    logger.info(f"🔍 ══════════════════════════════════════════════════════")
    logger.info(f"🔍 DETECTANDO INTENCIÓN")
    logger.info(f"💬 Mensaje: '{mensaje_usuario[:80]}...'")
    
    router_llm = ChatOpenAI(model=MODEL_NAME)
    
    response = router_llm.invoke([
        ("system", SYSTEM_PROMPT_ROUTER),
        ("user", mensaje_usuario)
    ])
    
    intencion = response.content.strip().lower()
    logger.info(f"🎯 Intención detectada: '{intencion}'")
    logger.info(f"🔍 ══════════════════════════════════════════════════════")
    
    return intencion


def responder_como_chef(mensaje: str, history: list) -> tuple[str, list]:
    """Responde como Chef con recetas breves"""
    logger.info(f"👨‍🍳 ══════════════════════════════════════════════════════")
    logger.info(f"👨‍🍳 AGENTE: CHEF")
    logger.debug(f"📝 Mensaje: '{mensaje[:80]}...'")
    
    llm_chef = ChatOpenAI(model=MODEL_NAME)
    response = llm_chef.invoke([
        ("system", SYSTEM_PROMPT_CHEF),
        ("user", mensaje)
    ])
    
    logger.info(f"✅ Chef respondió: {len(response.content)} caracteres")
    logger.info(f"👨‍🍳 ══════════════════════════════════════════════════════")
    
    # Actualizar historial
    new_history = history + [
        ("user", mensaje),
        ("assistant", response.content)
    ]
    
    return response.content, new_history


def responder_como_nutriologo(mensaje: str, history: list) -> tuple[str, list]:
    """Responde como Nutriólogo con info nutricional"""
    logger.info(f"🥗 ══════════════════════════════════════════════════════")
    logger.info(f"🥗 AGENTE: NUTRIÓLOGO")
    logger.debug(f"📝 Mensaje: '{mensaje[:80]}...'")
    
    llm_nutri = ChatOpenAI(model=MODEL_NAME)
    response = llm_nutri.invoke([
        ("system", SYSTEM_PROMPT_NUTRIOLOGO),
        ("user", mensaje)
    ])
    
    logger.info(f"✅ Nutriólogo respondió: {len(response.content)} caracteres")
    logger.info(f"🥗 ══════════════════════════════════════════════════════")
    
    new_history = history + [
        ("user", mensaje),
        ("assistant", response.content)
    ]
    
    return response.content, new_history


def responder_como_bartender(mensaje: str, history: list) -> tuple[str, list]:
    """Responde como Bartender con cócteles"""
    logger.info(f"🍹 ══════════════════════════════════════════════════════")
    logger.info(f"🍹 AGENTE: BARTENDER")
    logger.debug(f"📝 Mensaje: '{mensaje[:80]}...'")
    
    llm_bartender = ChatOpenAI(model=MODEL_NAME)
    response = llm_bartender.invoke([
        ("system", SYSTEM_PROMPT_BARTENDER),
        ("user", mensaje)
    ])
    
    logger.info(f"✅ Bartender respondió: {len(response.content)} caracteres")
    logger.info(f"🍹 ══════════════════════════════════════════════════════")
    
    new_history = history + [
        ("user", mensaje),
        ("assistant", response.content)
    ]
    
    return response.content, new_history


def responder_como_barista(mensaje: str, history: list) -> tuple[str, list]:
    """Responde como Barista con técnicas de café"""
    logger.info(f"☕ ══════════════════════════════════════════════════════")
    logger.info(f"☕ AGENTE: BARISTA")
    logger.debug(f"📝 Mensaje: '{mensaje[:80]}...'")
    
    llm_barista = ChatOpenAI(model=MODEL_NAME)
    response = llm_barista.invoke([
        ("system", SYSTEM_PROMPT_BARISTA),
        ("user", mensaje)
    ])
    
    logger.info(f"✅ Barista respondió: {len(response.content)} caracteres")
    logger.info(f"☕ ══════════════════════════════════════════════════════")
    
    new_history = history + [
        ("user", mensaje),
        ("assistant", response.content)
    ]
    
    return response.content, new_history


def responder_como_ingeniero(mensaje: str, history: list) -> tuple[str, list]:
    """Responde como Ingeniero en Alimentos con conservación"""
    logger.info(f"🔬 ══════════════════════════════════════════════════════")
    logger.info(f"🔬 AGENTE: INGENIERO EN ALIMENTOS")
    logger.debug(f"📝 Mensaje: '{mensaje[:80]}...'")
    
    llm_ingeniero = ChatOpenAI(model=MODEL_NAME)
    response = llm_ingeniero.invoke([
        ("system", SYSTEM_PROMPT_INGENIERO),
        ("user", mensaje)
    ])
    
    logger.info(f"✅ Ingeniero respondió: {len(response.content)} caracteres")
    logger.info(f"🔬 ══════════════════════════════════════════════════════")
    
    new_history = history + [
        ("user", mensaje),
        ("assistant", response.content)
    ]
    
    return response.content, new_history


def responder_fuera_alcance(mensaje: str, history: list) -> tuple[str, list]:
    """Responde cuando la pregunta está fuera de alcance"""
    logger.warning(f"⚠️ ══════════════════════════════════════════════════════")
    logger.warning(f"⚠️  PREGUNTA FUERA DE ALCANCE")
    logger.debug(f"📝 Mensaje: '{mensaje[:80]}...'")
    
    respuesta = (
        "Entiendo tu frustración y lamento no poder ayudarte con esa consulta.\n\n"
        "Si quieres hacer una queja o sugerencia sobre nuestros servicios, "
        f"puedes enviarla a nuestro buzón de quejas: {BUZON_QUEJAS}\n\n"
    )
    
    logger.info(f"✅ Respuesta fuera de alcance enviada")
    logger.warning(f"⚠️ ══════════════════════════════════════════════════════")
    
    new_history = history + [
        ("user", mensaje),
        ("assistant", respuesta)
    ]
    
    return respuesta, new_history

# ========== CLI DEMO ==========
def main():
    logger.info("=" * 60)
    logger.info("🚀 Chat demo iniciado - The Hap & D Company (Multi-Agente)")
    logger.info("=" * 60)
    logger.info(f"🤖 Modelo: {MODEL_NAME}")
    logger.info(f"🔧 Tools disponibles: {len(TOOLS)}")
    logger.info(f"📧 Buzón de quejas: {BUZON_QUEJAS}")
    logger.info(f"🎭 Roles disponibles: Buscador, Chef, Nutriólogo, Bartender, Barista, Ingeniero")
    logger.info("=" * 60)
    
    print("Chat demo. Escribe 'salir' para terminar.")
    # Historial con system prompt
    history = [("system", SYSTEM_PROMPT)]
    logger.info("📋 Historial inicializado con system prompt")
    
    turn_number = 0
    while True:
        q = input("> ").strip()
        if not q:
            continue
        if q.lower() in {"salir", "exit", "quit"}:
            logger.info("👋 Usuario finalizó la sesión")
            logger.info("=" * 60)
            break
        
        turn_number += 1
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"💬 TURNO {turn_number} - Usuario: {q}")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        # PASO 1: Detectar intención del usuario
        intencion = detectar_intencion(q)
        
        # PASO 2: Rutear según la intención detectada
        if intencion == "busqueda_proveedores":
            # Flujo normal con tools (búsqueda de proveedores)
            logger.info(f"🔍 Ruta: BÚSQUEDA DE PROVEEDORES (con tools)")
            history.append(("user", q))
            out = app.invoke({"messages": history})
            last = out["messages"][-1]
            print(last.content)
            history = out["messages"]
            
        elif intencion == "chef":
            # Agente Chef
            logger.info(f"👨‍🍳 Ruta: CHEF (recetas y preparación)")
            respuesta, history = responder_como_chef(q, history)
            print(respuesta)
            
        elif intencion == "nutriologo":
            # Agente Nutriólogo
            logger.info(f"🥗 Ruta: NUTRIÓLOGO (información nutricional)")
            respuesta, history = responder_como_nutriologo(q, history)
            print(respuesta)
            
        elif intencion == "bartender":
            # Agente Bartender
            logger.info(f"🍹 Ruta: BARTENDER (cócteles y bebidas)")
            respuesta, history = responder_como_bartender(q, history)
            print(respuesta)
            
        elif intencion == "barista":
            # Agente Barista
            logger.info(f"☕ Ruta: BARISTA (técnicas de café)")
            respuesta, history = responder_como_barista(q, history)
            print(respuesta)
            
        elif intencion == "ingeniero_alimentos":
            # Agente Ingeniero en Alimentos
            logger.info(f"🔬 Ruta: INGENIERO EN ALIMENTOS (conservación)")
            respuesta, history = responder_como_ingeniero(q, history)
            print(respuesta)
            
        elif intencion == "fuera_alcance":
            # Respuesta para temas fuera del sector gastronómico
            logger.warning(f"⚠️  Ruta: FUERA DE ALCANCE")
            respuesta, history = responder_fuera_alcance(q, history)
            print(respuesta)
            
        else:
            # Fallback si el router devuelve algo inesperado
            logger.error(f"❌ Intención desconocida: '{intencion}'")
            respuesta = "Disculpa, no entendí tu consulta. ¿Puedes reformularla? 😊"
            print(respuesta)
            history.append(("user", q))
            history.append(("assistant", respuesta))
        
        logger.info(f"✅ TURNO {turn_number} completado")
        logger.debug(f"📚 Historial actualizado: {len(history)} mensajes totales")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

logger.info("📦 Módulo chatbot.py cargado completamente")

if __name__ == "__main__":
    main()