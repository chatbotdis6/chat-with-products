"""Tool para buscar proveedores por precio - Optimización de costos."""
import json
import logging
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from chat.services.search_service import SearchService
from chat.config.settings import settings

logger = logging.getLogger(__name__)


class PrecioArgs(BaseModel):
    """Argumentos para la búsqueda de productos por precio."""
    product: str = Field(
        ...,
        description="Nombre del producto a buscar precios (ej. 'pollo entero', 'vino tinto').",
    )
    marca: str = Field(
        default="",
        description="Marca específica (opcional). Si se especifica, filtra solo esa marca.",
    )


def _determinar_grava_iva(impuesto: str) -> bool:
    """
    Determina si un producto grava IVA basándose en el campo impuesto.
    
    Args:
        impuesto: Valor del campo impuesto ("más IVA", "Exento de IVA", etc.)
        
    Returns:
        True si el producto grava IVA, False si está exento
    """
    if not impuesto:
        # Por defecto, asumimos que grava IVA si no hay información
        return True
    
    impuesto_lower = impuesto.lower().strip()
    
    # Patrones que indican que NO grava IVA (exento)
    exento_patterns = [
        "exento", "exenta", "sin iva", "0%", "tasa 0", 
        "no aplica", "n/a", "no grava", "libre"
    ]
    
    for pattern in exento_patterns:
        if pattern in impuesto_lower:
            return False
    
    # Si contiene "más iva", "iva", "+iva", etc. → grava IVA
    return True


def _formatear_precio_con_iva(precio: float, moneda: str, unidad: str, grava_iva: bool) -> str:
    """
    Formatea el precio según si grava IVA o no.
    
    Args:
        precio: Precio numérico
        moneda: Moneda (MXN, USD, etc.)
        unidad: Unidad de venta (kg, L, pza, etc.)
        grava_iva: Si el producto grava IVA
        
    Returns:
        String formateado: "$42/kg" o "$220 + IVA/750ml"
    """
    # Formatear precio sin decimales si es entero
    if precio == int(precio):
        precio_str = f"${int(precio)}"
    else:
        precio_str = f"${precio:.2f}"
    
    # Agregar "+ IVA" si corresponde
    if grava_iva:
        precio_str += " + IVA"
    
    # Agregar unidad
    if unidad:
        # Normalizar unidad
        unidad_clean = unidad.strip()
        precio_str += f"/{unidad_clean}"
    
    return precio_str


