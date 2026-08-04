"""
Importa registros de escaneo desde un Excel a la tabla `registros` de MySQL.

Estructura esperada del Excel (los nombres de columna son configurables abajo):
  | codigo             | fecha_hora          |
  | DE03AB10BAYYCU     | 2026-08-29 07:15:00 |
  | MA03RA12CRYYTO     | 2026-08-29 07:32:00 |

Si el Excel no tiene columna de fecha/hora, se puede configurar
FECHA_HORA_COL = None y el script usará la fecha actual para todos los registros.

Requisitos:
    pip install pandas openpyxl sqlalchemy pymysql
"""

import pandas as pd
import io
from sqlalchemy import create_engine, text
from datetime import datetime

# ──────────────────────────────────────────────
# CONFIGURACIÓN — ajustar antes de correr
# ──────────────────────────────────────────────
EXCEL_PATH   = "registros.xlsx"  # ruta al archivo Excel
SHEET_NAME   = "SIM_SEP"            # 0 = primera hoja, o escribe el nombre exacto entre comillas

CODIGO_COL      = "ID"      # nombre de la columna en el Excel con el ID/código
FECHA_HORA_COL  = "HORA"  # nombre de la columna con la fecha y hora
                                 # Pon None si el Excel no tiene esta columna

SKIP_DUPLICATES = False          # True = omite registros cuyo (codigo, fecha_hora) ya exista

DB_USER     = "root"
DB_PASSWORD = "Emirates#0621"
DB_HOST     = "localhost"
DB_NAME     = "registro_escaneos"
TABLE_NAME  = "registros"
# ──────────────────────────────────────────────


def main():
    # 1. Leer Excel
    print(f"\nLeyendo: {EXCEL_PATH}  (hoja: {SHEET_NAME})")
    with open(EXCEL_PATH, "rb") as f:
        df = pd.read_excel(io.BytesIO(f.read()), sheet_name=SHEET_NAME, engine="openpyxl")

    print(f"  {len(df)} filas encontradas | Columnas: {list(df.columns)}")

    # 2. Validar columna de código
    if CODIGO_COL not in df.columns:
        raise ValueError(
            f"No se encontró la columna '{CODIGO_COL}'. "
            f"Columnas disponibles: {list(df.columns)}"
        )

    # 3. Preparar dataframe final
    out = pd.DataFrame()
    out["codigo"] = df[CODIGO_COL].astype(str).str.strip()

    if FECHA_HORA_COL and FECHA_HORA_COL in df.columns:
        out["fecha_hora"] = pd.to_datetime(df[FECHA_HORA_COL], dayfirst=True, errors="coerce")
        nulos = out["fecha_hora"].isna().sum()
        if nulos:
            print(f"  ⚠️  {nulos} fila(s) con fecha inválida serán omitidas.")
        out = out.dropna(subset=["fecha_hora"])
    elif FECHA_HORA_COL is None:
        now = datetime.now()
        print(f"  Sin columna de fecha — se usará la hora actual: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        out["fecha_hora"] = now
    else:
        raise ValueError(
            f"No se encontró la columna '{FECHA_HORA_COL}'. "
            f"Si el Excel no tiene fechas, cambia FECHA_HORA_COL = None"
        )

    # Eliminar filas con código vacío o "nan"
    out = out[out["codigo"].str.lower() != "nan"]
    out = out[out["codigo"].str.strip() != ""]
    print(f"  {len(out)} registro(s) válidos para insertar.")

    if out.empty:
        print("Nada que insertar.")
        return

    # 4. Conectar a MySQL
    engine = create_engine(
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"
    )

    # 5. Filtrar duplicados si SKIP_DUPLICATES está activo
    if SKIP_DUPLICATES:
        with engine.connect() as con:
            existing = pd.read_sql(
                text(f"SELECT codigo, fecha_hora FROM `{TABLE_NAME}`"), con
            )

        if not existing.empty:
            existing["fecha_hora"] = pd.to_datetime(existing["fecha_hora"])
            existing["_key"] = existing["codigo"] + "|" + existing["fecha_hora"].astype(str)
            out["_key"]      = out["codigo"]      + "|" + out["fecha_hora"].astype(str)
            before = len(out)
            out = out[~out["_key"].isin(existing["_key"])].drop(columns="_key")
            skipped = before - len(out)
            if skipped:
                print(f"  {skipped} registro(s) duplicado(s) omitidos.")

        if out.empty:
            print("Todos los registros ya existen en la base de datos.")
            return

    # 6. Insertar
    out[["codigo", "fecha_hora"]].to_sql(
        name=TABLE_NAME,
        con=engine,
        if_exists="append",
        index=False,
    )

    print(f"\n✅  {len(out)} registro(s) insertados en `{TABLE_NAME}` de '{DB_NAME}'.\n")


if __name__ == "__main__":
    main()
