# search.py
from sqlalchemy import create_engine, text
import os
import re
import logging
from dotenv import load_dotenv
from utils.embedding_utils import generar_embedding
from utils.normalize_db_url import normalize_db_url  # <- igual que en el otro archivo

# Configurar logging
logger = logging.getLogger(__name__)

load_dotenv()
DATABASE_URL = normalize_db_url(os.getenv("DATABASE_URL"))
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)

# =====================================================
# Utils: WhatsApp multi-número (parseo y normalización)
# =====================================================
_SEP_SPLIT = re.compile(r"[,\n/;|]+")  # separadores comunes: coma, salto de línea, / ; |
_DIGITS = re.compile(r"\D+")

def _split_phones(raw: str | None) -> list[str]:
    """Separa por , ; / | o saltos de línea y limpia espacios."""
    if not raw:
        return []
    return [t.strip() for t in _SEP_SPLIT.split(raw) if t.strip()]

def _only_digits(s: str) -> str:
    """Deja solo dígitos."""
    return _DIGITS.sub("", s or "")

def _normalize_with_cc(digits: str, default_cc: str = "52") -> str:
    """
    Normaliza para wa.me:
    - Si ya trae prefijo país (52 o 521) lo respeta.
    - Si no lo trae y parece local (>=10 dígitos), antepone default_cc (México=52).
    - Si es demasiado corto, lo deja tal cual.
    """
    if not digits:
        return ""
    if digits.startswith("52") or digits.startswith("521"):
        return digits
    if len(digits) >= 10:
        return default_cc + digits
    return digits

def _wa_links_multi(raw: str | None, default_cc: str = "52") -> tuple[list[str], list[str]]:
    """
    Devuelve (numeros_limpios, links_wa) deduplicados manteniendo el orden.
    - numeros_limpios: lista de números solo con dígitos y prefijo país cuando falta.
    - links_wa: lista de 'https://wa.me/<numero_normalizado>'.
    """
    uniq, links, seen = [], [], set()
    for token in _split_phones(raw):
        d = _only_digits(token)
        d = _normalize_with_cc(d, default_cc=default_cc)
        if not d or d in seen:
            continue
        seen.add(d)
        uniq.append(d)
        links.append(f"https://wa.me/{d}")
    return uniq, links


