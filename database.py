# ===========================================================
# database.py — SCIL QNA 2025 / Gestor de Base de Datos Auditor
# Versión multiusuario con control de entes y contraseñas SHA256
# ===========================================================

import sqlite3
import json
import os
import hashlib
import threading
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_path='scil.db'):
        self.db_path = db_path
        self._local = threading.local()
        self._initialized = False
        self.init_db()

    # -------------------------------------------------------
    # Conexión y configuración
    # -------------------------------------------------------
    def get_connection(self):
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def init_db(self):
        conn = self.get_connection()
        cur = conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS resultados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo_analisis TEXT NOT NULL,
                rfc TEXT NOT NULL,
                datos TEXT NOT NULL,
                hash_firma TEXT UNIQUE,
                fecha_analisis TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS archivos_procesados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_archivo TEXT NOT NULL,
                tipo_analisis TEXT,
                total_registros INTEGER,
                fecha_procesamiento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                usuario TEXT UNIQUE NOT NULL,
                clave TEXT NOT NULL,
                entes TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tipo ON resultados(tipo_analisis);
            CREATE INDEX IF NOT EXISTS idx_rfc_tipo ON resultados(rfc, tipo_analisis);
            CREATE INDEX IF NOT EXISTS idx_hash ON resultados(hash_firma);
            CREATE INDEX IF NOT EXISTS idx_fecha ON resultados(fecha_analisis);
        """)
        conn.commit()
        self._initialized = True
        print("✅ Base de datos inicializada correctamente.")

    # -------------------------------------------------------
    # Gestión de usuarios
    # -------------------------------------------------------
    def get_usuario(self, usuario, clave):
        """Valida usuario por nombre y contraseña (hash SHA256)."""
        conn = self.get_connection()
        cur = conn.cursor()

        clave_hash = hashlib.sha256(clave.encode('utf-8')).hexdigest()
        cur.execute("SELECT * FROM usuarios WHERE usuario=? AND clave=?", (usuario, clave_hash))
        row = cur.fetchone()

        if not row:
            return None

        data = dict(row)
        entes = [e.strip().upper() for e in data.get("entes", "").split(",") if e.strip()]
        # Si el usuario tiene todos los entes (Odilia, Víctor)
        if len(entes) > 40 or "*" in entes:
            entes = []
        data["entes"] = entes
        return data

    # -------------------------------------------------------
    # Comparación y guardado de resultados
    # -------------------------------------------------------
    def comparar_con_historico(self, nuevos_resultados, tipo_analisis='laboral'):
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT hash_firma FROM resultados WHERE tipo_analisis=?", (tipo_analisis,))
        antiguos = {r['hash_firma'] for r in cur.fetchall()}

        nuevos_unicos, repetidos, nuevos_hash = [], [], set()
        for res in nuevos_resultados:
            firma = hashlib.sha256(
                f"{res.get('rfc','')}_{res.get('tipo_patron','')}_{res.get('descripcion','')}_{tipo_analisis}".encode('utf-8')
            ).hexdigest()
            res['hash_firma'] = firma
            if firma in antiguos:
                repetidos.append(res)
            else:
                nuevos_unicos.append(res)
            nuevos_hash.add(firma)

        desaparecidos_hash = antiguos - nuevos_hash
        desaparecidos = []
        if desaparecidos_hash:
            qmarks = ','.join(['?'] * len(desaparecidos_hash))
            cur.execute(f"SELECT datos FROM resultados WHERE hash_firma IN ({qmarks})", tuple(desaparecidos_hash))
            for row in cur.fetchall():
                try:
                    desaparecidos.append(json.loads(row['datos']))
                except:
                    continue

        print(f"🔍 Comparación QNA: {len(nuevos_unicos)} nuevos, {len(repetidos)} repetidos, {len(desaparecidos)} desaparecidos.")
        return nuevos_unicos, repetidos, desaparecidos

    # -------------------------------------------------------
    # Guardado
    # -------------------------------------------------------
    def guardar_resultados(self, resultados, tipo_analisis='laboral', nombre_archivo=None):
        if not resultados:
            return 0
        conn = self.get_connection()
        cur = conn.cursor()
        nuevos = 0
        cur.execute('BEGIN TRANSACTION')

        try:
            for res in resultados:
                firma = res.get('hash_firma') or hashlib.sha256(
                    f"{res.get('rfc','')}_{res.get('tipo_patron','')}_{res.get('descripcion','')}_{tipo_analisis}".encode('utf-8')
                ).hexdigest()
                cur.execute("SELECT 1 FROM resultados WHERE hash_firma=?", (firma,))
                if cur.fetchone():
                    continue
                cur.execute("""
                    INSERT INTO resultados (tipo_analisis, rfc, datos, hash_firma)
                    VALUES (?, ?, ?, ?)
                """, (tipo_analisis, res.get('rfc',''), json.dumps(res, ensure_ascii=False), firma))
                nuevos += 1

            if nombre_archivo:
                cur.execute("""
                    INSERT INTO archivos_procesados (nombre_archivo, tipo_analisis, total_registros)
                    VALUES (?, ?, ?)
                """, (nombre_archivo, tipo_analisis, len(resultados)))

            conn.commit()
            print(f"💾 {nuevos} resultados guardados.")
        except Exception as e:
            conn.rollback()
            print(f"❌ Error guardando resultados: {e}")
            raise
        return nuevos

    # -------------------------------------------------------
    # Lectura con paginación
    # -------------------------------------------------------
    def obtener_resultados_paginados(self, tipo_analisis=None, busqueda=None, pagina=1, limite=50):
        conn = self.get_connection()
        cur = conn.cursor()

        base = "FROM resultados WHERE 1=1"
        params = []

        if tipo_analisis:
            base += " AND tipo_analisis=?"
            params.append(tipo_analisis)
        if busqueda:
            base += " AND datos LIKE ?"
            params.append(f"%{busqueda}%")

        cur.execute(f"SELECT COUNT(1) {base}", tuple(params))
        total = cur.fetchone()[0]
        offset = (pagina - 1) * limite
        cur.execute(f"SELECT datos {base} ORDER BY fecha_analisis DESC LIMIT ? OFFSET ?", tuple(params + [limite, offset]))
        filas = cur.fetchall()

        resultados = []
        for f in filas:
            try:
                resultados.append(json.loads(f['datos']))
            except:
                continue
        return resultados, total

