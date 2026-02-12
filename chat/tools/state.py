"""Estado global para proveedores pendientes - Singleton Pattern."""
from typing import Dict, List, Any


class ProveedoresPendientesState:
    """Gestiona el estado de proveedores pendientes por sesión."""
    
    _instance = None
    _proveedores_pendientes: Dict[str, List[Any]] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def set_pendientes(self, key: str, proveedores: List[Any]) -> None:
        """Guarda proveedores pendientes para una búsqueda."""
        self._proveedores_pendientes[key.lower()] = proveedores
    
    def get_pendientes(self, key: str) -> List[Any]:
        """Obtiene proveedores pendientes de una búsqueda."""
        return self._proveedores_pendientes.get(key.lower(), [])
    
    def clear_pendientes(self, key: str) -> None:
        """Limpia proveedores pendientes de una búsqueda."""
        key_lower = key.lower()
        if key_lower in self._proveedores_pendientes:
            self._proveedores_pendientes[key_lower] = []
    
    def has_pendientes(self, key: str) -> bool:
        """Verifica si hay proveedores pendientes para una búsqueda."""
        return bool(self.get_pendientes(key))


# Instancia global
proveedores_state = ProveedoresPendientesState()