def buscar_productos_mejorado(
    search_query: str,
    top_k: int = 20,
    knn_limit: int = 200,          # candidatos vectoriales antes de fusionar
    threshold_trgm: float = 0.40,  # suele ir bien 0.40-0.50
    threshold_vector: float = 0.75,# si usas cosine, 0.70-0.80 razonable
    w_trgm: float = 0.6,
    w_vec: float = 0.4,
):
    """
    Devuelve:
      - productos: lista de matches ordenada por score (fusión trigram+vector)
      - proveedores: agregación por proveedor (best_score, matches, ejemplos, + info de contacto)
    Requiere extensiones: pg_trgm y vector.
    """
    logger.info(f"🔍 Búsqueda iniciada: query='{search_query}', top_k={top_k}, threshold_trgm={threshold_trgm}, threshold_vector={threshold_vector}")
    
    emb = generar_embedding(search_query)
    logger.debug(f"📊 Embedding generado: dimensión={len(emb)}")

    # Si la consulta es mini, subimos el listón trigram para evitar ruido
    if len(search_query.strip()) <= 3:
        threshold_trgm = max(threshold_trgm, 0.55)
        logger.info(f"⚠️  Query corta detectada, threshold_trgm ajustado a {threshold_trgm}")

    sql = text("""
    WITH trgm AS (
      SELECT
        p.id,
        p.id_producto_csv,
        p.nombre_producto,
        p.marca,
        p.presentacion_venta,
        p.unidad_venta,
        p.precio_unidad,
        p.moneda,
        pr.id_proveedor,
        pr.nombre_comercial,
        pr.nombre_ejecutivo_ventas,
        pr.whatsapp_ventas,
        pr.pagina_web,
        pr.nivel_membresia,
        pr.calificacion_usuarios,
        GREATEST(
          similarity(p.nombre_producto, :q),
          similarity(COALESCE(p.marca, ''), :q),
          similarity(COALESCE(p.cod_producto::text, ''), :q)
        ) AS trgm_sim
      FROM productos p
      JOIN proveedores pr ON p.id_proveedor = pr.id_proveedor
      WHERE (p.nombre_producto % :q
             OR COALESCE(p.marca,'') % :q
             OR COALESCE(p.cod_producto::text,'') % :q)
    ),
    vec AS (
      -- COSINE: sim = 1 - distancia
      SELECT
        p.id,
        p.id_producto_csv,
        p.nombre_producto,
        p.marca,
        p.presentacion_venta,
        p.unidad_venta,
        p.precio_unidad,
        p.moneda,
        pr.id_proveedor,
        pr.nombre_comercial,
        pr.nombre_ejecutivo_ventas,
        pr.whatsapp_ventas,
        pr.pagina_web,
        pr.nivel_membresia,
        pr.calificacion_usuarios,
        1 - (p.embedding <=> CAST(:embedding AS vector)) AS vec_sim
      FROM productos p
      JOIN proveedores pr ON p.id_proveedor = pr.id_proveedor
      ORDER BY p.embedding <=> CAST(:embedding AS vector)
      LIMIT :knn_limit
    ),
    unioned AS (
      SELECT *, trgm_sim AS trgm, 0.0::float AS vec FROM trgm
      UNION ALL
      SELECT *, 0.0::float AS trgm, vec_sim AS vec FROM vec
    ),
    fused AS (
      SELECT
        id,
        id_producto_csv,
        nombre_producto,
        marca,
        presentacion_venta,
        unidad_venta,
        precio_unidad,
        moneda,
        id_proveedor,
        nombre_comercial,
        nombre_ejecutivo_ventas,
        whatsapp_ventas,
        pagina_web,
        nivel_membresia,
        calificacion_usuarios,
        MAX(trgm) AS trgm_sim,
        MAX(vec)  AS vec_sim,
        (:w_trgm * MAX(trgm) + :w_vec * MAX(vec)) AS score
      FROM unioned
      GROUP BY
        id, id_producto_csv, nombre_producto, marca, presentacion_venta, unidad_venta, 
        precio_unidad, moneda, id_proveedor, nombre_comercial, nombre_ejecutivo_ventas, 
        whatsapp_ventas, pagina_web, nivel_membresia, calificacion_usuarios
    ),
    filtered AS (
      SELECT *
      FROM fused
      WHERE (trgm_sim >= :thr_trgm OR vec_sim >= :thr_vec)
    ),
    top_products AS (
      SELECT *
      FROM filtered
      ORDER BY score DESC
      LIMIT :top_k
    )
    SELECT * FROM top_products;
    """)

    with engine.connect() as conn:
        logger.debug("🔌 Ejecutando consulta SQL en la base de datos...")
        prod_rows = conn.execute(
            sql,
            {
                "q": search_query,
                "embedding": emb,
                "knn_limit": knn_limit,
                "w_trgm": w_trgm,
                "w_vec": w_vec,
                "thr_trgm": threshold_trgm,
                "thr_vec": threshold_vector,
                "top_k": top_k,
            },
        ).fetchall()
    
    logger.info(f"✅ Consulta SQL completada: {len(prod_rows)} productos encontrados")

    # ---------------------------------------
    # Productos (nivel item)
    # ---------------------------------------
    productos = []
    for row in prod_rows:
        nums, links = _wa_links_multi(row.whatsapp_ventas)
        productos.append({
            "score": float(row.score),
            "similaridad_trgm": float(row.trgm_sim),
            "similaridad_vector": float(row.vec_sim),
            "producto": row.nombre_producto,
            "marca": row.marca,
            "presentacion_venta": row.presentacion_venta,
            "unidad": row.unidad_venta,
            "precio": row.precio_unidad,
            "moneda": row.moneda,
            "proveedor_id": row.id_proveedor,
            "proveedor": row.nombre_comercial,
            # Info proveedor adjunta por comodidad (no se muestra en vista básica)
            "ejecutivo_ventas": row.nombre_ejecutivo_ventas,
            "whatsapp_ventas_raw": row.whatsapp_ventas,
            "whatsapp_ventas_list": nums,   # lista de números normalizados
            "whatsapp_links": links,        # lista de enlaces wa.me/...
            "pagina_web": row.pagina_web,
            "nivel_membresia": row.nivel_membresia,
            "calificacion_usuarios": row.calificacion_usuarios,
            "id": row.id,
            "id_producto_csv": row.id_producto_csv,
        })
    
    # Log de productos con similitudes
    if productos:
        logger.info(f"📋 Productos encontrados con similitudes:")
        for i, p in enumerate(productos[:10], 1):  # Mostrar solo los top 10 para no saturar
            logger.info(
                f"  {i}. '{p['producto']}' ({p['proveedor']}) - "
                f"Score: {p['score']:.3f} | "
                f"Trgm: {p['similaridad_trgm']:.3f} | "
                f"Vec: {p['similaridad_vector']:.3f}"
            )
        if len(productos) > 10:
            logger.info(f"  ... y {len(productos) - 10} productos más")

    # ---------------------------------------
    # Proveedores (agregado por proveedor)
    # ---------------------------------------
    prov_map: dict[int, dict] = {}
    for r in productos:
        pid = r["proveedor_id"]
        if pid not in prov_map:
            prov_map[pid] = {
                "proveedor_id": pid,
                "proveedor": r["proveedor"],
                # Info de contacto completa para “modo detalle”
                "ejecutivo_ventas": r["ejecutivo_ventas"],
                "whatsapp_ventas_list": list(r["whatsapp_ventas_list"]),
                "whatsapp_links": list(r["whatsapp_links"]),
                "pagina_web": r["pagina_web"],
                "nivel_membresia": r["nivel_membresia"],
                "calificacion_usuarios": r["calificacion_usuarios"],
                # Métricas de ranking/ejemplos
                "best_score": r["score"],
                "matches": 0,
                "ejemplos": [],
            }
        prov = prov_map[pid]
        prov["matches"] += 1
        if len(prov["ejemplos"]) < 3 and r["producto"] not in prov["ejemplos"]:
            prov["ejemplos"].append(r["producto"])
        if r["score"] > prov["best_score"]:
            prov["best_score"] = r["score"]

        # Completa faltantes
        if not prov["ejecutivo_ventas"] and r["ejecutivo_ventas"]:
            prov["ejecutivo_ventas"] = r["ejecutivo_ventas"]
        if not prov["pagina_web"] and r["pagina_web"]:
            prov["pagina_web"] = r["pagina_web"]

        # Fusiona teléfonos/links sin duplicados preservando orden
        for d in r["whatsapp_ventas_list"]:
            if d not in prov["whatsapp_ventas_list"]:
                prov["whatsapp_ventas_list"].append(d)
        for l in r["whatsapp_links"]:
            if l not in prov["whatsapp_links"]:
                prov["whatsapp_links"].append(l)

    # Ordenar proveedores por: nivel_membresia (menor es mejor), calificacion_usuarios (mayor es mejor), best_score, matches
    proveedores = sorted(
        prov_map.values(),
        key=lambda x: (
            x["nivel_membresia"] if x["nivel_membresia"] is not None else 999,  # NULL al final
            -(x["calificacion_usuarios"] if x["calificacion_usuarios"] is not None else 0),  # Calificación DESC
            -x["best_score"],  # Score DESC
            -x["matches"]  # Matches DESC
        ),
    )
    
    logger.info(f"📦 Proveedores únicos encontrados: {len(proveedores)}")
    if proveedores:
        top_3 = proveedores[:3]
        logger.info(f"🏆 Top 3 proveedores: {[p['proveedor'] for p in top_3]}")

    return productos, proveedores


