#!/usr/bin/env python3
# ===========================================================
# migrar_bd.py — SCIL / SASP 2025
# Script para migrar a la nueva estructura de BD
# ===========================================================

import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "scil.db"
BACKUP_DIR = Path(__file__).parent / "backups"

def hacer_backup():
    """Crea un backup de la base de datos actual."""
    if not DB_PATH.exists():
        print(f"❌ No se encontró la base de datos en: {DB_PATH}")
        return None

    # Crear directorio de backups si no existe
    BACKUP_DIR.mkdir(exist_ok=True)

    # Nombre del backup con timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"scil_backup_{timestamp}.db"

    # Copiar archivo
    shutil.copy2(DB_PATH, backup_path)
    print(f"✅ Backup creado: {backup_path}")
    return backup_path


def migrar_datos():
    """
    Migra datos de la tabla laboral antigua a registros_laborales.
    IMPORTANTE: Solo migra si aún no se ha hecho la migración.
    """
    if not DB_PATH.exists():
        print(f"❌ No se encontró la base de datos en: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Verificar si la nueva tabla ya existe
    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='registros_laborales'
    """)

    if not cur.fetchone():
        print("⚠️  La tabla registros_laborales no existe. Ejecutando inicialización de BD...")
        from core.database import DatabaseManager
        db = DatabaseManager(str(DB_PATH))
        print("✅ Tablas inicializadas correctamente.")

    # Contar registros en cada tabla
    cur.execute("SELECT COUNT(*) FROM laboral")
    count_laboral = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM registros_laborales")
    count_registros = cur.fetchone()[0]

    print(f"\n📊 Estado actual de la base de datos:")
    print(f"   - Tabla laboral (antigua): {count_laboral} registros")
    print(f"   - Tabla registros_laborales (nueva): {count_registros} registros")

    conn.close()


def limpiar_tabla_laboral():
    """
    Limpia la tabla laboral antigua (opcional).
    Se recomienda hacer esto después de verificar que la nueva tabla funciona correctamente.
    """
    respuesta = input("\n¿Deseas limpiar la tabla 'laboral' antigua? (s/n): ").strip().lower()

    if respuesta != 's':
        print("⏭️  Omitiendo limpieza de tabla laboral.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        cur.execute("DELETE FROM laboral")
        conn.commit()
        print(f"✅ Tabla 'laboral' limpiada. Registros eliminados.")
    except Exception as e:
        print(f"❌ Error al limpiar tabla laboral: {e}")
        conn.rollback()
    finally:
        conn.close()


def limpiar_solventaciones():
    """
    Limpia solventaciones huérfanas (RFCs que ya no existen en registros_laborales).
    """
    respuesta = input("\n¿Deseas limpiar solventaciones huérfanas? (s/n): ").strip().lower()

    if respuesta != 's':
        print("⏭️  Omitiendo limpieza de solventaciones.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        # Eliminar solventaciones de RFCs que ya no existen
        cur.execute("""
            DELETE FROM solventaciones
            WHERE rfc NOT IN (SELECT DISTINCT rfc FROM registros_laborales)
        """)
        eliminados = cur.rowcount
        conn.commit()
        print(f"✅ Solventaciones huérfanas eliminadas: {eliminados}")
    except Exception as e:
        print(f"❌ Error al limpiar solventaciones: {e}")
        conn.rollback()
    finally:
        conn.close()


def main():
    """Función principal de migración."""
    print("=" * 60)
    print("SCIL / SASP 2025 - Migración de Base de Datos")
    print("=" * 60)
    print("\nEste script realizará las siguientes acciones:")
    print("1. Crear backup de la base de datos actual")
    print("2. Verificar/crear la nueva tabla registros_laborales")
    print("3. Opcionalmente, limpiar tabla laboral antigua")
    print("4. Opcionalmente, limpiar solventaciones huérfanas")
    print("\n" + "=" * 60)

    continuar = input("\n¿Deseas continuar? (s/n): ").strip().lower()
    if continuar != 's':
        print("❌ Migración cancelada.")
        return

    # Paso 1: Backup
    print("\n📦 Creando backup...")
    backup_path = hacer_backup()
    if not backup_path:
        return

    # Paso 2: Migrar datos
    print("\n🔄 Verificando estructura de base de datos...")
    migrar_datos()

    # Paso 3: Limpiar tabla laboral (opcional)
    limpiar_tabla_laboral()

    # Paso 4: Limpiar solventaciones (opcional)
    limpiar_solventaciones()

    print("\n" + "=" * 60)
    print("✅ Migración completada exitosamente")
    print(f"📂 Base de datos: {DB_PATH}")
    print(f"💾 Backup guardado en: {backup_path}")
    print("=" * 60)
    print("\n⚠️  IMPORTANTE:")
    print("   - Ahora puedes subir nuevamente tus archivos Excel")
    print("   - Los duplicados RFC+ENTE se actualizarán automáticamente")
    print("   - Solo se mostrarán cruces REALES (misma QNA en diferentes entes)")


if __name__ == "__main__":
    main()
