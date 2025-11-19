"""
Gestor de base de datos para SCIL
Maneja almacenamiento y consulta de resultados de análisis
"""

import sqlite3
import json
import hashlib
import threading
from datetime import datetime
from pathlib import Path
from src.utils.logger import SCILLogger


class DatabaseManager:
    """
    Gestor centralizado de base de datos SQLite

    Características:
    - Histórico completo de análisis
    - Detección de duplicados mediante hash
    - Clasificación por tipo de análisis (patrones/horarios)
    - Thread-safe
    - Sistema de logging integrado
    """

    def __init__(self, db_path='data/scil.db'):
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._initialized = False
        self.logger = SCILLogger.get_logger('Database')

        # Asegurar directorio
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.init_db()

    # ========================================================
    # CONEXIÓN Y CONFIGURACIÓN
    # ========================================================

    def get_connection(self):
        """
        Obtiene conexión SQLite segura por hilo

        Returns:
            sqlite3.Connection: Conexión thread-safe
        """
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row

        return self._local.conn

    def init_db(self):
        """Inicializa estructura de base de datos"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            self.logger.info("Inicializando base de datos...")

            # Tabla de resultados
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS resultados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo_analisis TEXT NOT NULL,
                    rfc TEXT NOT NULL,
                    datos TEXT NOT NULL,
                    hash_firma TEXT UNIQUE,
                    fecha_analisis TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_tipo (tipo_analisis),
                    INDEX idx_rfc (rfc),
                    INDEX idx_hash (hash_firma)
                )
            """)

            # Tabla de archivos procesados
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS archivos_procesados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre_archivo TEXT NOT NULL,
                    tipo_analisis TEXT,
                    total_registros INTEGER,
                    nuevos_registros INTEGER,
                    duplicados_omitidos INTEGER,
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

            self.logger.info("Base de datos inicializada correctamente")

        except Exception as e:
            self.logger.error(f"Error inicializando base de datos: {e}")
            raise

    def ensure_initialized(self):
        """Asegura que la base de datos está inicializada"""
        if not self._initialized:
            self.init_db()

    # ========================================================
    # GUARDADO DE RESULTADOS
    # ========================================================

    def guardar_resultados(self, resultados, tipo_analisis='patrones', nombre_archivo=None):
        """
        Guarda resultados de análisis evitando duplicados

        Args:
            resultados: Lista de hallazgos a guardar
            tipo_analisis: Tipo de análisis ('patrones' o 'horarios')
            nombre_archivo: Nombre del archivo procesado

        Returns:
            tuple: (nuevos, duplicados)
        """
        if not resultados:
            self.logger.warning("No hay resultados para guardar")
            return (0, 0)

        self.ensure_initialized()
        conn = self.get_connection()
        cursor = conn.cursor()

        nuevos = 0
        duplicados = 0

        cursor.execute('BEGIN TRANSACTION')

        try:
            for res in resultados:
                # Generar firma única
                firma_data = f"{res.get('rfc', '')}_{res.get('tipo_patron', '')}_{res.get('descripcion', '')}_{tipo_analisis}"
                firma = hashlib.sha256(firma_data.encode('utf-8')).hexdigest()

                # Verificar si existe
                cursor.execute("SELECT 1 FROM resultados WHERE hash_firma = ?", (firma,))
                if cursor.fetchone():
                    duplicados += 1
                    continue

                # Insertar nuevo registro
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

            # Registrar archivo procesado
            if nombre_archivo:
                cursor.execute("""
                    INSERT INTO archivos_procesados
                    (nombre_archivo, tipo_analisis, total_registros, nuevos_registros, duplicados_omitidos)
                    VALUES (?, ?, ?, ?, ?)
                """, (nombre_archivo, tipo_analisis, len(resultados), nuevos, duplicados))

            conn.commit()

            self.logger.info(
                f"Guardados {nuevos} registros nuevos "
                f"({duplicados} duplicados omitidos) - Tipo: {tipo_analisis}"
            )

            return (nuevos, duplicados)

        except Exception as e:
            conn.rollback()
            self.logger.error(f"Error guardando resultados: {e}")
            raise

    # ========================================================
    # CONSULTA DE RESULTADOS
    # ========================================================

    def obtener_resultados(self, tipo_analisis=None, limite=None):
        """
        Recupera resultados almacenados

        Args:
            tipo_analisis: Filtrar por tipo (None = todos)
            limite: Número máximo de resultados

        Returns:
            list: Lista de resultados
        """
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
            except json.JSONDecodeError as e:
                self.logger.warning(f"Error decodificando resultado: {e}")
                continue

        self.logger.info(f"Recuperados {len(resultados)} resultados ({tipo_analisis or 'todos'})")

        return resultados

    def comparar_con_historico(self, nuevos_resultados, tipo_analisis='patrones'):
        """
        Compara resultados nuevos con histórico

        Args:
            nuevos_resultados: Lista de nuevos hallazgos
            tipo_analisis: Tipo de análisis

        Returns:
            tuple: (nuevos, repetidos, desaparecidos)
        """
        self.ensure_initialized()
        conn = self.get_connection()
        cursor = conn.cursor()

        # Hash existentes en BD
        cursor.execute(
            "SELECT hash_firma FROM resultados WHERE tipo_analisis = ?",
            (tipo_analisis,)
        )
        antiguos = {r['hash_firma'] for r in cursor.fetchall()}

        nuevos_hash = set()
        nuevos_unicos = []
        repetidos = []

        # Clasificar nuevos resultados
        for r in nuevos_resultados:
            firma_data = f"{r.get('rfc', '')}_{r.get('tipo_patron', '')}_{r.get('descripcion', '')}_{tipo_analisis}"
            h = hashlib.sha256(firma_data.encode('utf-8')).hexdigest()

            if h in antiguos:
                repetidos.append(r)
            else:
                nuevos_unicos.append(r)

            nuevos_hash.add(h)

        # Hallazgos que desaparecieron
        desaparecidos_hash = antiguos - nuevos_hash
        desaparecidos = []

        if desaparecidos_hash:
            placeholders = ','.join(['?'] * len(desaparecidos_hash))
            cursor.execute(
                f"SELECT datos FROM resultados WHERE hash_firma IN ({placeholders})",
                tuple(desaparecidos_hash)
            )

            for row in cursor.fetchall():
                try:
                    desaparecidos.append(json.loads(row['datos']))
                except json.JSONDecodeError:
                    continue

        self.logger.info(
            f"Comparación completada: Nuevos={len(nuevos_unicos)}, "
            f"Repetidos={len(repetidos)}, Desaparecidos={len(desaparecidos)}"
        )

        return nuevos_unicos, repetidos, desaparecidos

    # ========================================================
    # UTILIDADES
    # ========================================================

    def obtener_archivos_procesados(self, tipo_analisis=None, limite=50):
        """
        Obtiene histórico de archivos procesados

        Args:
            tipo_analisis: Filtrar por tipo (None = todos)
            limite: Número máximo de registros

        Returns:
            list: Lista de archivos procesados
        """
        self.ensure_initialized()
        conn = self.get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM archivos_procesados"
        params = []

        if tipo_analisis:
            query += " WHERE tipo_analisis = ?"
            params.append(tipo_analisis)

        query += " ORDER BY fecha_procesamiento DESC"
        query += f" LIMIT {int(limite)}"

        cursor.execute(query, tuple(params))

        return [dict(r) for r in cursor.fetchall()]

    def obtener_estadisticas(self):
        """
        Obtiene estadísticas generales de la base de datos

        Returns:
            dict: Estadísticas generales
        """
        self.ensure_initialized()
        conn = self.get_connection()
        cursor = conn.cursor()

        stats = {}

        # Total de resultados
        cursor.execute("SELECT COUNT(*) as total FROM resultados")
        stats['total_resultados'] = cursor.fetchone()['total']

        # Por tipo de análisis
        cursor.execute("""
            SELECT tipo_analisis, COUNT(*) as total
            FROM resultados
            GROUP BY tipo_analisis
        """)
        stats['por_tipo'] = {r['tipo_analisis']: r['total'] for r in cursor.fetchall()}

        # RFCs únicos
        cursor.execute("SELECT COUNT(DISTINCT rfc) as total FROM resultados")
        stats['rfcs_unicos'] = cursor.fetchone()['total']

        # Archivos procesados
        cursor.execute("SELECT COUNT(*) as total FROM archivos_procesados")
        stats['archivos_procesados'] = cursor.fetchone()['total']

        return stats

    def __del__(self):
        """Cierra conexión al destruir objeto"""
        if hasattr(self._local, 'conn'):
            self._local.conn.close()