def buscar_proveedores_por_producto(
    product: str,
    top_k: int = 25,
    threshold_trgm: float = 0.55,
    threshold_vector: float = 0.75,
):
    """
    Vista "básica" para el chat:
    - Devuelve proveedores por relevancia con:
        rank, proveedor_id, proveedor, coincidencias, mejor_score, ejemplos
    - Incluye un campo 'contacto_detallado' con TODA la info de contacto (listas),
      para que el chat la use si el usuario pide "más info" (pero sin mostrarla de primeras).
    """
    _, proveedores = buscar_productos_mejorado(
        search_query=product,
        top_k=top_k,
        threshold_trgm=threshold_trgm,
        threshold_vector=threshold_vector,
    )

    salida = []
    for i, p in enumerate(proveedores, 1):
        ejemplos = ", ".join(p["ejemplos"]) if p["ejemplos"] else "—"
        salida.append({
            "rank": i,
            "proveedor_id": p["proveedor_id"],
            "proveedor": p["proveedor"],
            "coincidencias": p["matches"],
            "mejor_score": round(p["best_score"], 3),
            "ejemplos": ejemplos,
            # NO se muestra en la lista básica; queda disponible para el paso de detalle:
            "contacto_detallado": {
                "nombre_ejecutivo_ventas": p["ejecutivo_ventas"],
                "whatsapp_ventas_list": p["whatsapp_ventas_list"],  # lista de números
                "whatsapp_links": p["whatsapp_links"],              # lista de enlaces
                "pagina_web": p["pagina_web"],
            },
        })
    return salida


