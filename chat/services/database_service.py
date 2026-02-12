"""Servicio de base de datos para búsquedas - Separation of Concerns."""
import logging
from typing import List, Tuple
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Row

from chat.config.settings import settings
from utils.embedding_utils import generar_embedding

logger = logging.getLogger(__name__)


class DatabaseService:
    """Servicio para operaciones de base de datos - Interface Segregation Principle."""
    
    def __init__(self):
        """Inicializa el servicio de base de datos."""
        self.engine = create_engine(
            settings.database_url_normalized,
            pool_pre_ping=settings.POOL_PRE_PING,
            pool_recycle=settings.POOL_RECYCLE
        )
        logger.info("✅ DatabaseService inicializado")
    
    def search_products(
        self,
        search_query: str,
        top_k: int,
        knn_limit: int,
        threshold_trgm: float,
        threshold_vector: float,
        w_trgm: float,
        w_vec: float,
    ) -> List[Row]:
        """
        Realiza búsqueda híbrida (trigram + vector) en la base de datos.
        
        Args:
            search_query: Consulta de búsqueda
            top_k: Número máximo de resultados
            knn_limit: Límite de candidatos vectoriales
            threshold_trgm: Umbral de similitud trigram
            threshold_vector: Umbral de similitud vectorial
            w_trgm: Peso para similitud trigram
            w_vec: Peso para similitud vectorial
            
        Returns:
            Lista de filas con productos encontrados
        """
        logger.debug("🔌 Ejecutando consulta SQL en la base de datos...")
        
        emb = generar_embedding(search_query)
        
        # Si la consulta es mini, subimos el listón trigram
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
          WHERE (p.nombre_producto % :q
                 OR COALESCE(p.marca,'') % :q)
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
        ),
        top_products AS (
          SELECT *
          FROM filtered
          ORDER BY score DESC
          LIMIT :top_k
        )
        SELECT * FROM top_products;
        """)
        
        with self.engine.connect() as conn:
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
        return prod_rows
    
    def get_proveedor_detalle(self, proveedor_id: int) -> Row | None:
        """
        Obtiene los detalles de un proveedor por su ID.
        
        Args:
            proveedor_id: ID del proveedor
            
        Returns:
            Fila con información del proveedor o None
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
        
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"pid": proveedor_id}).fetchone()
        
        return row
