# main.py
import os
import logging
from io import BytesIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # requiere 'tzdata' en requirements
import boto3
import pandas as pd

# Carga .env solo en local (no afecta en Heroku)
from dotenv import load_dotenv
load_dotenv()

from ingest.ingestor import CSVIngestor

BUCKET_NAME = "supplier-catalogs-2025"
PROVEEDORES_KEY = "data/proveedores.csv"
PRODUCTOS_PREFIX = "data/"  # se esperan archivos *_productos_YYYY_MM_DD.csv

# Zona horaria de referencia para “hoy”
JOB_TZ = os.getenv("JOB_TZ", "Europe/Madrid")


def hoy_str(tz_name: str = JOB_TZ) -> str:
    """Devuelve AYER como 'YYYY_MM_DD' en la zona horaria indicada."""
    dt = datetime.now(ZoneInfo(tz_name)) - timedelta(days=1)
    return dt.strftime("%Y_%m_%d")


def descargar_csv_desde_s3(s3_client, bucket, key) -> pd.DataFrame:
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(BytesIO(obj["Body"].read()), encoding="latin1")


def get_etag(s3_client, bucket, key) -> str:
    """ETag sin comillas para deduplicar por contenido."""
    head = s3_client.head_object(Bucket=bucket, Key=key)
    return head["ETag"].strip('"')


def listar_archivos_productos_hoy(s3_client, bucket, prefix, tz_name: str = JOB_TZ):
    """Devuelve keys que acaban en '_productos_YYYY_MM_DD.csv' (solo hoy)."""
    fecha = hoy_str(tz_name)
    keys = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for c in page.get("Contents", []):
            k = c["Key"]
            if k.endswith(f"_productos_{fecha}.csv"):
                keys.append(k)
    return keys


# --- NUEVO: util para listar TODOS los CSVs de productos ---
def listar_archivos_productos_todos(s3_client, bucket, prefix):
    """Devuelve todas las keys de productos bajo el prefijo indicado.
    Criterio: termina en .csv y contiene '_productos_'.
    """
    keys = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for c in page.get("Contents", []):
            k = c["Key"]
            if k.endswith(".csv") and "_productos_" in k:
                keys.append(k)
    return keys


# --- NUEVO: método para ingerir todos los ficheros si run=True ---
def ingest_all_product_files(run: bool, s3_client, bucket: str, prefix: str,
                             proveedores_validos: set[int], ingestor: CSVIngestor):
    """Ingesta todos los CSVs de productos encontrados si run=True; si run=False, no hace nada."""
    if not run:
        logging.info("ingest_all_product_files: run=False → no se ingesta nada.")
        return

    archivos = listar_archivos_productos_todos(s3_client, bucket, prefix)
    logging.info(f"Archivos totales para ingesta: {len(archivos)}")

    if not archivos:
        logging.info("No se encontraron CSVs de productos para ingerir.")
        return

    for key in archivos:
        try:
            filename = key.split("/")[-1]
            proveedor_id = int(filename.split("_")[0])  # prefijo del filename

            # Validación contra proveedores.csv
            if proveedor_id not in proveedores_validos:
                logging.warning(
                    f"[{key}] id_proveedor {proveedor_id} no está en proveedores.csv. Se omite.")
                continue

            etag = get_etag(s3_client, bucket, key)
            if ingestor.was_file_ingested(key, etag):
                logging.info(f"Saltando (ya ingerido) {key} ({etag})")
                continue

            df_productos = descargar_csv_desde_s3(s3_client, bucket, key)

            # Validación mínima
            if "id_producto" not in df_productos.columns:
                logging.error(f"[{key}] Falta columna 'id_producto'; se omite el archivo.")
                continue

            # Sincroniza productos del proveedor (insert/update/delete)
            ingestor.sync_productos_from_csv(df_productos, proveedor_id)

            # Marca como procesado
            ingestor.mark_file_ingested(key, etag)

        except Exception as e:
            logging.error(f"Error procesando '{key}': {e}", exc_info=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    s3_client = boto3.client("s3")

    # Instancia ingestor y crea tablas (sin drop)
    ingestor = CSVIngestor(proveedores_file=None, productos_dir=None)
    ingestor.create_tables()

    # Reset controlado por variable de entorno (¡cuidado en prod!)
    if os.getenv("RESET_DB", "").lower() == "true":
        ingestor.reset_database()

    # 1) Upsert de proveedores desde proveedores.csv
    try:
        df_proveedores = descargar_csv_desde_s3(s3_client, BUCKET_NAME, PROVEEDORES_KEY)
        ingestor.upsert_proveedores(df_proveedores)
        proveedores_validos = set(
            pd.to_numeric(df_proveedores["id_proveedor"], errors="coerce")
            .dropna()
            .astype(int)
            .tolist()
        )
    except Exception as e:
        logging.warning(f"No se pudo procesar 'proveedores.csv': {e}")
        df_proveedores = None
        proveedores_validos = set()

    # 2) Productos: según variable de entorno
    ingest_all_days = os.getenv("INGEST_ALL_DAYS", "").lower() == "true"
    if ingest_all_days:
        logging.info("INGEST_ALL_DAYS=true → ingesta de TODOS los ficheros de productos.")
        ingest_all_product_files(True, s3_client, BUCKET_NAME, PRODUCTOS_PREFIX, proveedores_validos, ingestor)
    else:
        archivos_hoy = listar_archivos_productos_hoy(s3_client, BUCKET_NAME, PRODUCTOS_PREFIX, JOB_TZ)
        logging.info(f"Archivos de hoy ({hoy_str()}): {archivos_hoy}")

        if not archivos_hoy:
            logging.info("No hay CSVs de productos para hoy. Nada que hacer.")
        else:
            for key in archivos_hoy:
                try:
                    filename = key.split("/")[-1]
                    proveedor_id = int(filename.split("_")[0])  # prefijo del filename

                    # Si el proveedor NO está en proveedores.csv → solo log y saltar
                    if proveedor_id not in proveedores_validos:
                        logging.warning(
                            f"[{key}] id_proveedor {proveedor_id} no está en proveedores.csv. "
                            "No se ingesta este CSV hasta que se añada su fila en proveedores.csv."
                        )
                        continue

                    etag = get_etag(s3_client, BUCKET_NAME, key)
                    if ingestor.was_file_ingested(key, etag):
                        logging.info(f"Saltando (ya ingerido) {key} ({etag})")
                        continue

                    df_productos = descargar_csv_desde_s3(s3_client, BUCKET_NAME, key)

                    # Validación mínima
                    if "id_producto" not in df_productos.columns:
                        logging.error(f"[{key}] Falta columna 'id_producto'; se omite el archivo.")
                        continue

                    # Sincroniza productos del proveedor (insert/update/delete)
                    ingestor.sync_productos_from_csv(df_productos, proveedor_id)

                    # Marca como procesado
                    ingestor.mark_file_ingested(key, etag)

                except Exception as e:
                    logging.error(f"Error procesando '{key}': {e}", exc_info=True)

    logging.info("Ingestión completada.")