def buscar_proveedores_con_relevancia(product: str, top_k: int = 25, marca_filtro: str | None = None):
    """
    Búsqueda con sistema de umbrales escalonados:
    
    - Nivel 1 (ALTA RELEVANCIA): trgm >= 0.55 OR vec >= 0.85
      → Productos muy relevantes, coincidencia directa
      
    - Nivel 2 (RELEVANCIA MEDIA): trgm >= 0.50 OR vec >= 0.80
      → Productos similares/alternativos (no tenemos exacto pero ofrecemos similares)
      
    - Nivel 3 (BAJA/NULA RELEVANCIA): No cumple ningún umbral
      → Producto fuera del sector gastronómico
    
    Args:
        product: nombre del producto a buscar
        top_k: número máximo de productos a retornar
        marca_filtro: si se especifica, filtra SOLO productos de esta marca (case-insensitive)
    
    Retorna: (proveedores_list, nivel_relevancia, marcas_disponibles)
      - nivel_relevancia: "alta", "media", "nula"
      - marcas_disponibles: lista de marcas encontradas (para sugerir si hay ambigüedad)
    """
    logger.info(f"🎯 Búsqueda con relevancia escalonada para: '{product}'" + (f" | Marca: '{marca_filtro}'" if marca_filtro else ""))
    
    # NIVEL 1: Umbrales altos (coincidencia directa)
    THRESHOLD_TRGM_HIGH = 0.55
    THRESHOLD_VEC_HIGH = 0.87
    
    productos_high, proveedores_high = buscar_productos_mejorado(
        search_query=product,
        top_k=top_k,
        threshold_trgm=THRESHOLD_TRGM_HIGH,
        threshold_vector=THRESHOLD_VEC_HIGH,
    )
    
    # Aplicar filtro de marca si se especificó
    if marca_filtro:
        marca_lower = marca_filtro.lower().strip()
        productos_high = [
            p for p in productos_high 
            if p.get("marca") and p["marca"].lower().strip() == marca_lower
        ]
        logger.info(f"🏷️  Filtro de marca '{marca_filtro}' aplicado: {len(productos_high)} productos")
    
    # Extraer marcas disponibles (antes de filtrar por relevancia)
    marcas_disponibles = set()
    for p in productos_high:
        marca = p.get("marca")
        if marca and marca.strip() and marca.strip() not in ["—", "N/A", "Sin marca"]:
            marcas_disponibles.add(marca.strip())
    marcas_disponibles = sorted(list(marcas_disponibles))
    
    # Verificar si hay productos que cumplan los umbrales altos
    productos_relevantes_high = [
        p for p in productos_high 
        if p["similaridad_trgm"] >= THRESHOLD_TRGM_HIGH or p["similaridad_vector"] >= THRESHOLD_VEC_HIGH
    ]
    
    if productos_relevantes_high:
        logger.info(f"✅ NIVEL 1 (ALTA): {len(productos_relevantes_high)} productos encontrados con alta relevancia")
        logger.info(f"   Mejores similitudes: Trgm={max(p['similaridad_trgm'] for p in productos_relevantes_high):.3f}, Vec={max(p['similaridad_vector'] for p in productos_relevantes_high):.3f}")
        
        # Reagrupar por proveedor con la info de precios incluida
        salida = _agrupar_proveedores_con_precios(productos_relevantes_high)
        return salida, "alta", marcas_disponibles
    
    # NIVEL 2: Umbrales medios (productos similares/alternativos)
    THRESHOLD_TRGM_MED = 0.50
    THRESHOLD_VEC_MED = 0.83
    
    logger.info(f"⚠️  NIVEL 1 no cumplido, intentando NIVEL 2 (MEDIA)...")
    
    productos_med, proveedores_med = buscar_productos_mejorado(
        search_query=product,
        top_k=top_k,
        threshold_trgm=THRESHOLD_TRGM_MED,
        threshold_vector=THRESHOLD_VEC_MED,
    )
    
    # Aplicar filtro de marca si se especificó
    if marca_filtro:
        marca_lower = marca_filtro.lower().strip()
        productos_med = [
            p for p in productos_med 
            if p.get("marca") and p["marca"].lower().strip() == marca_lower
        ]
        logger.info(f"🏷️  Filtro de marca '{marca_filtro}' aplicado (nivel medio): {len(productos_med)} productos")
    
    # Extraer marcas disponibles
    if not marcas_disponibles:  # Solo si no se encontraron en nivel alto
        for p in productos_med:
            marca = p.get("marca")
            if marca and marca.strip() and marca.strip() not in ["—", "N/A", "Sin marca"]:
                marcas_disponibles.add(marca.strip())
        marcas_disponibles = sorted(list(marcas_disponibles))
    
    productos_relevantes_med = [
        p for p in productos_med 
        if p["similaridad_trgm"] >= THRESHOLD_TRGM_MED or p["similaridad_vector"] >= THRESHOLD_VEC_MED
    ]
    
    if productos_relevantes_med:
        logger.info(f"⚡ NIVEL 2 (MEDIA): {len(productos_relevantes_med)} productos similares encontrados")
        logger.info(f"   Mejores similitudes: Trgm={max(p['similaridad_trgm'] for p in productos_relevantes_med):.3f}, Vec={max(p['similaridad_vector'] for p in productos_relevantes_med):.3f}")
        
        salida = _agrupar_proveedores_con_precios(productos_relevantes_med)
        return salida, "media", marcas_disponibles
    
    # NIVEL 3: Sin coincidencias relevantes (producto fuera del sector)
    logger.warning(f"❌ NIVEL 3 (NULA): No se encontraron productos relevantes para '{product}'")
    return [], "nula", []


