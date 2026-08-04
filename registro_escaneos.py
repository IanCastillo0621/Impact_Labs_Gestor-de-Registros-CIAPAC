"""
Script de captura de codigos de barras -> MySQL

Requisitos previos:
1. Haber ejecutado setup_db.sql en la base de datos de la organizacion.
2. Instalar la libreria de conexion:
   pip install mysql-connector-python

Uso:
- Corre este script (python registro_escaneos.py) y deja la terminal con el foco activo.
- Cada vez que se escanee un codigo de barras, el lector "escribira" el codigo
  y mandara un Enter, lo cual el script captura, guarda la fecha/hora actual,
  e inserta el registro en la tabla `registros`.
- Presiona Ctrl+C para terminar la sesion de captura.
"""

import mysql.connector
from mysql.connector import Error
from datetime import datetime
import config

# ---------------------------------------------------------------------------
# CONFIGURACION: las credenciales ahora se leen del archivo .env
# (ver config.py). Ajusta el .env, no este archivo.
# ---------------------------------------------------------------------------
DB_CONFIG = config.mysql_connector_config(config.DB_NAME_REGISTROS)


def conectar():
    try:
        conexion = mysql.connector.connect(**DB_CONFIG)
        return conexion
    except Error as err:
        print(f"No se pudo conectar a MySQL: {err}")
        return None


def main():
    conexion = conectar()
    if conexion is None:
        return

    cursor = conexion.cursor()
    print("Conectado a la base de datos.")
    print("Listo para escanear codigos. Presiona Ctrl+C para salir.\n")

    try:
        while True:
            codigo = input("Escanea un codigo: ").strip()

            if not codigo:
                continue

            fecha_hora = datetime.now()

            try:
                cursor.execute(
                    "INSERT INTO registros (codigo, fecha_hora) VALUES (%s, %s)",
                    (codigo, fecha_hora),
                )
                conexion.commit()
                print(f"  -> Registrado: {codigo} | {fecha_hora.strftime('%Y-%m-%d %H:%M:%S')}\n")
            except Error as err:
                print(f"  -> Error al insertar el registro: {err}\n")

    except KeyboardInterrupt:
        print("\nFinalizando captura de escaneos.")

    finally:
        cursor.close()
        conexion.close()


if __name__ == "__main__":
    main()
