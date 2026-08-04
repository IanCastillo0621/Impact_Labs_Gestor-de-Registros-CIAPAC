"""
Script para importar datos de un Excel (.xlsx) hacia la tabla ADULTOS de MySQL.
Analogo a importar_excel_a_mysql_NI.py pero para adultos.

Requisitos previos:
    pip install pandas sqlalchemy pymysql openpyxl python-dotenv

Como funciona:
- Lee el archivo Excel indicado en EXCEL_PATH_ADULTOS (.env), hoja SHEET_NAME.
- Sube todas las filas a la tabla ADULTOS en la base de datos "adultos".
- Si la tabla no existe, se crea automaticamente. Si ya existe, se agregan
  (append) solo los registros cuyo ID no exista ya en la tabla.
"""

import pandas as pd
import io
import pymysql
from sqlalchemy import create_engine
import config

# ---------------------------------------------------------------------------
# CONFIGURACION: la ruta del Excel y las credenciales se leen del .env.
# ---------------------------------------------------------------------------
EXCEL_PATH = config.EXCEL_PATH_ADULTOS
SHEET_NAME = "ADULTOS"  # ajustar si el nombre real de la hoja es distinto

TABLE_NAME = "ADULTOS"
DB_NAME = config.DB_NAME_ADULTOS


def main():
    # 1. Leer el Excel
    with open(EXCEL_PATH, 'rb') as f:
        file_bytes = io.BytesIO(f.read())

    df = pd.read_excel(file_bytes, sheet_name=SHEET_NAME, engine='openpyxl', header=0)
    print(f"Se leyeron {len(df)} filas y {len(df.columns)} columnas del Excel.")
    print("Columnas detectadas:", list(df.columns))

    # Renombrar columnas segun la tabla MySQL (mismo orden que setup_ad.sql)
    df.columns = [
        "Folio", "ID", "NOMBRE", "APELLIDOS", "GENERO", "EDO_CIVIL",
        "ESCOLARIDAD", "OCUPACION", "F_NACIMIENTO", "DOMICILIO",
        "COLONIA", "MUNICIPIO", "CURP", "EDAD",
    ]

    # 2. Conectar a MySQL
    engine = create_engine(config.sqlalchemy_url(DB_NAME))

    # 3. Filtrar registros que ya existen en la tabla (por ID)
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
        if_exists="append",
        index=False,
    )

    print(f"Listo: {len(df)} filas insertadas en la tabla '{TABLE_NAME}'.")


if __name__ == "__main__":
    main()
