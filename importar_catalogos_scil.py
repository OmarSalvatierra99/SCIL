#!/usr/bin/env python3
# importar_catalogos_scil.py — compatible con SCIL / SASP 2025

import pandas as pd, sqlite3, hashlib, os

DB_PATH = "scil.db"
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# --- 1. Importar entes estatales ---
estatales = pd.read_excel("Estatales.xlsx")
for _, r in estatales.iterrows():
    clave = f"ENTE_{int(float(r['NUM'])*100):05d}" if pd.notna(r['NUM']) else None
    cur.execute("""
        INSERT OR REPLACE INTO entes (clave, nombre, siglas, clasificacion, ambito, activo)
        VALUES (?, ?, ?, ?, 'ESTATAL', 1)
    """, (
        clave,
        str(r['NOMBRE']).strip(),
        str(r['SIGLAS']).strip().upper(),
        str(r['CLASIFICACION']).strip(),
    ))

# --- 2. Importar municipios ---
municipios = pd.read_excel("Municipales.xlsx")
for _, r in municipios.iterrows():
    clave = f"MUN_{int(r['NUM']):05d}"
    cur.execute("""
        INSERT OR REPLACE INTO municipios (clave, nombre, siglas, clasificacion, ambito, activo)
        VALUES (?, ?, ?, ?, 'MUNICIPAL', 1)
    """, (
        clave,
        str(r['NOMBRE']).strip(),
        str(r['SIGLAS']).strip().upper(),
        str(r['CLASIFICACION']).strip(),
    ))

# --- 3. Importar usuarios ---
usuarios = pd.read_excel("Usuarios_SASP_2025.xlsx")
for _, r in usuarios.iterrows():
    usuario = str(r['Usuario']).strip()
    clave_hash = hashlib.sha256(str(r['Clave']).encode()).hexdigest()
    nombre = str(r['Nombre completo']).strip()
    entes = str(r['Entes asignados']).strip().upper()
    cur.execute("""
        INSERT OR REPLACE INTO usuarios (nombre, usuario, clave, entes)
        VALUES (?, ?, ?, ?)
    """, (nombre, usuario, clave_hash, entes))

conn.commit()
conn.close()
print("✅ Catálogos y usuarios cargados correctamente en scil.db")

