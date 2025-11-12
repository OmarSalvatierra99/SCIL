#!/usr/bin/env python3
# ===========================================================
# importar_catalogos_scil.py — SCIL / SASP 2025
# Script optimizado para importar catálogos desde Excel
# ===========================================================

import pandas as pd
import sqlite3
import hashlib
import os
from pathlib import Path

# Configuración de rutas
BASE_DIR = Path(__file__).parent / "catalogos"
DB_PATH = Path(__file__).parent / "scil.db"

# Validar que exista el directorio de catálogos
if not BASE_DIR.exists():
    raise FileNotFoundError(f"❌ No se encontró el directorio: {BASE_DIR}")


def conectar_db():
    """Crea conexión a la base de datos."""
    return sqlite3.connect(DB_PATH)


def limpiar_tablas(cursor):
    """Limpia las tablas antes de importar."""
    print("🧹 Limpiando tablas anteriores...")
    cursor.execute("DELETE FROM entes")
    cursor.execute("DELETE FROM municipios")
    cursor.execute("DELETE FROM usuarios")
    print("✅ Tablas limpiadas")


def importar_entes(cursor):
    """Importa catálogo de entes estatales."""
    archivo = BASE_DIR / "Estatales.xlsx"
    if not archivo.exists():
        print(f"⚠️  No se encontró {archivo.name}, omitiendo...")
        return

    print(f"📊 Importando {archivo.name}...")
    df = pd.read_excel(archivo)
    count = 0

    for _, row in df.iterrows():
        num_original = str(row["NUM"]).strip()
        if not num_original or num_original.lower() in ("nan", "none", ""):
            continue

        # Generar clave única evitando colisiones
        # Reemplazar punto por guion bajo: "1.1" → "ENTE_1_1", "11" → "ENTE_11"
        num_clean = num_original.rstrip('.').replace(".", "_")
        clave = f"ENTE_{num_clean}"

        cursor.execute("""
            INSERT OR REPLACE INTO entes (num, clave, nombre, siglas, clasificacion, ambito, activo)
            VALUES (?, ?, ?, ?, ?, 'ESTATAL', 1)
        """, (
            num_original,  # Guardamos el NUM original (ej: "1.2")
            clave,         # Clave sin colisiones (ej: "ENTE_1_2")
            str(row["NOMBRE"]).strip(),
            str(row["SIGLAS"]).strip().upper(),
            str(row["CLASIFICACION"]).strip()
        ))
        count += 1

    print(f"✅ {count} entes estatales importados")


def importar_municipios(cursor):
    """Importa catálogo de municipios."""
    archivo = BASE_DIR / "Municipales.xlsx"
    if not archivo.exists():
        print(f"⚠️  No se encontró {archivo.name}, omitiendo...")
        return

    print(f"📊 Importando {archivo.name}...")
    df = pd.read_excel(archivo)
    count = 0

    for _, row in df.iterrows():
        num_original = str(row["NUM"]).strip()
        if not num_original or num_original.lower() in ("nan", "none", ""):
            continue

        # Generar clave única evitando colisiones
        num_clean = num_original.rstrip('.').replace(".", "_")
        clave = f"MUN_{num_clean}"

        cursor.execute("""
            INSERT OR REPLACE INTO municipios (num, clave, nombre, siglas, clasificacion, ambito, activo)
            VALUES (?, ?, ?, ?, ?, 'MUNICIPAL', 1)
        """, (
            num_original,  # Guardamos el NUM original
            clave,         # Clave sin colisiones
            str(row["NOMBRE"]).strip(),
            str(row["SIGLAS"]).strip().upper(),
            str(row["CLASIFICACION"]).strip()
        ))
        count += 1

    print(f"✅ {count} municipios importados")


def importar_usuarios(cursor):
    """Importa catálogo de usuarios del sistema."""
    archivo = BASE_DIR / "Usuarios_SASP_2025.xlsx"
    if not archivo.exists():
        print(f"⚠️  No se encontró {archivo.name}, omitiendo...")
        return

    print(f"👥 Importando {archivo.name}...")
    df = pd.read_excel(archivo)
    count = 0

    for _, row in df.iterrows():
        usuario = str(row["Usuario"]).strip()
        clave_hash = hashlib.sha256(str(row["Clave"]).encode()).hexdigest()
        nombre = str(row["Nombre completo"]).strip()
        entes = str(row["Entes asignados"]).strip().upper()

        cursor.execute("""
            INSERT OR REPLACE INTO usuarios (nombre, usuario, clave, entes)
            VALUES (?, ?, ?, ?)
        """, (nombre, usuario, clave_hash, entes))
        count += 1

    print(f"✅ {count} usuarios importados")


def main():
    """Función principal de importación."""
    print("=" * 60)
    print("SCIL / SASP 2025 - Importador de Catálogos")
    print("=" * 60)

    conn = conectar_db()
    cur = conn.cursor()

    try:
        limpiar_tablas(cur)
        conn.commit()

        importar_entes(cur)
        importar_municipios(cur)
        importar_usuarios(cur)

        conn.commit()
        print("\n" + "=" * 60)
        print("✅ Importación completada exitosamente")
        print(f"📂 Base de datos: {DB_PATH}")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error durante la importación: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()

