#!/usr/bin/env python3
# ===========================================================
# limpiar_datos.py — SCIL / SASP 2025
# Script para limpiar datos laborales sin afectar catálogos
# ===========================================================

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "scil.db"

def limpiar_datos():
    """
    Limpia las tablas de datos laborales y solventaciones,
    manteniendo intactos los catálogos y usuarios.
    """
    if not DB_PATH.exists():
        print(f"❌ No se encontró la base de datos en: {DB_PATH}")
        return

    print(f"📂 Conectando a base de datos: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Contar registros antes de eliminar
        cursor.execute("SELECT COUNT(*) FROM laboral")
        count_laboral = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM solventaciones")
        count_solventaciones = cursor.fetchone()[0]

        print(f"\n📊 Registros actuales:")
        print(f"   - Laboral: {count_laboral}")
        print(f"   - Solventaciones: {count_solventaciones}")

        # Eliminar datos
        print(f"\n🧹 Limpiando datos...")
        cursor.execute("DELETE FROM laboral")
        cursor.execute("DELETE FROM solventaciones")

        conn.commit()

        print(f"✅ Datos eliminados exitosamente:")
        print(f"   - Laboral: {count_laboral} registros eliminados")
        print(f"   - Solventaciones: {count_solventaciones} registros eliminados")

        # Verificar que los catálogos siguen intactos
        cursor.execute("SELECT COUNT(*) FROM entes")
        count_entes = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM usuarios")
        count_usuarios = cursor.fetchone()[0]

        print(f"\n✅ Catálogos preservados:")
        print(f"   - Entes: {count_entes} registros")
        print(f"   - Usuarios: {count_usuarios} registros")

    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

    print("\n✅ Proceso completado. Los usuarios pueden volver a subir datos.")

if __name__ == "__main__":
    limpiar_datos()
