# ===========================================================
# database.py — SCIL / Gestor de Base de Datos Auditor
# Incluye comparación con histórico, registro incremental y
# control de duplicados por hash_firma.
# ===========================================================

import sqlite3
import json
import os
from datetime import datetime
import hashlib
import threading


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
        """Obtiene conexión SQLite segura por hilo."""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def init_db(self):
        """Inicializa estructura de base de datos."""
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

            CREATE INDEX IF NOT EXISTS idx_tipo ON resultados(tipo_analisis);
            CREATE INDEX IF NOT EXISTS idx_rfc_tipo ON resultados(rfc, tipo_analisis);
            CREATE INDEX IF NOT EXISTS idx_hash ON resultados(hash_firma);
            CREATE INDEX IF NOT EXISTS idx_fecha ON resultados(fecha_analisis);
        """)
        conn.commit()
        self._initialized = True
        print("✅ Base de datos inicializada.")

    def ensure_initialized(self):
        if not self._initialized:
            self.init_db()

    # -------------------------------------------------------
    # Guardado y comparación con histórico
    # -------------------------------------------------------
    def comparar_con_historico(self, nuevos_resultados, tipo_analisis='laboral'):
        """
        Compara nuevos resultados con el histórico.
        Retorna: (nuevos, repetidos, desaparecidos)
        """
        self.ensure_initialized()
        conn = self.get_connection()
        cur = conn.cursor()

        cur.execute("SELECT hash_firma FROM resultados WHERE tipo_analisis = ?", (tipo_analisis,))
        antiguos = {r['hash_firma'] for r in cur.fetchall()}

        nuevos_hash = set()
        nuevos_unicos = []
        repetidos = []

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
            cur.execute(
                f"SELECT datos FROM resultados WHERE hash_firma IN ({','.join(['?'] * len(desaparecidos_hash))})",
                tuple(desaparecidos_hash)
            )
            for row in cur.fetchall():
                try:
                    desaparecidos.append(json.loads(row['datos']))
                except:
                    continue

        print(f"🔍 Comparación: {len(nuevos_unicos)} nuevos, {len(repetidos)} repetidos, {len(desaparecidos)} desaparecidos.")
        return nuevos_unicos, repetidos, desaparecidos

    def guardar_resultados(self, resultados, tipo_analisis='laboral', nombre_archivo=None):
        """Guarda resultados nuevos evitando duplicados por hash_firma."""
        if not resultados:
            return 0
        self.ensure_initialized()
        conn = self.get_connection()
        cur = conn.cursor()
        nuevos = 0
        cur.execute('BEGIN TRANSACTION')

        try:
            for res in resultados:
                firma = res.get('hash_firma')
                if not firma:
                    firma = hashlib.sha256(
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
            print(f"💾 {nuevos} resultados guardados en histórico.")
        except Exception as e:
            conn.rollback()
            print(f"❌ Error guardando resultados: {e}")
            raise
        return nuevos

    # -------------------------------------------------------
    # Recuperación con paginación
    # -------------------------------------------------------
    def obtener_resultados_paginados(self, tipo_analisis=None, busqueda=None, pagina=1, limite=50):
        """Recupera resultados con filtros y paginación."""
        self.ensure_initialized()
        conn = self.get_connection()
        cur = conn.cursor()

        base = "FROM resultados WHERE 1=1"
        params = []

        if tipo_analisis:
            base += " AND tipo_analisis = ?"
            params.append(tipo_analisis)

        if busqueda:
            base += " AND datos LIKE ?"
            params.append(f"%{busqueda}%")

        # total de registros
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

    # -------------------------------------------------------
    def obtener_archivos_procesados(self, tipo_analisis=None):
        conn = self.get_connection()
        cur = conn.cursor()
        q = "SELECT * FROM archivos_procesados"
        p = []
        if tipo_analisis:
            q += " WHERE tipo_analisis=?"
            p.append(tipo_analisis)
        q += " ORDER BY fecha_procesamiento DESC"
        cur.execute(q, tuple(p))
        return [dict(r) for r in cur.fetchall()]

