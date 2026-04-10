"""
Query Node - Text-to-SQL for intelligent database queries.

This node uses LLM (o3-mini) to generate dynamic SQL queries from natural
language, enabling flexible searches like:
- "proveedores de queso con entrega a domicilio"
- "el aceite más barato"
- "productos con precio menor a $500"
"""
import logging
import re
from typing import Dict, Any, List, Optional, Tuple

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Row

from chat.graph.state import (
    ConversationState, 
    NodeOutput,
    SearchResults,
    ProveedorResult,
    RelevanciaLevel,
)
from chat.config.settings import settings
from chat.services.database_service import DatabaseService
from chat.services.data_transformer import DataTransformer
from chat.services.whatsapp_formatter import WhatsAppFormatter
from utils.embedding_utils import generar_embedding

logger = logging.getLogger(__name__)

# Database schema description for Text-to-SQL
DB_SCHEMA = """
TABLAS DISPONIBLES:

1. proveedores:
   - id_proveedor (INTEGER, PK): ID único del proveedor
   - nombre_comercial (TEXT): Nombre comercial del proveedor
   - razon_social (TEXT): Razón social
   - nombre_ejecutivo_ventas (TEXT): Nombre del contacto de ventas
   - whatsapp_ventas (TEXT): Números de WhatsApp (pueden ser múltiples)
   - pagina_web (TEXT): URL de la página web
   - descripcion (TEXT): Descripción del proveedor
   - entregas_domicilio (BOOLEAN): Si hace entregas a domicilio
   - monto_minimo (FLOAT): Monto mínimo de compra
   - ofrece_credito (BOOLEAN): Si ofrece crédito
   - calificacion_usuarios (FLOAT): Calificación de usuarios (0-5)
   - nivel_membresia (FLOAT): Nivel de membresía (mayor = mejor)

2. productos:
   - id (INTEGER, PK): ID único del producto
   - id_proveedor (INTEGER, FK → proveedores.id_proveedor)
   - id_producto_csv (INTEGER): ID original del CSV
   - nombre_producto (TEXT): Nombre del producto
   - marca (TEXT): Marca del producto
   - presentacion_venta (TEXT): Presentación (1kg, 500ml, etc.)
   - precio_unidad (FLOAT): Precio unitario
   - unidad_venta (TEXT): Unidad de venta
   - moneda (TEXT): Moneda (MXN, USD)
   - impuesto (TEXT): "más IVA", "Exento de IVA", etc.
   - categoria_1 (TEXT): Categoría principal
   - categoria_2 (TEXT): Subcategoría
   - vigencia (TEXT): Vigencia del precio
   - embedding (VECTOR(1536)): Embedding para búsqueda semántica

EXTENSIONES DISPONIBLES:
- pg_trgm: Para búsqueda por similitud de texto (similarity function, % operator)
- pgvector: Para búsqueda por embeddings (<=> operator para distancia coseno)

ÍNDICES:
- GIN en nombre_producto para trigram
- IVFFlat en embedding para vector search
"""

TEXT_TO_SQL_PROMPT = """Eres un experto en SQL para PostgreSQL con extensiones pg_trgm y pgvector.

## ESQUEMA DE BASE DE DATOS:
{schema}

## PARÁMETROS DISPONIBLES (usa :nombre_parametro):
- :query = término de búsqueda del usuario (texto)
- :embedding = vector embedding del término (VECTOR(1536))
- :marca = marca específica si se menciona (puede ser NULL)
- :precio_max = precio máximo si se menciona (puede ser NULL)
- :precio_min = precio mínimo si se menciona (puede ser NULL)

## BÚSQUEDA HÍBRIDA (OBLIGATORIO para búsqueda de productos):
Usa SIEMPRE esta estrategia combinando trigram + vector:

```sql
-- Score combinado: 60% trigram + 40% vector
(0.6 * similarity(p.nombre_producto, :query) + 
 0.4 * (1 - (p.embedding <=> CAST(:embedding AS vector)))) AS score
```

Para el WHERE, usa threshold de similitud:
```sql
WHERE similarity(p.nombre_producto, :query) > 0.25
   OR (1 - (p.embedding <=> CAST(:embedding AS vector))) > 0.65
```

## REGLAS OBLIGATORIAS:
1. SOLO genera SELECT queries - NUNCA INSERT, UPDATE, DELETE, DROP
2. SIEMPRE usa búsqueda híbrida (trigram + vector) para productos
3. SIEMPRE incluye JOIN entre productos y proveedores
4. SIEMPRE limita resultados con LIMIT 25
5. Ordena por: score DESC, nivel_membresia DESC
6. Si hay filtro de marca: AND LOWER(p.marca) = LOWER(:marca)
7. Si hay filtro de precio: AND p.precio_unidad <= :precio_max

## COLUMNAS OBLIGATORIAS:
p.id, p.nombre_producto, p.marca, p.presentacion_venta, p.precio_unidad, 
p.moneda, p.impuesto, p.unidad_venta, pr.id_proveedor, pr.nombre_comercial, 
pr.descripcion, pr.nombre_ejecutivo_ventas, pr.whatsapp_ventas, pr.pagina_web,
pr.nivel_membresia, pr.calificacion_usuarios, score

## FORMATO DE RESPUESTA:
Responde SOLO con el SQL. Envuelve en ```sql y ```.

## EJEMPLO COMPLETO:
Usuario: "aceite de oliva"
```sql
SELECT p.id, p.nombre_producto, p.marca, p.presentacion_venta,
       p.precio_unidad, p.moneda, p.impuesto, p.unidad_venta,
       pr.id_proveedor, pr.nombre_comercial, pr.descripcion,
       pr.nombre_ejecutivo_ventas, pr.whatsapp_ventas, pr.pagina_web,
       pr.nivel_membresia, pr.calificacion_usuarios,
       (0.6 * similarity(p.nombre_producto, :query) + 
        0.4 * (1 - (p.embedding <=> CAST(:embedding AS vector)))) AS score
FROM productos p
JOIN proveedores pr ON p.id_proveedor = pr.id_proveedor
WHERE similarity(p.nombre_producto, :query) > 0.25
   OR (1 - (p.embedding <=> CAST(:embedding AS vector))) > 0.65
ORDER BY score DESC, pr.nivel_membresia DESC
LIMIT 25;
```
LIMIT 25;
```"""