def _agrupar_proveedores_con_precios(productos: list[dict]) -> list[dict]:
    """
    Agrupa productos por proveedor e incluye información de precios en el contexto.
    Esta info NO se muestra inicialmente, pero está disponible para el LLM.
    
    Retorna lista de proveedores con:
    - rank, proveedor_id, proveedor, ejemplos
    - contexto_precios: lista de productos con precio, presentación, moneda
    - contacto_detallado: para cuando se solicite
    """
    prov_map: dict[int, dict] = {}
    
    for p in productos:
        pid = p["proveedor_id"]
        
        if pid not in prov_map:
            prov_map[pid] = {
                "proveedor_id": pid,
                "proveedor": p["proveedor"],
                "nivel_membresia": p["nivel_membresia"],
                "calificacion_usuarios": p["calificacion_usuarios"],
                "best_score": p["score"],
                "matches": 0,
                "ejemplos": [],
                "contexto_precios": [],  # Info de precios para el LLM
                "contacto_detallado": {
                    "nombre_ejecutivo_ventas": p["ejecutivo_ventas"],
                    "whatsapp_ventas_list": list(p["whatsapp_ventas_list"]),
                    "whatsapp_links": list(p["whatsapp_links"]),
                    "pagina_web": p["pagina_web"],
                },
            }
        
        prov = prov_map[pid]
        prov["matches"] += 1
        
        # Agregar producto a ejemplos (sin precio)
        if len(prov["ejemplos"]) < 3 and p["producto"] not in prov["ejemplos"]:
            prov["ejemplos"].append(p["producto"])
        
        # Agregar a contexto de precios (CON precio, marca, presentación)
        prov["contexto_precios"].append({
            "producto": p["producto"],
            "marca": p.get("marca"),
            "precio": p.get("precio"),
            "unidad": p.get("unidad"),
            "presentacion_venta": p.get("presentacion_venta"),
            "moneda": p.get("moneda", "MXN"),
                    })
        
        if p["score"] > prov["best_score"]:
            prov["best_score"] = p["score"]
    
    # Ordenar por nivel_membresia y calificacion_usuarios (criterio por defecto)
    proveedores = sorted(
        prov_map.values(),
        key=lambda x: (
            x["nivel_membresia"] if x["nivel_membresia"] is not None else 999,
            -(x["calificacion_usuarios"] if x["calificacion_usuarios"] is not None else 0),
            -x["best_score"],
            -x["matches"]
        ),
    )
    
    # Formatear salida
    salida = []
    for i, p in enumerate(proveedores, 1):
        ejemplos = ", ".join(p["ejemplos"]) if p["ejemplos"] else "—"
        salida.append({
            "rank": i,
            "proveedor_id": p["proveedor_id"],
            "proveedor": p["proveedor"],
            "coincidencias": p["matches"],
            "mejor_score": round(p["best_score"], 3),
            "ejemplos": ejemplos,
            "contexto_precios": p["contexto_precios"],  # Para que LLM pueda usar si se pide
            "contacto_detallado": p["contacto_detallado"],
        })
    
    return salida


