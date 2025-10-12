def normalize_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        # Normaliza el esquema y usa psycopg (psycopg3)
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        # Añade driver explícito si falta
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url