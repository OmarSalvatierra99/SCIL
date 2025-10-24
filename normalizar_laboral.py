# ===========================================================
# normalizar_laboral.py — SCIL QNA 2025
# Convierte todas las siglas en "entes" a claves ENTE_XXXXX
# ===========================================================

import sqlite3
import json

DB_PATH = "scil.db"

def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Crear mapa sigla -> clave
    cur.execute("SELECT UPPER(siglas) AS sigla, clave FROM entes")
    mapa = {row["sigla"]: row["clave"] for row in cur.fetchall() if row["sigla"]}
    print(f"📘 {len(mapa)} siglas cargadas desde el catálogo de entes")

    # Leer todos los registros de laboral
    cur.execute("SELECT id, datos FROM laboral")
    filas = cur.fetchall()
    total = len(filas)
    actualizados = 0

    for row in filas:
        d = json.loads(row["datos"])
        entes = d.get("entes", [])
        nuevos = []
        modificado = False

        for e in entes:
            e_norm = e.strip().upper()
            if e_norm in mapa:
                nuevos.append(mapa[e_norm])
                if mapa[e_norm] != e:
                    modificado = True
            else:
                nuevos.append(e_norm)

        if modificado:
            d["entes"] = nuevos
            cur.execute("UPDATE laboral SET datos=? WHERE id=?", (json.dumps(d, ensure_ascii=False), row["id"]))
            actualizados += 1

    conn.commit()
    conn.close()
    print(f"✅ {actualizados} de {total} registros actualizados a formato ENTE_XXXXX")

if __name__ == "__main__":
    run()

