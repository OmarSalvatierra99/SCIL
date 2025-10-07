# ===========================================================
# database.py  —  SCIL / Gestor de Base de Datos Auditor
# Arquitectura con histórico, clasificación por tipo de análisis
# y comparativo incremental.
# ===========================================================

import sqlite3
import json
import os
from datetime import datetime
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
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            print("🔄 Inicializando base de datos...")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS resultados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo_analisis TEXT NOT NULL,          -- 'patrones' o 'horarios'
                    rfc TEXT NOT NULL,
                    datos TEXT NOT NULL,
                    hash_firma TEXT,                      -- hash único del hallazgo (para evitar duplicados)
                    fecha_analisis TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS archivos_procesados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre_archivo TEXT NOT NULL,
                    tipo_analisis TEXT,
                    total_registros INTEGER,
                    fecha_procesamiento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Índices para rendimiento
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tipo ON resultados(tipo_analisis)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_rfc_tipo ON resultados(rfc, tipo_analisis)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_hash ON resultados(hash_firma)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_fecha ON resultados(fecha_analisis)')

            conn.commit()
            self._initialized = True
            print("✅ Base de datos lista")
        except Exception as e:
            print(f"❌ Error inicializando base de datos: {e}")
            raise

    def ensure_initialized(self):
        if not self._initialized:
            self.init_db()

    # -------------------------------------------------------
    # Guardado de resultados (con histórico y comparación)
    # -------------------------------------------------------
    def guardar_resultados(self, resultados, tipo_analisis='patrones', nombre_archivo=None):
        """
        Guarda nuevos resultados sin eliminar anteriores.
        Evita duplicados mediante hash_firma único por RFC + tipo + descripción.
        """
        if not resultados:
            print("⚠️ No hay resultados para guardar.")
            return

        import hashlib

        self.ensure_initialized()
        conn = self.get_connection()
        cursor = conn.cursor()

        nuevos = 0
        duplicados = 0

        cursor.execute('BEGIN TRANSACTION')
        try:
            for res in resultados:
                # Se genera una firma única de cada hallazgo
                firma = hashlib.sha256(
                    f"{res.get('rfc','')}_{res.get('tipo_patron','')}_{res.get('descripcion','')}_{tipo_analisis}".encode('utf-8')
                ).hexdigest()

                # Verificar si ya existe
                cursor.execute("SELECT 1 FROM resultados WHERE hash_firma = ?", (firma,))
                if cursor.fetchone():
                    duplicados += 1
                    continue

                cursor.execute("""
                    INSERT INTO resultados (tipo_analisis, rfc, datos, hash_firma)
                    VALUES (?, ?, ?, ?)
                """, (
                    tipo_analisis,
                    res.get('rfc', ''),
                    json.dumps(res, ensure_ascii=False, default=str),
                    firma
                ))
                nuevos += 1

            # Registro de archivo procesado
            if nombre_archivo:
                cursor.execute("""
                    INSERT INTO archivos_procesados (nombre_archivo, tipo_analisis, total_registros)
                    VALUES (?, ?, ?)
                """, (nombre_archivo, tipo_analisis, len(resultados)))

            conn.commit()
            print(f"💾 Guardados {nuevos} nuevos resultados ({duplicados} duplicados omitidos).")

        except Exception as e:
            conn.rollback()
            print(f"❌ Error guardando resultados: {e}")
            raise

    # -------------------------------------------------------
    # Recuperación y comparación
    # -------------------------------------------------------
    def obtener_resultados(self, tipo_analisis=None, limite=None):
        """Recupera resultados (por tipo o todos)."""
        self.ensure_initialized()
        conn = self.get_connection()
        cursor = conn.cursor()

        query = "SELECT datos FROM resultados"
        params = []
        if tipo_analisis:
            query += " WHERE tipo_analisis = ?"
            params.append(tipo_analisis)
        query += " ORDER BY fecha_analisis DESC"
        if limite:
            query += f" LIMIT {int(limite)}"

        cursor.execute(query, tuple(params))
        filas = cursor.fetchall()
        resultados = []
        for f in filas:
            try:
                resultados.append(json.loads(f['datos']))
            except json.JSONDecodeError:
                continue

        print(f"📊 Recuperados {len(resultados)} resultados ({tipo_analisis or 'todos'})")
        return resultados

    def comparar_con_historico(self, nuevos_resultados, tipo_analisis='patrones'):
        """
        Compara un conjunto nuevo de resultados con el histórico.
        Devuelve listas separadas: nuevos, repetidos, y desaparecidos.
        """
        import hashlib
        self.ensure_initialized()
        conn = self.get_connection()
        cursor = conn.cursor()

        # Hash actuales en BD
        cursor.execute("SELECT hash_firma FROM resultados WHERE tipo_analisis = ?", (tipo_analisis,))
        antiguos = {r['hash_firma'] for r in cursor.fetchall()}

        nuevos_hash = set()
        nuevos_unicos = []
        repetidos = []

        for r in nuevos_resultados:
            h = hashlib.sha256(
                f"{r.get('rfc','')}_{r.get('tipo_patron','')}_{r.get('descripcion','')}_{tipo_analisis}".encode('utf-8')
            ).hexdigest()
            if h in antiguos:
                repetidos.append(r)
            else:
                nuevos_unicos.append(r)
            nuevos_hash.add(h)

        desaparecidos_hash = antiguos - nuevos_hash
        desaparecidos = []
        if desaparecidos_hash:
            cursor.execute(
                f"SELECT datos FROM resultados WHERE hash_firma IN ({','.join(['?']*len(desaparecidos_hash))})",
                tuple(desaparecidos_hash)
            )
            for row in cursor.fetchall():
                try:
                    desaparecidos.append(json.loads(row['datos']))
                except:
                    continue

        print(f"🔍 Comparación completada → Nuevos: {len(nuevos_unicos)}, Repetidos: {len(repetidos)}, Desaparecidos: {len(desaparecidos)}")
        return nuevos_unicos, repetidos, desaparecidos

    # -------------------------------------------------------
    # Utilidades
    # -------------------------------------------------------
    def obtener_archivos_procesados(self, tipo_analisis=None):
        """Devuelve histórico de archivos analizados."""
        self.ensure_initialized()
        conn = self.get_connection()
        cursor = conn.cursor()
        query = "SELECT * FROM archivos_procesados"
        params = []
        if tipo_analisis:
            query += " WHERE tipo_analisis = ?"
            params.append(tipo_analisis)
        query += " ORDER BY fecha_procesamiento DESC"
        cursor.execute(query, tuple(params))
        return [dict(r) for r in cursor.fetchall()]

    def __del__(self):
        if hasattr(self._local, 'conn'):
            self._local.conn.close()