def obtener_marcas_disponibles(product: str, top_k: int = 50) -> list[str]:
    """
    Obtiene las marcas disponibles para un producto dado.
    Útil para preguntar al usuario cuando hay ambigüedad.
    
    Retorna: lista de marcas únicas ordenadas alfabéticamente
    """
    logger.info(f"🏷️  ═══════════════════════════════════════════════════════")
    logger.info(f"🏷️  OBTENER MARCAS DISPONIBLES")
    logger.info(f"🏷️  ═══════════════════════════════════════════════════════")
    logger.info(f"🔍 Producto solicitado: '{product}'")
    logger.info(f"📊 Top_k configurado: {top_k}")
    logger.debug(f"⚙️  Umbrales: trgm=0.40, vector=0.70 (bajos para capturar variantes)")
    
    # Búsqueda con umbrales bajos para capturar todas las variantes
    logger.debug(f"🚀 Llamando a buscar_productos_mejorado...")
    productos, _ = buscar_productos_mejorado(
        search_query=product,
        top_k=top_k,
        threshold_trgm=0.40,
        threshold_vector=0.70,
    )
    
    logger.info(f"📦 Productos obtenidos de la búsqueda: {len(productos)}")
    
    # Extraer marcas únicas (excluyendo None y strings vacíos)
    marcas = set()
    productos_con_marca = 0
    productos_sin_marca = 0
    
    for idx, p in enumerate(productos):
        marca = p.get("marca")
        producto_nombre = p.get("producto", "N/A")
        
        if marca and marca.strip() and marca.strip() not in ["—", "N/A", "Sin marca"]:
            marcas.add(marca.strip())
            productos_con_marca += 1
            if idx < 5:  # Log de primeros 5 para debugging
                logger.debug(f"   ✓ Producto {idx+1}: '{producto_nombre}' -> Marca: '{marca.strip()}'")
        else:
            productos_sin_marca += 1
            if idx < 5:
                logger.debug(f"   ✗ Producto {idx+1}: '{producto_nombre}' -> Sin marca válida")
    
    logger.info(f"📊 Estadísticas de marcas:")
    logger.info(f"   • Productos con marca válida: {productos_con_marca}")
    logger.info(f"   • Productos sin marca: {productos_sin_marca}")
    
    marcas_lista = sorted(list(marcas))
    
    logger.info(f"✅ Total de marcas únicas encontradas: {len(marcas_lista)}")
    
    if marcas_lista:
        if len(marcas_lista) <= 15:
            logger.info(f"🏷️  Marcas completas: {marcas_lista}")
        else:
            logger.info(f"🏷️  Primeras 15 marcas: {marcas_lista[:15]}")
            logger.debug(f"🏷️  Marcas restantes ({len(marcas_lista)-15}): {marcas_lista[15:]}")
    else:
        logger.warning(f"⚠️  No se encontraron marcas válidas para '{product}'")
    
    logger.info(f"🏷️  ═══════════════════════════════════════════════════════")
    
    return marcas_lista


# ---------------------------------------
# (Opcional) Obtener detalle por proveedor_id directamente
# ---------------------------------------
def obtener_detalle_proveedor(proveedor_id: int) -> dict | None:
    """
    Devuelve el detalle de contacto de un proveedor por id.
    Útil si al hacer clic en "más info" pasas el proveedor_id desde la vista básica.
    """
    sql = text("""
        SELECT
          id_proveedor,
          nombre_comercial,
          nombre_ejecutivo_ventas,
          whatsapp_ventas,
          pagina_web
        FROM proveedores
        WHERE id_proveedor = :pid
        LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"pid": proveedor_id}).fetchone()

    if not row:
        return None

    numeros, links = _wa_links_multi(row.whatsapp_ventas)
    return {
        "proveedor_id": row.id_proveedor,
        "proveedor": row.nombre_comercial,
        "nombre_ejecutivo_ventas": row.nombre_ejecutivo_ventas,
        "whatsapp_ventas_list": numeros,  # lista normalizada
        "whatsapp_links": links,          # lista de wa.me
        "pagina_web": row.pagina_web,
    }
