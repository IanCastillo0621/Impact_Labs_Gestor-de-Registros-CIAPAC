"""
Configuración centralizada. Todos los scripts (app.py, registro_escaneos.py,
importar_excel_a_mysql_NI.py, importar_excel_a_mysql_AD.py, importar_registros.py)
deben importar desde aquí en vez de tener credenciales propias.

Requiere: pip install python-dotenv
"""

import os
from dotenv import load_dotenv

load_dotenv()  # busca el archivo .env en la carpeta actual


def _get(name, default=None, required=False):
    val = os.getenv(name, default)
    if required and not val:
        raise RuntimeError(
            f"Falta la variable '{name}' en el archivo .env. "
            f"Revisa que .env exista junto a este script y tenga esa clave."
        )
    return val


# --- MySQL: credenciales base ---
DB_HOST = _get("DB_HOST", "localhost")
DB_PORT = int(_get("DB_PORT", "3306"))
DB_USER = _get("DB_USER", required=True)
DB_PASSWORD = _get("DB_PASSWORD", required=True)

# --- Nombres de bases de datos ---
DB_NAME_REGISTROS = _get("DB_NAME_REGISTROS", "registro_escaneos")
DB_NAME_ADULTOS = _get("DB_NAME_ADULTOS", "adultos")
DB_NAME_NINOS = _get("DB_NAME_NINOS", "ninos")

# --- Flask ---
FLASK_HOST = _get("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(_get("FLASK_PORT", "5001"))
FLASK_DEBUG = _get("FLASK_DEBUG", "False").lower() == "true"

# --- Rutas de Excel ---
EXCEL_PATH_ADULTOS = _get("EXCEL_PATH_ADULTOS")
EXCEL_PATH_NINOS = _get("EXCEL_PATH_NINOS")
EXCEL_PATH_REGISTROS = _get("EXCEL_PATH_REGISTROS")


def mysql_connector_config(database):
    """Dict listo para mysql.connector.connect(**config)"""
    return {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "database": database,
    }


def sqlalchemy_url(database):
    """URL lista para sqlalchemy.create_engine(...) con pymysql"""
    return f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{database}"
