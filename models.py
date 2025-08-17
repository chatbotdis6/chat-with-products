from sqlalchemy import (
    Column, Integer, Float, Boolean, Date, ForeignKey, JSON, Text,
    UniqueConstraint, Index, DateTime, func
)
from sqlalchemy.orm import declarative_base
from ingest.database import Vector  # Tipo personalizado pgvector (VECTOR(1536))

Base = declarative_base()


class Proveedor(Base):
    __tablename__ = 'proveedores'

    id_proveedor = Column(Integer, primary_key=True)  # viene de proveedores.csv
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

    # PK artificial
    id = Column(Integer, primary_key=True)

    # Claves de negocio
    id_proveedor = Column(Integer, ForeignKey('proveedores.id_proveedor'), nullable=False)
    # id del producto tal y como viene en el CSV diario
    id_producto_csv = Column(Integer, nullable=False)

    # Datos del producto
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

    # Embedding (1536 dims)
    embedding = Column(Vector)

    __table_args__ = (
        # Un producto único por proveedor + id_producto_csv
        UniqueConstraint('id_proveedor', 'id_producto_csv', name='uq_prod_proveedor_prodid'),
        Index('ix_prod_id_proveedor', 'id_proveedor'),
    )


class IngestedFile(Base):
    """
    Registro de ficheros (S3) ya procesados para no reingestar el mismo
    archivo si el job se relanza. Se usa la pareja (s3_key, etag).
    """
    __tablename__ = 'ingested_files'

    id = Column(Integer, primary_key=True)
    s3_key = Column(Text, nullable=False)
    etag = Column(Text, nullable=False)
    processed_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('s3_key', 'etag', name='uq_ingested_s3key_etag'),
    )
