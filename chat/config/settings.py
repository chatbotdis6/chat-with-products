"""Configuración del sistema - Principio Single Responsibility."""
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Configuración centralizada de la aplicación."""
    
    # LLM Configuration
    CHAT_MODEL: str = os.getenv("CHAT_MODEL", "gpt-5")  # Conversación natural y creativa
    ROUTER_MODEL: str = os.getenv("ROUTER_MODEL", "gpt-4o")  # Clasificación + extracción entidades
    SQL_MODEL: str = os.getenv("SQL_MODEL", "o3-mini")  # Text-to-SQL (razonamiento sobre estructura)
    
    # Business Configuration
    BUZON_QUEJAS: str = os.getenv("BUZON_QUEJAS", "fake_buzon@gmail.com")
    PLATFORM_URL: str = os.getenv("PLATFORM_URL", "https://konekt.com")
    
    # Search Configuration - Alta relevancia
    THRESHOLD_TRGM_HIGH: float = 0.55
    THRESHOLD_VEC_HIGH: float = 0.87
    
    # Search Configuration - Media relevancia
    THRESHOLD_TRGM_MED: float = 0.50
    THRESHOLD_VEC_MED: float = 0.83
    
    # Search Configuration - Defaults
    DEFAULT_THRESHOLD_TRGM: float = 0.40
    DEFAULT_THRESHOLD_VECTOR: float = 0.75
    
    # Search Configuration - Weights
    WEIGHT_TRGM: float = 0.6
    WEIGHT_VEC: float = 0.4
    
    # Search Configuration - Limits
    DEFAULT_TOP_K: int = 20
    DEFAULT_KNN_LIMIT: int = 200
    MAX_PROVEEDORES_MOSTRADOS: int = 3
    MAX_EJEMPLOS_POR_PROVEEDOR: int = 3
    
    # Platform Transition Configuration
    CONSULTAS_ANTES_SUGERENCIA: int = 2  # Después de 2 consultas, sugerir plataforma
    CONSULTAS_ANTES_DERIVACION: int = 4  # Después de 4 consultas, derivar con LLM (turno 5)
    CONSULTAS_ANTES_PLANTILLA: int = 5   # Después de 5 consultas, usar plantilla fija (turno 6+)
    
    # Database Configuration
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
    POOL_PRE_PING: bool = True
    POOL_RECYCLE: int = 1800
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
    
    @property
    def database_url_normalized(self) -> str:
        """Normaliza la URL de la base de datos."""
        from utils.normalize_db_url import normalize_db_url
        return normalize_db_url(self.DATABASE_URL)


settings = Settings()
