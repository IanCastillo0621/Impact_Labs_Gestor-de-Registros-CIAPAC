"""
Script para importar datos de un Excel (.xlsx) hacia una tabla de MySQL.

Requisitos previos:
    pip install pandas sqlalchemy pymysql openpyxl

Como funciona:
- Lee el archivo Excel indicado en EXCEL_PATH (hoja SHEET_NAME).
- Sube todas las filas a la tabla TABLE_NAME en la base de datos configurada.
- Si la tabla no existe, se crea automaticamente usando los nombres de columna
  del Excel. Si ya existe, los datos se agregan (append) sin borrar lo que
  ya hay.
"""

import pandas as pd
import io
import pymysql
from sqlalchemy import create_engine
import config

# ---------------------------------------------------------------------------
# CONFIGURACION: la ruta del Excel y las credenciales se leen del .env.
# Solo ajusta SHEET_NAME/TABLE_NAME aquí si cambia el nombre de la hoja.
# ---------------------------------------------------------------------------
EXCEL_PATH = config.EXCEL_PATH_NINOS
SHEET_NAME = "NINOS"  # 0 = primera hoja, o el nombre exacto de la hoja como texto

TABLE_NAME = "NINOS"
DB_NAME = config.DB_NAME_NINOS


def main():
    # 1. Leer el Excel
    with open(EXCEL_PATH, 'rb') as f:
        file_bytes = io.BytesIO(f.read())
    
    # 1. Leer el Excel forcing the engine onto the raw bytes stream
    df = pd.read_excel(file_bytes, sheet_name=SHEET_NAME, engine='openpyxl', header=0)
    print(f"Se leyeron {len(df)} filas y {len(df.columns)} columnas del Excel.")
    print("Columnas detectadas:", list(df.columns))

    df.columns = ["Folio", "ID", "NOMBRE", "APELLIDOS", "GENERO", "F_NACIMIENTO", "DOMICILIO", "COLONIA", "MUNICIPIO", "GRADO_ESC", "ESCUELA", "CURP", "EDAD"]  # Renombrar columnas segun la tabla MySQL

    # 2. Conectar a MySQL
    engine = create_engine(config.sqlalchemy_url(DB_NAME))

    # 3. Filtrar registros que ya existen en la tabla (por Folio)
    try:
        existing = pd.read_sql(f"SELECT ID FROM `{TABLE_NAME}`", engine)
        existing_ids = set(existing["ID"].astype(str))
        before = len(df)
        df = df[~df["ID"].astype(str).isin(existing_ids)]
        duplicates = before - len(df)
        if duplicates:
            print(f"Se omitieron {duplicates} registro(s) ya existentes en la base de datos.")
    except Exception:
        pass  # La tabla aun no existe, se insertan todos los registros

    if df.empty:
        print("No hay registros nuevos para insertar.")
        return

    # 4. Subir los datos
    df.to_sql(
        name=TABLE_NAME,
        con=engine,
        if_exists="append",  # usar "replace" si quieres borrar y recrear la tabla
        index=False,
    )

    print(f"Listo: {len(df)} filas insertadas en la tabla '{TABLE_NAME}'.")


if __name__ == "__main__":
    main()
