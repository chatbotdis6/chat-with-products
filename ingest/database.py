import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import UserDefinedType

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Define el tipo VECTOR para SQLAlchemy
class Vector(UserDefinedType):
    def get_col_spec(self):
        return "VECTOR(1536)"

# Crea el engine
engine = create_engine(DATABASE_URL)

# Asegura que la extensión pgvector está habilitada
with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))


# Crea sesión
SessionLocal = sessionmaker(bind=engine)
