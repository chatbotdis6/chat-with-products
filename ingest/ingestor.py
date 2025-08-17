# ingest/ingestor.py
import os
import pandas as pd
import logging
import sys
from pathlib import Path
import unicodedata
import glob

from sqlalchemy.exc import SQLAlchemyError
import dateparser

project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from models import Proveedor, Producto, Base
from ingest.database import engine, SessionLocal
from utils.embedding_utils import generar_embedding

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Utilidades robustas ---
def limpiar_booleano(valor):
    if pd.isna(valor):
        return False
    valor = str(valor).strip().casefold()
    valor = unicodedata.normalize("NFKD", valor).encode("ASCII", "ignore").decode("utf-8")
    return valor == "si"

def parse_fecha_espanol(fecha_str):
    if pd.isna(fecha_str):
        return None
    return dateparser.parse(str(fecha_str), languages=["es"])

def parse_precio(valor) -> float:
    try:
        val = str(valor).strip().replace("$", "").replace(" ", "").replace(",", ".")
        return float(val)
    except:
        logging.warning(f"Precio inválido '{valor}'")
        return None

def to_float(val):
    try:
        return float(val)
    except:
        return 0.0

def to_int(val):
    try:
        return int(val)
    except:
        return 0

# --- Clase de Ingestión ---
class CSVIngestor:
    def __init__(self, proveedores_file: str, productos_dir: str):
        self.proveedores_file = proveedores_file
        self.productos_dir = productos_dir
        self.session = SessionLocal()

    def create_tables(self):
        logging.info("Creando tablas si no existen...")
        # NO hacer drop_all en producción
        Base.metadata.create_all(engine)

    def reset_database(self):
        logging.info("Eliminando datos existentes de las tablas...")
        try:
            self.session.query(Producto).delete()
            self.session.query(Proveedor).delete()
            self.session.commit()
            logging.info("Tablas vaciadas correctamente.")
        except SQLAlchemyError as e:
            self.session.rollback()
            logging.error(f"Error al resetear la base de datos: {e}")

    def load_csv(self, path: str) -> pd.DataFrame:
        logging.info(f"Cargando archivo: {path}")
        return pd.read_csv(path, encoding="latin1")

    def insert_proveedores(self, df: pd.DataFrame):
        logging.info("Insertando proveedores...")
        for _, row in df.iterrows():
            try:
                proveedor = Proveedor(
                    id_proveedor=to_int(row.get("id_proveedor")),
                    nombre_comercial=row.get("nombre_comercial"),
                    razon_social=row.get("razon_social"),
                    nombre_ejecutivo_ventas=row.get("nombre_ejecutivo_ventas"),
                    whatsapp_ventas=str(row.get("whatsapp_ventas")).strip(),
                    pagina_web=row.get("pagina_web"),
                    entregas_domicilio=limpiar_booleano(row.get("entregas_domicilio")),
                    monto_minimo=to_float(row.get("monto_minimo")),
                    ofrece_credito=limpiar_booleano(row.get("ofrece_credito")),
                    calificacion_usuarios=to_float(row.get("calificacion_usuarios")),
                    nivel_membresia=to_int(row.get("nivel_membresia")),
                )
                self.session.add(proveedor)
            except Exception as e:
                logging.warning(f"Error procesando proveedor: {e}")
        try:
            self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            logging.error(f"Error al insertar proveedores: {e}")

    def insert_productos(self, df_prod: pd.DataFrame):
        for idx, row in df_prod.iterrows():
            try:
                proveedor_id = row.get("id_proveedor")
                if pd.isna(proveedor_id):
                    logging.warning(f"[Fila {idx}] id_proveedor no especificado, producto omitido.")
                    continue

                precio = parse_precio(row.get("precio_unidad"))

                categorias = [
                    row.get("categoria_1"),
                    row.get("categoria_2"),
                    row.get("categoria_3"),
                    row.get("categoria_4"),
                    row.get("categoria_5")
                ]
                categorias = [cat for cat in categorias if cat and isinstance(cat, str)]

                nombre_producto = row.get("nombre_producto") or ""
                texto_embedding = f"{nombre_producto}"
                embedding = generar_embedding(texto_embedding)

                logging.info(
                    f"[Fila {idx}] Insertando producto: '{nombre_producto}', marca='{row.get('marca')}', precio={precio}, proveedor_id={proveedor_id}"
                )

                producto = Producto(
                    id_proveedor=to_int(proveedor_id),
                    nombre_producto=nombre_producto,
                    cod_producto=row.get("cod_producto"),
                    marca=row.get("marca"),
                    presentacion_venta=row.get("presentacion_venta"),
                    unidad_venta=row.get("unidad_venta"),
                    precio_unidad=precio if precio is not None else 0.0,
                    moneda=row.get("moneda"),
                    categorias=categorias,
                    ultima_actualizacion=parse_fecha_espanol(row.get("ultima_actualizacion")),
                    vigencia=row.get("vigencia"),
                    proveedor=row.get("proveedor"),
                    embedding=embedding
                )

                self.session.add(producto)
                self.session.commit()

            except Exception as e:
                logging.exception(f"[Fila {idx}] Error al insertar producto '{row.get('nombre_producto')}': {e}")
                self.session.rollback()

    def insert_productos_from_all_files(self):
        pattern = Path(self.productos_dir) / "*_productos.csv"
        archivos = glob.glob(str(pattern))
        for filepath in archivos:
            try:
                filename = Path(filepath).stem
                id_str = filename.split("_")[0]
                id_proveedor = int(id_str)
                logging.info(f"Cargando productos del proveedor {id_proveedor} desde '{filepath}'")
                df = pd.read_csv(filepath, encoding="latin1")
                df["id_proveedor"] = id_proveedor
                self.insert_productos(df)
            except Exception as e:
                logging.exception(f"Error procesando archivo '{filepath}': {e}")
        logging.info("Ingestión completada.")