class QueryNode:
    """
    Query node that generates and executes SQL queries using LLM.
    
    Uses o3-mini for Text-to-SQL generation, enabling:
    1. Natural language queries ("proveedores con entrega a domicilio")
    2. Complex filters ("precio menor a $500 y marca Anchor")
    3. Fallback to hybrid search if LLM SQL fails
    """
    
    def __init__(self):
        """Initialize the query node."""
        self.db = DatabaseService()
        self.transformer = DataTransformer()
        self.engine = create_engine(
            settings.database_url_normalized,
            pool_pre_ping=settings.POOL_PRE_PING,
            pool_recycle=settings.POOL_RECYCLE
        )
        # LLM for Text-to-SQL
        # Note: o3/o3-mini don't support temperature parameter
        model_name = settings.SQL_MODEL
        if model_name.startswith("o3"):
            self.sql_llm = ChatOpenAI(model=model_name)
        else:
            self.sql_llm = ChatOpenAI(model=model_name, temperature=0)
        logger.info(f"✅ QueryNode inicializado con SQL_MODEL={settings.SQL_MODEL}")
    
    def _generate_sql_with_llm(
        self,
        user_query: str,
        entities: Dict[str, Any],
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Generate SQL query using LLM (o3-mini) with hybrid search parameters.
        
        Args:
            user_query: Natural language query from user
            entities: Extracted entities (producto, marca, precio, etc.)
            
        Returns:
            Tuple of (SQL query, parameters dict) or None if generation fails
        """
        # Get search term and generate embedding
        search_term = entities.get("producto") or user_query
        try:
            embedding = generar_embedding(search_term)
            embedding_str = str(embedding)  # Convert list to string for SQL
        except Exception as e:
            logger.error(f"❌ Error generando embedding: {e}")
            return None
        
        # Build parameters dict
        params = {
            "search_term": search_term,
            "embedding": embedding_str,
        }
        
        # Build context from entities
        context_parts = []
        if entities.get("producto"):
            context_parts.append(f"Producto/Término de búsqueda: {entities['producto']}")
        if entities.get("marca"):
            context_parts.append(f"Marca: {entities['marca']}")
            params["marca"] = entities['marca']
        if entities.get("precio_max"):
            context_parts.append(f"Precio máximo: ${entities['precio_max']}")
            params["precio_max"] = float(entities['precio_max'])
        if entities.get("precio_min"):
            context_parts.append(f"Precio mínimo: ${entities['precio_min']}")
            params["precio_min"] = float(entities['precio_min'])
        if entities.get("busca_precio"):
            context_parts.append("El usuario quiere ver precios (ordenar por precio)")
        
        context = "\n".join(context_parts) if context_parts else "Sin filtros específicos"
        
        # Show which parameters are available
        available_params = list(params.keys())
        params_info = f"Parámetros disponibles: {', '.join([':' + p for p in available_params])}"
        
        prompt = f"""## CONSULTA DEL USUARIO:
"{user_query}"

## ENTIDADES EXTRAÍDAS:
{context}

## PARÁMETROS PARA TU SQL:
{params_info}

IMPORTANTE: Usa :search_term y :embedding para la búsqueda híbrida (trigram + vector).
Genera el SQL para buscar productos/proveedores según esta consulta."""

        try:
            logger.info(f"🤖 Generando SQL con {settings.SQL_MODEL}...")
            logger.debug(f"📝 Parámetros: {list(params.keys())}")
            
            response = self.sql_llm.invoke([
                SystemMessage(content=TEXT_TO_SQL_PROMPT.format(schema=DB_SCHEMA)),
                HumanMessage(content=prompt)
            ])
            
            # Extract SQL from response
            sql = self._extract_sql_from_response(response.content)
            
            if sql:
                logger.info(f"✅ SQL generado: {sql[:100]}...")
                return (sql, params)
            else:
                logger.warning("⚠️  No se pudo extraer SQL de la respuesta")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error generando SQL: {e}")
            return None
    
    def _extract_sql_from_response(self, response: str) -> Optional[str]:
        """Extract SQL from LLM response (handles ```sql blocks)."""
        # Try to extract from code block
        sql_match = re.search(r'```sql\s*(.*?)\s*```', response, re.DOTALL | re.IGNORECASE)
        if sql_match:
            return sql_match.group(1).strip()
        
        # Try plain code block
        code_match = re.search(r'```\s*(.*?)\s*```', response, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()
        
        # Check if response itself looks like SQL
        if response.strip().upper().startswith('SELECT'):
            return response.strip()
        
        return None
    
    def _validate_sql(self, sql: str) -> bool:
        """Validate that SQL is safe to execute (only SELECT)."""
        sql_upper = sql.upper().strip()
        
        # Must start with SELECT
        if not sql_upper.startswith('SELECT'):
            logger.warning("❌ SQL no comienza con SELECT")
            return False
        
        # Block dangerous keywords
        dangerous = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE', 'ALTER', 'CREATE', 'GRANT', 'REVOKE']
        for keyword in dangerous:
            if keyword in sql_upper:
                logger.warning(f"❌ SQL contiene keyword peligroso: {keyword}")
                return False
        
        return True
    
    def _execute_llm_sql(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Row]:
        """Execute LLM-generated SQL safely with parameters."""
        if not self._validate_sql(sql):
            return []
        
        try:
            with self.engine.connect() as conn:
                if params:
                    # Bind parameters to the query
                    logger.debug(f"📊 Ejecutando SQL con parámetros: {list(params.keys())}")
                    rows = conn.execute(text(sql), params).fetchall()
                else:
                    rows = conn.execute(text(sql)).fetchall()
            logger.info(f"✅ SQL ejecutado: {len(rows)} resultados")
            return rows
        except Exception as e:
            logger.error(f"❌ Error ejecutando SQL: {e}")
            logger.error(f"SQL: {sql[:200]}...")
            if params:
                logger.error(f"Params keys: {list(params.keys())}")
            return []
    
    def _execute_hybrid_search(
        self,
        search_query: str,
        marca: Optional[str] = None,
        precio_max: Optional[float] = None,
        precio_min: Optional[float] = None,
        top_k: int = 25,
    ) -> List[Row]:
        """
        Execute hybrid search with optional filters.
        
        This combines trigram similarity + vector similarity with
        optional filters for marca and precio.
        """
        logger.info(f"🔍 Executing hybrid search: '{search_query}'")
        if marca:
            logger.info(f"   📍 Filter: marca='{marca}'")
        if precio_max:
            logger.info(f"   📍 Filter: precio_max={precio_max}")
        if precio_min:
            logger.info(f"   📍 Filter: precio_min={precio_min}")
        
        # Generate embedding for vector search
        embedding = generar_embedding(search_query)
        
        # Build dynamic WHERE clause for filters
        filter_clauses = []
        params = {
            "q": search_query,
            "embedding": embedding,
            "knn_limit": settings.DEFAULT_KNN_LIMIT,
            "w_trgm": settings.WEIGHT_TRGM,
            "w_vec": settings.WEIGHT_VEC,
            "thr_trgm": settings.THRESHOLD_TRGM_HIGH,
            "thr_vec": settings.THRESHOLD_VEC_HIGH,
            "top_k": top_k,
        }
        
        # Add marca filter
        marca_filter_trgm = ""
        marca_filter_vec = ""
        if marca:
            marca_filter_trgm = "AND LOWER(p.marca) = LOWER(:marca)"
            marca_filter_vec = "AND LOWER(p.marca) = LOWER(:marca)"
            params["marca"] = marca
        
        # Add precio filters
        precio_filter = ""
        if precio_max is not None:
            precio_filter += " AND p.precio_unidad <= :precio_max"
            params["precio_max"] = precio_max
        if precio_min is not None:
            precio_filter += " AND p.precio_unidad >= :precio_min"
            params["precio_min"] = precio_min
        
        sql = text(f"""
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
            p.impuesto,
            pr.id_proveedor,
            pr.nombre_comercial,
            pr.nombre_ejecutivo_ventas,
            pr.whatsapp_ventas,
            pr.pagina_web,
            pr.descripcion,
            pr.nivel_membresia,
            pr.calificacion_usuarios,
            GREATEST(
              similarity(p.nombre_producto, :q),
              similarity(COALESCE(p.marca, ''), :q)
            ) AS trgm_sim
          FROM productos p
          JOIN proveedores pr ON p.id_proveedor = pr.id_proveedor
          WHERE (p.nombre_producto % :q OR COALESCE(p.marca,'') % :q)
            {marca_filter_trgm}
            {precio_filter}
        ),
        vec AS (
          SELECT
            p.id,
            p.id_producto_csv,
            p.nombre_producto,
            p.marca,
            p.presentacion_venta,
            p.unidad_venta,
            p.precio_unidad,
            p.moneda,
            p.impuesto,
            pr.id_proveedor,
            pr.nombre_comercial,
            pr.nombre_ejecutivo_ventas,
            pr.whatsapp_ventas,
            pr.pagina_web,
            pr.descripcion,
            pr.nivel_membresia,
            pr.calificacion_usuarios,
            1 - (p.embedding <=> CAST(:embedding AS vector)) AS vec_sim
          FROM productos p
          JOIN proveedores pr ON p.id_proveedor = pr.id_proveedor
          WHERE 1=1
            {marca_filter_vec}
            {precio_filter}
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
            impuesto,
            id_proveedor,
            nombre_comercial,
            nombre_ejecutivo_ventas,
            whatsapp_ventas,
            pagina_web,
            descripcion,
            nivel_membresia,
            calificacion_usuarios,
            MAX(trgm) AS trgm_sim,
            MAX(vec)  AS vec_sim,
            (:w_trgm * MAX(trgm) + :w_vec * MAX(vec)) AS score
          FROM unioned
          GROUP BY
            id, id_producto_csv, nombre_producto, marca, presentacion_venta, unidad_venta, 
            precio_unidad, moneda, impuesto, id_proveedor, nombre_comercial, nombre_ejecutivo_ventas, 
            whatsapp_ventas, pagina_web, descripcion, nivel_membresia, calificacion_usuarios
        ),
        filtered AS (
          SELECT *
          FROM fused
          WHERE (trgm_sim >= :thr_trgm OR vec_sim >= :thr_vec)
        )
        SELECT * FROM filtered
        ORDER BY score DESC
        LIMIT :top_k;
        """)
        
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        
        logger.info(f"✅ Hybrid search returned {len(rows)} products")
        return rows
    
    def _execute_price_search(
        self,
        search_query: str,
        marca: Optional[str] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Execute price-focused search that returns products sorted by price.
        """
        logger.info(f"💰 Executing price search: '{search_query}'")
        
        embedding = generar_embedding(search_query)
        
        params = {
            "q": search_query,
            "embedding": embedding,
            "top_k": top_k,
        }
        
        marca_filter = ""
        if marca:
            marca_filter = "AND LOWER(p.marca) = LOWER(:marca)"
            params["marca"] = marca
        
        sql = text(f"""
        SELECT 
            p.id,
            p.nombre_producto,
            p.marca,
            p.presentacion_venta,
            p.precio_unidad,
            p.moneda,
            p.impuesto,
            pr.id_proveedor,
            pr.nombre_comercial,
            pr.nivel_membresia,
            (0.6 * similarity(p.nombre_producto, :q) +
             0.4 * (1 - (p.embedding <=> CAST(:embedding AS vector)))) AS relevance_score
        FROM productos p
        JOIN proveedores pr ON p.id_proveedor = pr.id_proveedor
        WHERE (similarity(p.nombre_producto, :q) > 0.3 OR 
               (1 - (p.embedding <=> CAST(:embedding AS vector))) > 0.82)
          AND p.precio_unidad IS NOT NULL
          AND p.precio_unidad > 0
          AND (0.6 * similarity(p.nombre_producto, :q) +
               0.4 * (1 - (p.embedding <=> CAST(:embedding AS vector)))) > 0.6
          {marca_filter}
        ORDER BY precio_unidad ASC
        LIMIT :top_k;
        """)
        
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        
        # Format for price display
        precios = []
        for row in rows:
            moneda = row.moneda or "MXN"
            if moneda.upper() == "PMX":
                moneda = "MXN"
            precio_str = f"${row.precio_unidad:,.2f} {moneda}"
            if row.impuesto and "IVA" in row.impuesto.upper():
                precio_str += " + IVA"
            
            precios.append({
                "proveedor": row.nombre_comercial,
                "proveedor_id": row.id_proveedor,
                "producto": row.nombre_producto,
                "marca": row.marca,
                "presentacion": row.presentacion_venta,
                "precio_formateado": precio_str,
                "precio_unidad": row.precio_unidad,
                "grava_iva": "IVA" in (row.impuesto or "").upper(),
            })
        
        logger.info(f"✅ Price search returned {len(precios)} prices")
        return precios
    
    def _get_provider_detail(self, proveedor_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed provider information."""
        sql = text("""
            SELECT
              pr.id_proveedor,
              pr.nombre_comercial,
              pr.nombre_ejecutivo_ventas,
              pr.whatsapp_ventas,
              pr.pagina_web,
              pr.descripcion,
              pr.nivel_membresia,
              pr.calificacion_usuarios
            FROM proveedores pr
            WHERE pr.id_proveedor = :pid
            LIMIT 1
        """)
        
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"pid": proveedor_id}).fetchone()
        
        if not row:
            return None
        
        numeros, links = WhatsAppFormatter.format_numbers(row.whatsapp_ventas)
        
        return {
            "proveedor_id": row.id_proveedor,
            "proveedor": row.nombre_comercial,
            "descripcion": row.descripcion,
            "nombre_ejecutivo_ventas": row.nombre_ejecutivo_ventas,
            "whatsapp_ventas_list": numeros,
            "whatsapp_links": links,
            "pagina_web": row.pagina_web,
            "nivel_membresia": row.nivel_membresia,
            "calificacion_usuarios": row.calificacion_usuarios,
        }
    
    def _rows_to_search_results(
        self,
        rows: List[Row],
        nivel_relevancia: str,
        show_max: int = 3
    ) -> SearchResults:
        """Convert database rows to SearchResults format."""
        # Transform rows to productos format
        productos = [self.transformer.row_to_producto(row) for row in rows]
        
        # Group by provider with price context
        proveedores = self.transformer.proveedores_con_precios(productos)
        
        # Extract unique brands
        marcas = self.transformer.extract_marcas(productos)
        
        # Determine how many to show
        total_proveedores = len(proveedores)
        proveedores_mostrados = proveedores[:show_max]
        proveedores_ocultos = total_proveedores - len(proveedores_mostrados)
        
        # Format for output
        proveedores_formatted: List[ProveedorResult] = []
        for i, p in enumerate(proveedores_mostrados, 1):
            # Handle ejemplos - can be list or already a string
            ejemplos_raw = p.get("ejemplos", [])
            if isinstance(ejemplos_raw, list):
                ejemplos = ", ".join(ejemplos_raw) if ejemplos_raw else "—"
            else:
                ejemplos = ejemplos_raw if ejemplos_raw else "—"
            
            # Get provider description (key is 'descripcion_proveedor' in transformer)
            descripcion = p.get("descripcion_proveedor") or p.get("descripcion") or "—"
            
            proveedores_formatted.append(ProveedorResult(
                rank=i,
                proveedor_id=p["proveedor_id"],
                proveedor=p["proveedor"],
                descripcion=descripcion,
                ejemplos=ejemplos,
                coincidencias=p.get("matches", 0),
                mejor_score=round(p.get("best_score", 0), 3),
                contexto_precios=p.get("contexto_precios", []),
            ))
        
        # Store hidden provider IDs
        hidden_ids = [p["proveedor_id"] for p in proveedores[show_max:]]
        
        # Generate message based on relevancia
        if nivel_relevancia == RelevanciaLevel.ALTA.value:
            mensaje = f"Encontré {total_proveedores} proveedores con ese producto."
        elif nivel_relevancia == RelevanciaLevel.MEDIA.value:
            mensaje = "No encontré ese producto exacto, pero tengo alternativas similares."
        else:
            mensaje = "No encontré productos que coincidan con tu búsqueda."
        
        return SearchResults(
            nivel_relevancia=nivel_relevancia,
            mensaje=mensaje,
            proveedores_mostrados=len(proveedores_mostrados),
            proveedores_ocultos=proveedores_ocultos,
            proveedores=proveedores_formatted,
            marcas_disponibles=marcas,
        ), hidden_ids


# Singleton instance
_query_node = QueryNode()


def _get_provider_detail(node: QueryNode, proveedor_nombre: str) -> NodeOutput:
    """
    Get detailed information about a specific provider.
    
    Args:
        node: QueryNode instance
        proveedor_nombre: Name of the provider to look up
        
    Returns:
        NodeOutput with provider details
    """
    logger.info(f"📋 Looking up provider: {proveedor_nombre}")
    
    sql = text("""
        SELECT 
            pr.id_proveedor,
            pr.nombre_comercial,
            pr.descripcion,
            pr.nombre_ejecutivo_ventas,
            pr.whatsapp_ventas,
            pr.pagina_web,
            pr.nivel_membresia,
            pr.calificacion_usuarios,
            similarity(pr.nombre_comercial, :nombre) as sim
        FROM proveedores pr
        WHERE similarity(pr.nombre_comercial, :nombre) > 0.3
        ORDER BY similarity(pr.nombre_comercial, :nombre) DESC
        LIMIT 1
    """)
    
    try:
        with node.engine.connect() as conn:
            row = conn.execute(sql, {"nombre": proveedor_nombre}).fetchone()
        
        if row:
            # Format WhatsApp numbers using proper formatter
            whatsapp_raw = row.whatsapp_ventas or ""
            whatsapp_list, whatsapp_links = WhatsAppFormatter.format_numbers(whatsapp_raw)
            
            provider_detail = {
                "proveedor_id": row.id_proveedor,
                "nombre": row.nombre_comercial,
                "descripcion": row.descripcion or "Sin descripción disponible",
                "ejecutivo_ventas": row.nombre_ejecutivo_ventas or "No especificado",
                "whatsapp_ventas": whatsapp_list,
                "whatsapp_links": whatsapp_links,
                "pagina_web": row.pagina_web or "No disponible",
                "nivel_membresia": row.nivel_membresia or 0,
                "calificacion": row.calificacion_usuarios or 0,
            }
            
            logger.info(f"✅ Found provider: {row.nombre_comercial}")
            
            return {
                "search_results": None,
                "nivel_relevancia": RelevanciaLevel.ALTA.value,
                "response_metadata": {"provider_detail": provider_detail},
            }
        else:
            logger.warning(f"⚠️  Provider not found: {proveedor_nombre}")
            return {
                "search_results": None,
                "nivel_relevancia": RelevanciaLevel.NULA.value,
                "response_metadata": {"provider_not_found": proveedor_nombre},
            }
            
    except Exception as e:
        logger.error(f"❌ Error looking up provider: {e}")
        return {
            "search_results": None,
            "nivel_relevancia": "",
            "error": str(e),
        }


def query_node(state: ConversationState) -> NodeOutput:
    """
    Query node that searches the database based on extracted entities.
    
    Strategy:
    1. First, try LLM-generated SQL (o3-mini) for flexible queries
    2. If LLM SQL fails or returns no results, fallback to hybrid search
    
    Args:
        state: Current conversation state with entities from router
        
    Returns:
        Updated state with search results
    """
    logger.info("🗄️  ════════════════════════════════════════════════════")
    logger.info("🗄️  QUERY NODE - Text-to-SQL with LLM")
    
    intent = state.get("intent", "")
    entities = state.get("entities", {})
    search_filters = state.get("search_filters", {})
    messages = state.get("messages", [])
    
    # Get the user's original message for context
    user_message = ""
    if messages:
        for msg in reversed(messages):
            if hasattr(msg, 'type') and msg.type == 'human':
                user_message = msg.content
                break
            elif hasattr(msg, 'role') and msg.role == 'user':
                user_message = msg.content
                break
    
    producto = search_filters.get("producto") or entities.get("producto", "")
    marca = search_filters.get("marca") or entities.get("marca")
    precio_max = search_filters.get("precio_max") or entities.get("precio_max")
    precio_min = search_filters.get("precio_min") or entities.get("precio_min")
    busca_precio = entities.get("busca_precio", False)
    proveedor_nombre = entities.get("proveedor_nombre")
    
    # Use db_action for sub-intent routing (replaces old intent names)
    db_action = state.get("db_action", "")
    
    # If db_action is filter_price, force busca_precio = True
    if db_action == "filter_price":
        busca_precio = True
    
    # Check if filtering by price without product - use last searched product
    if db_action == "filter_price" and not producto:
        # Try to get from last_search_query first (most reliable)
        last_query = state.get("last_search_query", "")
        if last_query:
            producto = last_query
            logger.info(f"📊 Reusing last_search_query for price filter: '{producto}'")
        elif search_filters.get("producto"):
            producto = search_filters.get("producto", "")
            logger.info(f"📊 Reusing search_filters.producto for price filter: '{producto}'")
    
    logger.info(f"📦 Product: '{producto}' | Brand: {marca} | Price query: {busca_precio}")
    logger.info(f"💬 User message: '{user_message[:80]}...'" if len(user_message) > 80 else f"💬 User message: '{user_message}'")
    
    # Handle special db_actions
    if db_action == "detail" and proveedor_nombre:
        logger.info(f"📋 Getting provider detail for: {proveedor_nombre}")
        return _get_provider_detail(_query_node, proveedor_nombre)
    
    if db_action == "show_more":
          pending = state.get("pending_providers", [])
          prev_search_query = state.get("last_search_query", "")
          
          if not pending and not prev_search_query:
              return {
                  "search_results": None,
                  "nivel_relevancia": "",
                  "response": "No hay más proveedores para mostrar."
              }
          
          if pending:
              # Re-execute search and show the next batch from pending IDs
              logger.info(f"📋 Showing {len(pending)} more providers from pending")
              try:
                  sql = text("""
                      SELECT DISTINCT ON (pr.id_proveedor)
                          0 AS id, 0 AS id_producto_csv,
                          '' AS nombre_producto, '' AS marca,
                          '' AS presentacion_venta, '' AS unidad_venta,
                          0.0 AS precio_unidad, 'MXN' AS moneda, '' AS impuesto,
                          pr.id_proveedor, pr.nombre_comercial,
                          pr.nombre_ejecutivo_ventas, pr.whatsapp_ventas,
                          pr.pagina_web, pr.descripcion,
                          pr.nivel_membresia, pr.calificacion_usuarios,
                          0.0 AS trgm_sim, 0.0 AS vec_sim, 0.0 AS score
                      FROM proveedores pr
                      WHERE pr.id_proveedor = ANY(:ids)
                      ORDER BY pr.id_proveedor
                  """)
                  with _query_node.engine.connect() as conn:
                      rows = conn.execute(sql, {"ids": pending}).fetchall()
                  
                  if rows:
                      # Build provider results
                      proveedores_formatted = []
                      for i, row in enumerate(rows, 1):
                          proveedores_formatted.append(ProveedorResult(
                              rank=i,
                              proveedor_id=row.id_proveedor,
                              proveedor=row.nombre_comercial,
                              descripcion=row.descripcion or "—",
                              ejemplos="—",
                              coincidencias=0,
                              mejor_score=0,
                              contexto_precios=[],
                          ))
                      
                      search_results = SearchResults(
                          nivel_relevancia=RelevanciaLevel.ALTA.value,
                          mensaje=f"Aquí tienes {len(rows)} proveedores más.",
                          proveedores_mostrados=len(rows),
                          proveedores_ocultos=0,
                          proveedores=proveedores_formatted,
                          marcas_disponibles=[],
                      )
                      return {
                          "search_results": search_results,
                          "nivel_relevancia": RelevanciaLevel.ALTA.value,
                          "pending_providers": [],
                          "search_filters": state.get("search_filters", {}),
                      }
              except Exception as e:
                  logger.error(f"❌ Error showing more providers: {e}")
          
          # Fallback: re-run search with higher show_max
          if prev_search_query:
              logger.info(f"🔄 Re-running search for '{prev_search_query}' with show_max=10")
              rows = _query_node._execute_hybrid_search(
                  search_query=prev_search_query,
                  marca=marca,
              )
              if rows:
                  search_results, hidden_ids = _query_node._rows_to_search_results(
                      rows, RelevanciaLevel.ALTA.value, show_max=10
                  )
                  return {
                      "search_results": search_results,
                      "nivel_relevancia": RelevanciaLevel.ALTA.value,
                      "pending_providers": hidden_ids,
                      "search_filters": state.get("search_filters", {}),
                  }
          
          return {
              "search_results": None,
              "nivel_relevancia": "",
              "response": "No hay más proveedores para mostrar en este momento.",
          }    # No product to search
    if not producto and not user_message:
        logger.warning("⚠️  No product or message for search")
        return {
            "search_results": None,
            "nivel_relevancia": "",
            "requires_search": False,
        }
    
    try:
        # PRIORITY: If user explicitly asks for prices, use price search directly
        if (busca_precio or db_action == "filter_price") and producto:
            logger.info(f"💰 User requested prices for '{producto}' - using price search")
            precios = _query_node._execute_price_search(producto, marca)
            
            if precios:
                # Save search context for follow-up
                updated_filters = {
                    "producto": producto,
                    "marca": marca,
                    "precio_max": precio_max,
                    "precio_min": precio_min,
                }
                
                return {
                    "search_results": SearchResults(
                        nivel_relevancia=RelevanciaLevel.ALTA.value,
                        mensaje=f"Encontré {len(precios)} precios para {producto}.",
                        proveedores_mostrados=len(precios),
                        proveedores_ocultos=0,
                        proveedores=[],
                        marcas_disponibles=[],
                    ),
                    "nivel_relevancia": RelevanciaLevel.ALTA.value,
                    "pending_providers": [],
                    "search_filters": updated_filters,
                    "response_metadata": {"precios": precios, "producto": producto},
                }
            else:
                logger.info("⚠️  Price search returned no results, falling back to standard search")
        
        rows = []
        nivel = RelevanciaLevel.NULA.value
        used_llm_sql = False
        
        # Data-driven relevance threshold.
        # Empirical analysis: legit matches score >= 0.65, false positives < 0.55
        RELEVANCE_THRESHOLD = 0.55
        
        # STRATEGY 1: Try LLM-generated SQL first
        search_context = user_message or producto
        if search_context:
            logger.info("🤖 Attempting Text-to-SQL with LLM...")
            
            result = _query_node._generate_sql_with_llm(search_context, entities)
            
            if result:
                sql, params = result
                rows = _query_node._execute_llm_sql(sql, params)
                if rows:
                    # Post-filter: discard individual rows below the threshold
                    # (prevents false positives like "Fibra Negra" matching "trufa negra")
                    original_count = len(rows)
                    rows = [
                        row for row in rows
                        if hasattr(row, 'score') and float(row.score) >= RELEVANCE_THRESHOLD
                    ]
                    
                    if not rows:
                        logger.info(
                            f"⚠️  LLM SQL returned {original_count} rows but ALL scores "
                            f"< {RELEVANCE_THRESHOLD} → false positives, discarding"
                        )
                    else:
                        best_score = max(float(row.score) for row in rows)
                        if len(rows) < original_count:
                            logger.info(
                                f"✅ LLM SQL: {original_count} → {len(rows)} rows after threshold filter "
                                f"(best_score={best_score:.3f}, threshold={RELEVANCE_THRESHOLD})"
                            )
                        else:
                            logger.info(f"✅ LLM SQL returned {len(rows)} results (best_score={best_score:.3f})")
                        nivel = RelevanciaLevel.ALTA.value
                        used_llm_sql = True
                else:
                    logger.info("⚠️  LLM SQL returned no results, trying fallback...")
        
        # STRATEGY 2: Fallback to hybrid search if LLM failed
        if not rows and producto:
            logger.info("🔄 Fallback to hybrid search...")
            
            # Price-focused search (secondary attempt)
            if busca_precio or db_action == "filter_price":
                precios = _query_node._execute_price_search(producto, marca)
                
                if precios:
                    return {
                        "search_results": SearchResults(
                            nivel_relevancia=RelevanciaLevel.ALTA.value,
                            mensaje=f"Encontré {len(precios)} precios para {producto}.",
                            proveedores_mostrados=len(precios),
                            proveedores_ocultos=0,
                            proveedores=[],
                            marcas_disponibles=[],
                        ),
                        "nivel_relevancia": RelevanciaLevel.ALTA.value,
                        "pending_providers": [],
                        "response_metadata": {"precios": precios},
                    }
            
            # Standard hybrid search
            rows = _query_node._execute_hybrid_search(
                search_query=producto,
                marca=marca,
                precio_max=precio_max,
                precio_min=precio_min,
            )
            
            # If no results with marca filter, retry without it
            if not rows and marca:
                logger.info(f"⚠️  No results with marca='{marca}', retrying without marca filter...")
                rows = _query_node._execute_hybrid_search(
                    search_query=producto,
                    marca=None,
                    precio_max=precio_max,
                    precio_min=precio_min,
                )
            
            if rows:
                # Filter individual rows below threshold (same as LLM SQL)
                original_count = len(rows)
                rows = [
                    row for row in rows
                    if hasattr(row, 'score') and float(row.score) >= RELEVANCE_THRESHOLD
                ]
                if not rows:
                    logger.info(
                        f"⚠️  Hybrid search {original_count} rows ALL below "
                        f"{RELEVANCE_THRESHOLD} → false positives, discarding"
                    )
                else:
                    nivel = RelevanciaLevel.ALTA.value
            else:
                # Try with lower thresholds (MEDIA level)
                logger.info("⚠️  No results with high thresholds, trying MEDIA level...")
                
                with _query_node.engine.connect() as conn:
                    embedding = generar_embedding(producto)
                    sql_media = text("""
                    WITH candidates AS (
                      SELECT
                        p.id, p.id_producto_csv, p.nombre_producto, p.marca,
                        p.presentacion_venta, p.unidad_venta, p.precio_unidad,
                        p.moneda, p.impuesto,
                        pr.id_proveedor, pr.nombre_comercial, pr.nombre_ejecutivo_ventas,
                        pr.whatsapp_ventas, pr.pagina_web, pr.descripcion,
                        pr.nivel_membresia, pr.calificacion_usuarios,
                        GREATEST(
                          similarity(p.nombre_producto, :q),
                          similarity(COALESCE(p.marca, ''), :q)
                        ) AS trgm_sim,
                        1 - (p.embedding <=> CAST(:embedding AS vector)) AS vec_sim,
                        (0.6 * GREATEST(similarity(p.nombre_producto, :q), similarity(COALESCE(p.marca, ''), :q)) + 
                         0.4 * (1 - (p.embedding <=> CAST(:embedding AS vector)))) AS score
                      FROM productos p
                      JOIN proveedores pr ON p.id_proveedor = pr.id_proveedor
                      WHERE similarity(p.nombre_producto, :q) > 0.25
                         OR (1 - (p.embedding <=> CAST(:embedding AS vector))) > 0.65
                    )
                    SELECT * FROM candidates
                    ORDER BY score DESC
                    LIMIT 25;
                    """)
                    rows = conn.execute(sql_media, {"q": producto, "embedding": embedding}).fetchall()
                
                if rows:
                    # Filter individual rows below threshold (same as LLM SQL)
                    original_count = len(rows)
                    rows = [
                        row for row in rows
                        if hasattr(row, 'score') and float(row.score) >= RELEVANCE_THRESHOLD
                    ]
                    if not rows:
                        logger.info(
                            f"⚠️  MEDIA fallback {original_count} rows ALL below "
                            f"{RELEVANCE_THRESHOLD} → false positives, discarding"
                        )
                        nivel = RelevanciaLevel.NULA.value
                    else:
                        nivel = RelevanciaLevel.MEDIA.value
                else:
                    nivel = RelevanciaLevel.NULA.value
        
        # Convert to search results
        if rows:
            search_results, hidden_ids = _query_node._rows_to_search_results(rows, nivel)
        else:
            search_results = SearchResults(
                nivel_relevancia=nivel,
                mensaje="No encontré productos que coincidan.",
                proveedores_mostrados=0,
                proveedores_ocultos=0,
                proveedores=[],
                marcas_disponibles=[],
            )
            hidden_ids = []
        
        logger.info(f"✅ Search complete: {search_results['proveedores_mostrados']} shown, "
                   f"{search_results['proveedores_ocultos']} hidden, nivel={nivel}, llm_sql={used_llm_sql}")
        logger.info("🗄️  ════════════════════════════════════════════════════")
        
        # Save product in search_filters for follow-up queries
        updated_filters = {
            "producto": producto or user_message,
            "marca": marca,
            "precio_max": precio_max,
            "precio_min": precio_min,
        }
        
        return {
            "search_results": search_results,
            "nivel_relevancia": nivel,
            "pending_providers": hidden_ids,
            "last_search_query": producto or user_message,
            "search_filters": updated_filters,
            "response_metadata": {"used_llm_sql": used_llm_sql},
        }
        
    except Exception as e:
        logger.error(f"❌ Query error: {e}", exc_info=True)
        return {
            "search_results": None,
            "nivel_relevancia": "",
            "error": str(e),
            "error_node": "query",
        }
