# main.py
import os
import logging
from io import BytesIO
import boto3
import pandas as pd

# Carga .env solo en local (no afecta en Heroku)
from dotenv import load_dotenv
load_dotenv()

from ingest.ingestor import CSVIngestor

BUCKET_NAME = "supplier-catalogs-2025"
PROVEEDORES_KEY = "data/proveedores.csv"
PRODUCTOS_PREFIX = "data/"  # Carpeta donde están los *_productos.csv

def descargar_csv_desde_s3(s3_client, bucket, key):
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(BytesIO(obj['Body'].read()), encoding="latin1")

def listar_archivos_productos(s3_client, bucket, prefix):
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    return [c['Key'] for c in response.get('Contents', []) if c['Key'].endswith('_productos.csv')]

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    s3_client = boto3.client("s3")

    # 1) Carga proveedores desde S3
    df_proveedores = descargar_csv_desde_s3(s3_client, BUCKET_NAME, PROVEEDORES_KEY)

    # 2) Instancia ingestor y crea tablas (sin drop)
    ingestor = CSVIngestor(proveedores_file=None, productos_dir=None)
    ingestor.create_tables()

    # Reset controlado por variable de entorno (¡cuidado en prod!)
    if os.getenv("RESET_DB", "").lower() == "true":
        ingestor.reset_database()

    ingestor.insert_proveedores(df_proveedores)

    # 3) Productos desde todos los CSV remotos
    archivos_productos = listar_archivos_productos(s3_client, BUCKET_NAME, PRODUCTOS_PREFIX)
    for key in archivos_productos:
        try:
            df_productos = descargar_csv_desde_s3(s3_client, BUCKET_NAME, key)
            id_str = key.split("/")[-1].split("_")[0]
            df_productos["id_proveedor"] = int(id_str)
            ingestor.insert_productos(df_productos)
        except Exception as e:
            logging.error(f"Error procesando archivo '{key}': {e}")

    logging.info("Ingestión completada desde S3.")
