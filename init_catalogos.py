# ===========================================================
# init_catalogos.py — SCIL QNA 2025 / Carga inicial de catálogos
# Lee los archivos Excel de entes y municipios y los inserta en la BD
# ===========================================================

import pandas as pd
import sqlite3
from pathlib import Path

DB_PATH = "scil.db"
CATALOGOS = {
    "entes": "Estatales.xlsx",
    "municipios": "Municipales.xlsx"
}

def importar_catalogo(ruta_excel: Path, tabla: str):
    """Importa un catálogo (entes o municipios) desde un archivo Excel."""
    if not ruta_excel.exists():
        print(f"⚠️  No se encontró el archivo: {ruta_excel}")
        return

    df = pd.read_excel(ruta_excel)
    if "NOMBRE" not in df.columns:
        print(f"⚠️  Archivo {ruta_excel.name} sin columna 'NOMBRE'")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    nuevos = 0

    for _, row in df.iterrows():
        nombre = str(row.get("NOMBRE") or "").strip()
        if not nombre:
            continue
        siglas = str(row.get("SIGLAS") or "").strip()
        clasif = str(row.get("CLASIFICACION") or "").strip()
        ambito = str(row.get("AMBITO") or "ESTATAL").strip()

        # Clave autogenerada tipo: "ENTE_###" o "MUN_###"
        prefix = "ENTE" if tabla == "entes" else "MUN"
        clave = f"{prefix}_{abs(hash(nombre)) % 100000}"

        cur.execute(f"""
            INSERT OR IGNORE INTO {tabla}
            (clave, nombre, siglas, clasificacion, ambito)
            VALUES (?, ?, ?, ?, ?)
        """, (clave, nombre, siglas, clasif, ambito))
        nuevos += 1

    conn.commit()
    conn.close()
    print(f"✅ {nuevos} registros procesados en {tabla} ({ruta_excel.name})")


def main():
    print("=== Cargando catálogos de entes y municipios ===")
    for tabla, archivo in CATALOGOS.items():
        ruta = Path(__file__).parent / archivo
        importar_catalogo(ruta, tabla)
    print("=== Carga completa ===")


if __name__ == "__main__":
    main()
