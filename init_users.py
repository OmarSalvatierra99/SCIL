# ===========================================================
# init_users.py — SCIL QNA 2025 / Inicializador de usuarios
# Crea usuarios con contraseñas seguras y asignación de entes
# ===========================================================

import sqlite3
import hashlib

DB_PATH = "scil.db"

def hash_password(password: str) -> str:
    """Genera hash SHA256 de una contraseña."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Borrar usuarios anteriores
    cur.execute("DELETE FROM usuarios")

    # Lista de entes completos (todos los que aparecen en tu base)
    TODOS_LOS_ENTES = (
        "CORACYT,SESAET,SI,OMG,ICATLAX,CEDH,SOTYV,TCYA,SEPE,SMYT,PROPAET,"
        "CGPI,SIA,COLTLAX,UPT,ITEA,UTT,CECYTE,ITST,USET,UPTREP,CONALEP,UIT,"
        "COBAT,ITAES,COESPO,ITJ,PCET,FOMTLAX,IDET,CEAS,FIDECIX,ITIFE,CEAVIT,"
        "IDC,AGHET,OPD,SF,CRI-ESCUELA,SEDIF,TJA,TET,ITE,UAT,IAIP,FGJET,PJ,PL,"
        "SMET,SESESP,CCOM,SCC,SB"
    )

    usuarios = [
        {
            "nombre": "C.P.C. Juan José Blanco Sánchez",
            "usuario": "juan",
            "clave": "JBlanco#2025!",
            "entes": "CORACYT,SESAET,SI,OMG,ICATLAX,CEDH,SOTYV,TCYA,SEPE,SMYT,PROPAET,CGPI,SIA"
        },
        {
            "nombre": "C.P. Cristina Rosas de la Cruz",
            "usuario": "cristina",
            "clave": "CRosas$2025!",
            "entes": "COLTLAX,UPT,ITEA,UTT,CECYTE,ITST,USET,UPTREP,CONALEP,UIT,COBAT,ITAES"
        },
        {
            "nombre": "C.P. Miguel Ángel Roldán Peña",
            "usuario": "miguel",
            "clave": "MRoldan@2025!",
            "entes": "COESPO,ITJ,PCET,FOMTLAX,IDET,CEAS,FIDECIX,ITIFE,CEAVIT,IDC,AGHET,OPD,SF,CRI-ESCUELA"
        },
        {
            "nombre": "Téc. Ángel Flores Licona",
            "usuario": "angel",
            "clave": "AFlores*2025!",
            "entes": "SEDIF,TJA,TET,ITE,UAT,IAIP,FGJET,PJ,PL,SMET,SESESP,CCOM,SCC,SB"
        },
        {
            "nombre": "C.P. Odilia Hernández García",
            "usuario": "odilia",
            "clave": "Odilia@2025#Cont",
            "entes": TODOS_LOS_ENTES
        },
        {
            "nombre": "C.P. Víctor Manuel Torres Ramírez",
            "usuario": "victor",
            "clave": "Victor#2025@Cont",
            "entes": TODOS_LOS_ENTES
        }
    ]

    # Insertar usuarios
    for u in usuarios:
        clave_hash = hash_password(u["clave"])
        cur.execute("""
            INSERT INTO usuarios (nombre, usuario, clave, entes)
            VALUES (?, ?, ?, ?)
        """, (u["nombre"], u["usuario"], clave_hash, u["entes"]))

    conn.commit()
    conn.close()

    print("✅ Usuarios creados correctamente:\n")
    for u in usuarios:
        print(f"  • {u['usuario']} ({u['nombre']})")
        print(f"    Clave: {u['clave']}")
        print(f"    Entes: {u['entes']}\n")

if __name__ == "__main__":
    run()

