# search.py

from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
from utils.embedding_utils import generar_embedding

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)


def buscar_productos(search_query: str, top_k: int = 20, threshold_trgm: float = 0.4, threshold_vector: float = 1.80):
    embedding = generar_embedding(search_query)

    with engine.connect() as conn:
        trgm_sql = text("""
            SELECT p.id_producto, p.nombre_producto, p.marca, p.unidad_venta, p.precio_unidad,
                   pr.nombre_comercial, pr.whatsapp_ventas, pr.pagina_web,
                   similarity(p.nombre_producto, :query) AS sim
            FROM productos p
            JOIN proveedores pr ON p.id_proveedor = pr.id_proveedor
            WHERE p.nombre_producto % :query
            ORDER BY sim DESC
            LIMIT :top_k
        """)
        trgm_results = conn.execute(trgm_sql, {"query": search_query, "top_k": top_k}).fetchall()
        trgm_ids = [row.id_producto for row in trgm_results]

        resultados_trgm = [
            {
                "similaridad": row.sim,
                "producto": row.nombre_producto,
                "marca": row.marca,
                "unidad": row.unidad_venta,
                "precio": row.precio_unidad,
                "proveedor": row.nombre_comercial,
                "contacto": row.whatsapp_ventas or row.pagina_web or "Sin contacto"
            }
            for row in trgm_results if row.sim >= threshold_trgm
        ]

        vector_sql = text("""
            SELECT p.id_producto, p.nombre_producto, p.marca, p.unidad_venta, p.precio_unidad,
                   pr.nombre_comercial, pr.whatsapp_ventas, pr.pagina_web,
                   1 - (p.embedding <#> CAST(:embedding AS vector)) AS similarity
            FROM productos p
            JOIN proveedores pr ON p.id_proveedor = pr.id_proveedor
            WHERE p.id_producto NOT IN :ids
            ORDER BY p.embedding <#> CAST(:embedding AS vector)
            LIMIT :top_k
        """)
        vector_results = conn.execute(
            vector_sql,
            {"embedding": embedding, "top_k": top_k, "ids": tuple(trgm_ids) or (-1,)}
        ).fetchall()

        resultados_vector = [
            {
                "similaridad": row.similarity,
                "producto": row.nombre_producto,
                "marca": row.marca,
                "unidad": row.unidad_venta,
                "precio": row.precio_unidad,
                "proveedor": row.nombre_comercial,
                "contacto": row.whatsapp_ventas or row.pagina_web or "Sin contacto"
            }
            for row in vector_results if row.similarity >= threshold_vector
        ]

        return resultados_trgm, resultados_vector
