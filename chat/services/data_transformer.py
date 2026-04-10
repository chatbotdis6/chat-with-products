"""Transformador de datos de productos y proveedores - Single Responsibility."""
import logging
from typing import List, Dict, Any
from sqlalchemy.engine import Row

from chat.models.types import ProductoInfo, ProveedorInfo
from chat.services.whatsapp_formatter import WhatsAppFormatter

logger = logging.getLogger(__name__)


class DataTransformer:
    """Transforma datos de la base de datos a estructuras tipadas."""
    
    @staticmethod
    def row_to_producto(row: Row) -> ProductoInfo:
        """
        Convierte una fila de BD a ProductoInfo.
        
        Handles both hybrid search results (with trgm_sim, vec_sim, score)
        and LLM-generated SQL results (which may lack these columns).
        """
        nums, links = WhatsAppFormatter.format_numbers(row.whatsapp_ventas)
        
        # Handle optional similarity columns (LLM SQL may not include them)
        score = getattr(row, 'score', None) or 0.5  # Default score for LLM results
        trgm_sim = getattr(row, 'trgm_sim', None) or 0.0
        vec_sim = getattr(row, 'vec_sim', None) or 0.0
        
        return ProductoInfo(
            score=float(score),
            similaridad_trgm=float(trgm_sim),
            similaridad_vector=float(vec_sim),
            producto=row.nombre_producto,
            marca=row.marca,
            presentacion_venta=row.presentacion_venta,
            unidad=getattr(row, 'unidad_venta', None),
            precio=row.precio_unidad,
            moneda=row.moneda,
            impuesto=getattr(row, 'impuesto', None),  # Campo de IVA
            proveedor_id=row.id_proveedor,
            proveedor=row.nombre_comercial,
            descripcion_proveedor=getattr(row, 'descripcion', None),
            ejecutivo_ventas=getattr(row, 'nombre_ejecutivo_ventas', None),
            whatsapp_ventas_raw=getattr(row, 'whatsapp_ventas', None),
            whatsapp_ventas_list=nums,
            whatsapp_links=links,
            pagina_web=getattr(row, 'pagina_web', None),
            nivel_membresia=getattr(row, 'nivel_membresia', 0),
            calificacion_usuarios=getattr(row, 'calificacion_usuarios', 0),
            id=row.id,
            id_producto_csv=getattr(row, 'id_producto_csv', None),
        )
    
    @staticmethod
    def proveedores_con_precios(productos: List[ProductoInfo]) -> List[ProveedorInfo]:
        """
        Agrupa productos por proveedor incluyendo contexto de precios.
        
        Args:
            productos: Lista de productos
            
        Returns:
            Lista de proveedores con contexto de precios
        """
        prov_map: Dict[int, Dict[str, Any]] = {}
        
        for p in productos:
            pid = p["proveedor_id"]
            
            if pid not in prov_map:
                prov_map[pid] = {
                    "proveedor_id": pid,
                    "proveedor": p["proveedor"],
                    "descripcion_proveedor": p.get("descripcion_proveedor"),
                    "ejecutivo_ventas": p["ejecutivo_ventas"],
                    "whatsapp_ventas_list": list(p["whatsapp_ventas_list"]),
                    "whatsapp_links": list(p["whatsapp_links"]),
                    "pagina_web": p["pagina_web"],
                    "nivel_membresia": p["nivel_membresia"],
                    "calificacion_usuarios": p["calificacion_usuarios"],
                    "best_score": p["score"],
                    "matches": 0,
                    "ejemplos": [],
                    "contexto_precios": [],
                }
            
            prov = prov_map[pid]
            prov["matches"] += 1
            
            # Agregar producto a ejemplos (sin precio)
            max_ejemplos = 3
            if len(prov["ejemplos"]) < max_ejemplos and p["producto"] not in prov["ejemplos"]:
                prov["ejemplos"].append(p["producto"])
            
            # Agregar a contexto de precios (CON precio, marca, presentación, impuesto)
            prov["contexto_precios"].append({
                "producto": p["producto"],
                "marca": p.get("marca"),
                "precio": p.get("precio"),
                "unidad": p.get("unidad"),
                "presentacion_venta": p.get("presentacion_venta"),
                "moneda": p.get("moneda", "MXN"),
                "impuesto": p.get("impuesto"),
            })
            
            # Actualizar best_score
            if p["score"] > prov["best_score"]:
                prov["best_score"] = p["score"]
        
        # Ordenar proveedores
        proveedores = sorted(
            prov_map.values(),
            key=lambda x: (
                x["nivel_membresia"] if x["nivel_membresia"] is not None else 999,
                -(x["calificacion_usuarios"] if x["calificacion_usuarios"] is not None else 0),
                -x["best_score"],
                -x["matches"]
            ),
        )
        
        # Agregar rank después de ordenar y convertir ejemplos a string
        for idx, prov in enumerate(proveedores, start=1):
            prov["rank"] = idx
            # Convertir ejemplos de lista a string separado por comas
            if isinstance(prov["ejemplos"], list):
                prov["ejemplos"] = ", ".join(prov["ejemplos"])
        
        return proveedores
    
    @staticmethod
    def extract_marcas(productos: List[ProductoInfo]) -> List[str]:
        """
        Extrae marcas únicas de una lista de productos.
        
        Args:
            productos: Lista de productos
            
        Returns:
            Lista de marcas únicas ordenadas
        """
        marcas = set()
        
        for p in productos:
            marca = p.get("marca")
            if marca and marca.strip() and marca.strip() not in ["—", "N/A", "Sin marca"]:
                marcas.add(marca.strip())
        
        return sorted(list(marcas))