def _ordenar_por_membresia_y_precio(productos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ordena productos por membresía/reputación primero, luego por precio.
    
    Criterios:
    1. nivel_membresia (menor = mejor)
    2. calificacion_usuarios (mayor = mejor)  
    3. precio (menor = mejor)
    """
    return sorted(
        productos,
        key=lambda x: (
            x.get("nivel_membresia") if x.get("nivel_membresia") is not None else 999,
            -(x.get("calificacion_usuarios") if x.get("calificacion_usuarios") is not None else 0),
            x.get("precio") if x.get("precio") is not None else float('inf')
        )
    )


def _tool_buscar_proveedores_precio(product: str, marca: str = "") -> str:
    """
    Busca proveedores con precios para un producto específico.
    Formato optimizado para WhatsApp: solo proveedor + precio (+ IVA si aplica).
    
    Args:
        product: Nombre del producto a buscar
        marca: Marca específica (opcional)
        
    Returns:
        JSON con lista de precios formateada para WhatsApp
    """
    logger.info(f"🔧 TOOL LLAMADA: buscar_proveedores_precio(product='{product}', marca='{marca}')")
    
    search_service = SearchService()
    
    # Buscar proveedores con relevancia
    rows, nivel_relevancia, marcas_disponibles = search_service.buscar_proveedores_con_relevancia(
        product=product
    )
    
    logger.info(f"📊 Nivel de relevancia: '{nivel_relevancia}', Proveedores encontrados: {len(rows)}")
    
    # Si no hay resultados
    if nivel_relevancia == "nula" or not rows:
        return json.dumps({
            "nivel_relevancia": nivel_relevancia,
            "mensaje": f"No encontré precios para '{product}'.",
            "precios": [],
            "producto_buscado": product,
            "grava_iva": None
        }, ensure_ascii=False)
    
    # Recopilar todos los productos con precios
    productos_con_precio = []
    
    for proveedor in rows:
        proveedor_nombre = proveedor.get("proveedor", "")
        nivel_membresia = proveedor.get("nivel_membresia")
        calificacion = proveedor.get("calificacion_usuarios")
        
        for ctx_precio in proveedor.get("contexto_precios", []):
            # Filtrar por marca si se especificó
            if marca:
                producto_marca = ctx_precio.get("marca", "") or ""
                if marca.lower() not in producto_marca.lower():
                    continue
            
            precio = ctx_precio.get("precio")
            if precio is None or precio <= 0:
                continue
            
            productos_con_precio.append({
                "proveedor": proveedor_nombre,
                "producto": ctx_precio.get("producto", ""),
                "marca": ctx_precio.get("marca", ""),
                "precio": precio,
                "unidad": ctx_precio.get("unidad", ""),
                "moneda": ctx_precio.get("moneda", "MXN"),
                "impuesto": ctx_precio.get("impuesto", ""),
                "nivel_membresia": nivel_membresia,
                "calificacion_usuarios": calificacion,
            })
    
    if not productos_con_precio:
        return json.dumps({
            "nivel_relevancia": nivel_relevancia,
            "mensaje": f"Encontré proveedores para '{product}' pero no tienen precios registrados.",
            "precios": [],
            "producto_buscado": product,
            "grava_iva": None
        }, ensure_ascii=False)
    
    # Ordenar por membresía/reputación primero, luego por precio
    productos_ordenados = _ordenar_por_membresia_y_precio(productos_con_precio)
    
    # Tomar máximo 5 mejores opciones
    max_precios = 5
    productos_top = productos_ordenados[:max_precios]
    
    # Determinar si el producto grava IVA (usar el primero como referencia)
    grava_iva = _determinar_grava_iva(productos_top[0].get("impuesto", ""))
    
    # Formatear precios para respuesta
    precios_formateados = []
    proveedores_vistos = set()  # Evitar duplicar proveedores
    
    for prod in productos_top:
        proveedor = prod["proveedor"]
        
        # Solo mostrar un precio por proveedor
        if proveedor in proveedores_vistos:
            continue
        proveedores_vistos.add(proveedor)
        
        precio_formateado = _formatear_precio_con_iva(
            precio=prod["precio"],
            moneda=prod["moneda"],
            unidad=prod["unidad"],
            grava_iva=_determinar_grava_iva(prod.get("impuesto", ""))
        )
        
        precios_formateados.append({
            "proveedor": proveedor,
            "precio_formateado": precio_formateado,
            "precio_numerico": prod["precio"],
            "unidad": prod["unidad"],
            "grava_iva": _determinar_grava_iva(prod.get("impuesto", "")),
        })
    
    # Construir nombre del producto para la respuesta
    nombre_producto = product
    if marca:
        nombre_producto = f"{product} {marca}"
    
    # Verificar si todos los productos tienen el mismo estado de IVA
    todos_gravan_iva = all(p["grava_iva"] for p in precios_formateados)
    ninguno_grava_iva = all(not p["grava_iva"] for p in precios_formateados)
    
    resultado = {
        "nivel_relevancia": nivel_relevancia,
        "mensaje": f"Precios actuales de {nombre_producto}:",
        "precios": precios_formateados,
        "producto_buscado": nombre_producto,
        "total_proveedores": len(proveedores_vistos),
        "hay_mas_en_plataforma": len(productos_con_precio) > len(precios_formateados),
        "grava_iva": todos_gravan_iva if todos_gravan_iva or ninguno_grava_iva else "mixto",
        "platform_url": settings.PLATFORM_URL,
    }
    
    logger.info(f"✅ Retornando {len(precios_formateados)} precios (grava_iva={resultado['grava_iva']})")
    return json.dumps(resultado, ensure_ascii=False)


# Crear la tool estructurada
buscar_proveedores_precio_tool = StructuredTool.from_function(
    func=_tool_buscar_proveedores_precio,
    name="buscar_proveedores_precio",
    description=(
        "Busca y compara PRECIOS de un producto específico entre proveedores. "
        "SOLO usar cuando el usuario EXPLÍCITAMENTE pide precio, el más barato, "
        "opciones económicas, o comparar costos. "
        "Devuelve lista con: Proveedor – Precio (+ IVA si aplica). "
        "Siempre invita a ver más en la Plataforma."
    ),
    args_schema=PrecioArgs,
)
