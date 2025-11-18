# ingest/ingestor.py
import pandas as pd
import logging
import sys
from pathlib import Path
import unicodedata
import glob

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select, delete, update
import dateparser

project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from models import Proveedor, Producto, Base, IngestedFile
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
    dt = dateparser.parse(str(fecha_str), languages=["es"])
    return dt.date() if hasattr(dt, "date") else dt

def parse_precio(valor) -> float:
    try:
        val = str(valor).strip().replace("$", "").replace(" ", "").replace(",", ".")
        return float(val)
    except Exception:
        logging.warning(f"Precio inválido '{valor}'")
        return None

def to_float(val):
    try:
        return float(val)
    except Exception:
        return 0.0

def to_int(val):
    try:
        return int(val)
    except Exception:
        return 0

def to_int_or_none(val):
    """Convierte a int robustamente; devuelve None si está vacío/NaN/no numérico o <= 0."""
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        s = str(val).strip()
        if not s or s.lower() == "nan":
            return None
        n = int(float(s))
        return n if n > 0 else None
    except Exception:
        return None

def safe_str(val):
    """Devuelve string limpio o None si viene vacío/NaN/'nan'."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return None if not s or s.lower() == "nan" else s


# --- Clase de Ingestión ---
class CSVIngestor:
    def __init__(self, proveedores_file: str | None, productos_dir: str | None):
        self.proveedores_file = proveedores_file
        self.productos_dir = productos_dir
        self.session = SessionLocal()

    def create_tables(self):
        logging.info("Creando tablas si no existen...")
        Base.metadata.create_all(engine)  # incluye ingested_files
        # Asegurar columna nueva en despliegues con tabla existente
        from sqlalchemy import text
        with engine.connect() as conn:
            try:
                conn.execute(text("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS descripcion TEXT"))
            except Exception as e:
                logging.warning(f"No se pudo asegurar columna 'descripcion' en proveedores: {e}")

    def reset_database(self):
        logging.info("Eliminando datos existentes de las tablas...")
        try:
            self.session.query(Producto).delete()
            self.session.query(Proveedor).delete()
            self.session.query(IngestedFile).delete()
            self.session.commit()
            logging.info("Tablas vaciadas correctamente.")
        except SQLAlchemyError as e:
            self.session.rollback()
            logging.error(f"Error al resetear la base de datos: {e}")

    # ---------- Tracking de ficheros procesados ----------
    def was_file_ingested(self, s3_key: str, etag: str) -> bool:
        try:
            q = self.session.execute(
                select(IngestedFile.id).where(
                    IngestedFile.s3_key == s3_key,
                    IngestedFile.etag == etag
                )
            ).scalar_one_or_none()
            return q is not None
        except Exception as e:
            logging.warning(f"No se pudo comprobar ingesta previa de '{s3_key}': {e}")
            return False

    def mark_file_ingested(self, s3_key: str, etag: str):
        try:
            rec = IngestedFile(s3_key=s3_key, etag=etag)
            self.session.add(rec)
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            logging.warning(f"No se pudo marcar como ingerido '{s3_key}': {e}")

    # ---------- Proveedores: upsert ----------
    def upsert_proveedores(self, df: pd.DataFrame):
        if df is None or df.empty:
            logging.info("upsert_proveedores: DataFrame vacío; no hay cambios.")
            return

        logging.info("Upsert de proveedores...")
        for _, row in df.iterrows():
            try:
                pid = to_int(row.get("id_proveedor"))
                prov = self.session.get(Proveedor, pid)
                if prov is None:
                    prov = Proveedor(
                        id_proveedor=pid,
                        nombre_comercial=row.get("nombre_comercial"),
                        razon_social=row.get("razon_social"),
                        nombre_ejecutivo_ventas=row.get("nombre_ejecutivo_ventas"),
                        whatsapp_ventas=safe_str(row.get("whatsapp_ventas")),
                        pagina_web=row.get("pagina_web"),
                        entregas_domicilio=limpiar_booleano(row.get("entregas_domicilio")),
                        monto_minimo=to_float(row.get("monto_minimo")),
                        ofrece_credito=limpiar_booleano(row.get("ofrece_credito")),
                        calificacion_usuarios=to_float(row.get("calificacion_usuarios")),
                        nivel_membresia=to_float(row.get("nivel_membresia")),
                        descripcion=safe_str(row.get("descripcion")),  # NUEVO CAMPO
                    )
                    self.session.add(prov)
                else:
                    prov.nombre_comercial = row.get("nombre_comercial")
                    prov.razon_social = row.get("razon_social")
                    prov.nombre_ejecutivo_ventas = row.get("nombre_ejecutivo_ventas")
                    prov.whatsapp_ventas = safe_str(row.get("whatsapp_ventas"))
                    prov.pagina_web = row.get("pagina_web")
                    prov.entregas_domicilio = limpiar_booleano(row.get("entregas_domicilio"))
                    prov.monto_minimo = to_float(row.get("monto_minimo"))
                    prov.ofrece_credito = limpiar_booleano(row.get("ofrece_credito"))
                    prov.calificacion_usuarios = to_float(row.get("calificacion_usuarios"))
                    prov.nivel_membresia = to_float(row.get("nivel_membresia"))
                    prov.descripcion = safe_str(row.get("descripcion"))  # NUEVO CAMPO
            except Exception as e:
                logging.warning(f"Error procesando proveedor id_proveedor={row.get('id_proveedor')}: {e}")
        try:
            self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            logging.error(f"Error al hacer upsert de proveedores: {e}")

    # ---------- Productos: sync por CSV del día ----------
    def sync_productos_from_csv(self, df_prod: pd.DataFrame, proveedor_id: int):
        """
        Para el proveedor indicado:
          - Inserta productos NUEVOS (id_producto_csv en CSV pero no en BD)
          - Actualiza precio_unidad (y otros campos básicos) de los EXISTENTES
          - Elimina productos que estén en BD pero ya no vengan en el CSV del día
        """
        if df_prod is None or df_prod.empty:
            logging.info(f"[Proveedor {proveedor_id}] CSV vacío; no hay cambios.")
            return

        # Por si la sesión viene abortada de un intento anterior
        try:
            self.session.rollback()
        except Exception:
            pass

        df = df_prod.copy()
        df["id_proveedor"] = proveedor_id

        if "id_producto" not in df.columns:
            logging.error("El CSV no contiene la columna 'id_producto'. No se puede sincronizar.")
            return

        # --- Normalización robusta de id_producto ---
        df["id_producto_csv"] = df["id_producto"].apply(to_int_or_none)
        invalid = df[df["id_producto_csv"].isna()]
        if not invalid.empty:
            logging.warning(
                "[Proveedor %s] %s filas sin id_producto válido; se omiten. Ejemplos: %s",
                proveedor_id, len(invalid), invalid["id_producto"].head(5).tolist()
            )
        # Descarta las inválidas y deduplica por id_producto_csv (última aparición)
        df = df.dropna(subset=["id_producto_csv"]).copy()
        df["id_producto_csv"] = df["id_producto_csv"].astype(int)
        df = df.drop_duplicates(subset=["id_producto_csv"], keep="last")

        # Conjuntos de IDs
        csv_ids = set(df["id_producto_csv"].tolist())

        # IDs existentes en BD para ese proveedor
        existing_ids = set(
            self.session.execute(
                select(Producto.id_producto_csv).where(Producto.id_proveedor == proveedor_id)
            ).scalars().all()
        )

        to_insert = csv_ids - existing_ids
        to_update = csv_ids & existing_ids
        to_delete = existing_ids - csv_ids

        logging.info(f"[Proveedor {proveedor_id}] nuevos={len(to_insert)} actualizar={len(to_update)} borrar={len(to_delete)}")

        # --- INSERTA NUEVOS ---
        for _, row in df[df["id_producto_csv"].isin(to_insert)].iterrows():
            try:
                categorias_raw = [
                    row.get("categoria_1"),
                    row.get("categoria_2"),
                    row.get("categoria_3"),
                    row.get("categoria_4"),
                    row.get("categoria_5"),
                ]
                categorias = [safe_str(c) for c in categorias_raw if safe_str(c)]

                nombre_producto = safe_str(row.get("nombre_producto"))
                # Texto para embedding (si no hay nombre, usa atributos alternativos; si no, string vacío)
                texto_emb = (
                    nombre_producto
                    or " ".join(x for x in [
                        safe_str(row.get("marca")),
                        safe_str(row.get("presentacion_venta")),
                        safe_str(row.get("cod_producto")),
                    ] if x)
                    or ""
                )

                precio = parse_precio(row.get("precio_unidad"))
                precio = float(precio) if (precio is not None and not pd.isna(precio)) else 0.0

                prod = Producto(
                    id_proveedor=proveedor_id,
                    id_producto_csv=int(row["id_producto_csv"]),
                    nombre_producto=nombre_producto,
                    cod_producto=safe_str(row.get("cod_producto")),
                    marca=safe_str(row.get("marca")),
                    presentacion_venta=safe_str(row.get("presentacion_venta")),
                    unidad_venta=safe_str(row.get("unidad_venta")),
                    precio_unidad=precio,
                    moneda=safe_str(row.get("moneda")),
                    categorias=categorias,
                    ultima_actualizacion=parse_fecha_espanol(row.get("ultima_actualizacion")),
                    vigencia=safe_str(row.get("vigencia")),
                    proveedor=safe_str(row.get("proveedor")),
                    embedding=generar_embedding(texto_emb)
                )
                self.session.add(prod)
                # Evita el INSERT en lote; si falla, rollback y continúa
                self.session.flush()

            except Exception as e:
                logging.exception(
                    "Error insertando producto nuevo (id_proveedor=%s, id_producto=%s): %s",
                    proveedor_id, row.get("id_producto"), e
                )
                try:
                    self.session.rollback()
                except Exception:
                    pass

        # --- ACTUALIZA EXISTENTES (precio_unidad y campos básicos) ---
        for _, row in df[df["id_producto_csv"].isin(to_update)].iterrows():
            try:
                precio = parse_precio(row.get("precio_unidad"))
                precio = float(precio) if (precio is not None and not pd.isna(precio)) else 0.0

                stmt = (
                    update(Producto)
                    .where(
                        Producto.id_proveedor == proveedor_id,
                        Producto.id_producto_csv == int(row["id_producto_csv"])
                    )
                    .values(
                        precio_unidad=precio,
                        moneda=safe_str(row.get("moneda")),
                        ultima_actualizacion=parse_fecha_espanol(row.get("ultima_actualizacion")),
                        vigencia=safe_str(row.get("vigencia")),
                        # Si quisieras actualizar más campos, se añaden aquí.
                    )
                )
                self.session.execute(stmt)
            except Exception as e:
                logging.exception(
                    "Error actualizando producto (id_proveedor=%s, id_producto=%s): %s",
                    proveedor_id, row.get("id_producto"), e
                )
                try:
                    self.session.rollback()
                except Exception:
                    pass

        # --- ELIMINA LOS QUE YA NO ESTÁN EN EL CSV DEL DÍA ---
        if to_delete:
            try:
                self.session.execute(
                    delete(Producto).where(
                        Producto.id_proveedor == proveedor_id,
                        Producto.id_producto_csv.in_(list(to_delete))
                    )
                )
            except Exception as e:
                logging.exception(
                    "Error eliminando %s productos (id_proveedor=%s): %s",
                    len(to_delete), proveedor_id, e
                )
                try:
                    self.session.rollback()
                except Exception:
                    pass

        # Commit final
        try:
            self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            logging.error(
                "Error en commit de sync productos (id_proveedor=%s) [nuevos=%s, actualizar=%s, borrar=%s]: %s",
                proveedor_id, len(to_insert), len(to_update), len(to_delete), e
            )

    # ---------- Compatibilidad (legacy) ----------
    def load_csv(self, path: str) -> pd.DataFrame:
        logging.info(f"Cargando archivo: {path}")
        return pd.read_csv(path, encoding="latin1")

    def insert_proveedores(self, df: pd.DataFrame):
        self.upsert_proveedores(df)

    def insert_productos(self, df_prod: pd.DataFrame):
        if "id_proveedor" not in df_prod.columns:
            logging.error("insert_productos: falta columna 'id_proveedor'.")
            return
        for proveedor_id, df_subset in df_prod.groupby("id_proveedor"):
            self.sync_productos_from_csv(df_subset, to_int(proveedor_id))

    def insert_productos_from_all_files(self):
        if not self.productos_dir:
            logging.warning("insert_productos_from_all_files: productos_dir no definido.")
            return

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
                self.sync_productos_from_csv(df, id_proveedor)
            except Exception as e:
                logging.exception(
                    "Error procesando archivo '%s' (id_proveedor=%s): %s",
                    filepath, id_proveedor, e
                )
        logging.info("Ingestión completada.")
