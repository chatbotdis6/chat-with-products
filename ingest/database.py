# ingest/database.py
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import UserDefinedType

# Lee DATABASE_URL del entorno (Heroku la define)
database_url = os.getenv("DATABASE_URL")

# Normaliza prefijo de Heroku para SQLAlchemy si viene como postgres://
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# Tipo VECTOR para pgvector (1536 dims)
class Vector(UserDefinedType):
    def get_col_spec(self):
        return "VECTOR(1536)"

# Crea engine con SSL obligatorio (Heroku)
engine = create_engine(
    database_url,
    pool_pre_ping=True,
    connect_args={"sslmode": "require"}  # clave en Heroku Postgres
)

# Habilita extensiones (idempotente, fuera de transacción)
with engine.connect() as conn:
    conn = conn.execution_options(isolation_level="AUTOCOMMIT")
    conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")

SessionLocal = sessionmaker(bind=engine)
