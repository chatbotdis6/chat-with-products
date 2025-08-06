from sqlalchemy import Column, Integer, Float, Boolean, Date, ForeignKey, JSON, Text
from sqlalchemy.orm import declarative_base
from ingest.database import Vector  # Importa el tipo personalizado para pgvector

Base = declarative_base()

class Proveedor(Base):
    __tablename__ = 'proveedores'

    id_proveedor = Column(Integer, primary_key=True)
    nombre_comercial = Column(Text)
    razon_social = Column(Text)
    nombre_ejecutivo_ventas = Column(Text)
    whatsapp_ventas = Column(Text)
    pagina_web = Column(Text)
    entregas_domicilio = Column(Boolean)
    monto_minimo = Column(Float)
    ofrece_credito = Column(Boolean)
    calificacion_usuarios = Column(Float)
    nivel_membresia = Column(Float)

class Producto(Base):
    __tablename__ = 'productos'

    id_producto = Column(Integer, primary_key=True)
    id_proveedor = Column(Integer, ForeignKey('proveedores.id_proveedor'))
    nombre_producto = Column(Text)
    cod_producto = Column(Text)
    marca = Column(Text)
    presentacion_venta = Column(Text)
    unidad_venta = Column(Text)
    precio_unidad = Column(Float)
    moneda = Column(Text)
    categorias = Column(JSON)
    ultima_actualizacion = Column(Date)
    vigencia = Column(Text)
    proveedor = Column(Text)
    
    # Campo para almacenar el embedding del producto (1536 dimensiones por defecto para OpenAI Ada)
    embedding = Column(Vector)
