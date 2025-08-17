# ingest/database.py
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import UserDefinedType

database_url = os.getenv("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

class Vector(UserDefinedType):
    cache_ok = True  # importante para SQLAlchemy 2.x

    def get_col_spec(self):
        return "VECTOR(1536)"

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            # Esperamos una lista/iterable de números -> '[v1, v2, ...]'
            try:
                return "[" + ", ".join(str(float(x)) for x in value) + "]"
            except Exception:
                # Si el embedding viene corrupto, guarda NULL
                return None
        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            # pgvector devuelve como texto '[...]'; si lo quisieras de vuelta como lista, parsea aquí.
            return value
        return process

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    connect_args={"sslmode": "require"}
)

# Extensiones
with engine.connect() as conn:
    conn = conn.execution_options(isolation_level="AUTOCOMMIT")
    conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")

SessionLocal = sessionmaker(bind=engine)
