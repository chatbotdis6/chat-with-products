"""Tools del chatbot."""
from .buscar_proveedores_tool import buscar_proveedores_tool
from .buscar_proveedores_marca_tool import buscar_proveedores_marca_tool
from .buscar_proveedores_precio_tool import buscar_proveedores_precio_tool
from .mostrar_mas_proveedores_tool import mostrar_mas_proveedores_tool
from .detalle_proveedor_tool import detalle_proveedor_tool

# Lista de todas las tools disponibles
TOOLS = [
    buscar_proveedores_tool,
    buscar_proveedores_marca_tool,
    buscar_proveedores_precio_tool,
    mostrar_mas_proveedores_tool,
    detalle_proveedor_tool,
]

__all__ = [
    "buscar_proveedores_tool",
    "buscar_proveedores_marca_tool",
    "buscar_proveedores_precio_tool",
    "mostrar_mas_proveedores_tool",
    "detalle_proveedor_tool",
    "TOOLS",
]
