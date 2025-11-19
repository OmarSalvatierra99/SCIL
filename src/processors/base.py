"""
Clase base para procesadores de SCIL
Contiene funcionalidad común para evitar duplicación de código
"""

import pandas as pd
import re
from datetime import datetime, date
from src.utils.logger import SCILLogger


class BaseProcessor:
    """
    Clase base con métodos comunes para procesadores de datos

    Proporciona:
    - Limpieza y normalización de RFC
    - Limpieza y normalización de fechas
    - Detección automática de columnas
    - Extracción de nombres de entes
    - Sistema de logging integrado
    """

    def __init__(self, logger_name='Processor'):
        self.column_cache = {}
        self.logger = SCILLogger.get_logger(logger_name)

    # ========================================================
    # LIMPIEZA Y NORMALIZACIÓN
    # ========================================================

    def limpiar_rfc(self, rfc):
        """
        Limpia y estandariza un RFC

        Args:
            rfc: RFC a limpiar (puede ser string, número o None)

        Returns:
            str: RFC limpio (10-13 caracteres alfanuméricos) o None
        """
        if pd.isna(rfc):
            return None

        rfc_s = str(rfc).strip().upper()
        rfc_s = re.sub(r'[^A-Z0-9]', '', rfc_s)

        if 10 <= len(rfc_s) <= 13:
            return rfc_s

        self.logger.warning(f"RFC inválido (longitud {len(rfc_s)}): {rfc}")
        return None

    def limpiar_fecha(self, fecha):
        """
        Convierte fecha a formato 'YYYY-MM-DD'

        Maneja:
        - datetime objects
        - date objects
        - Strings en varios formatos
        - Números seriales de Excel

        Args:
            fecha: Fecha en cualquier formato

        Returns:
            str: Fecha en formato 'YYYY-MM-DD' o None
        """
        if pd.isna(fecha):
            return None

        # Si ya es datetime
        if isinstance(fecha, datetime):
            return fecha.strftime('%Y-%m-%d')

        # Si es date
        if isinstance(fecha, date):
            return fecha.strftime('%Y-%m-%d')

        # Convertir a string y validar
        s = str(fecha).strip()
        if not s or s.lower() in ['nan', 'nat', 'none', 'null', '']:
            return None

        try:
            # Serial de Excel (número)
            if isinstance(fecha, (int, float)):
                f = pd.to_datetime(fecha, unit='D', origin='1899-12-30')
                return f.strftime('%Y-%m-%d')

            # String con formato variable
            f = pd.to_datetime(s, errors='coerce', dayfirst=True)
            if pd.isna(f):
                self.logger.warning(f"Fecha no reconocida: {s}")
                return None

            return f.strftime('%Y-%m-%d')

        except Exception as e:
            self.logger.warning(f"Error procesando fecha '{fecha}': {e}")
            return None

    def _to_date(self, ymd_string):
        """
        Convierte string 'YYYY-MM-DD' a objeto date

        Args:
            ymd_string: String en formato 'YYYY-MM-DD'

        Returns:
            date: Objeto date o None
        """
        if not ymd_string:
            return None

        try:
            return datetime.strptime(ymd_string, '%Y-%m-%d').date()
        except Exception as e:
            self.logger.warning(f"Error convirtiendo '{ymd_string}' a date: {e}")
            return None

    # ========================================================
    # DETECCIÓN Y EXTRACCIÓN
    # ========================================================

    def extraer_ente_de_nombre_hoja(self, sheet_name):
        """
        Extrae el nombre del ente del nombre de la hoja Excel

        Convención: "ENTE_resto_del_nombre"
        El prefijo antes del primer '_' se considera el ente

        Args:
            sheet_name: Nombre de la hoja Excel

        Returns:
            str: Nombre del ente
        """
        partes = str(sheet_name).split('_')
        ente = partes[0] if partes else str(sheet_name)
        self.logger.debug(f"Hoja '{sheet_name}' -> Ente '{ente}'")
        return ente

    def detectar_columna(self, columns, keywords, cache_key=None):
        """
        Detecta una columna por palabras clave

        Args:
            columns: Lista de nombres de columnas
            keywords: Lista de palabras clave a buscar
            cache_key: Clave para caché (opcional)

        Returns:
            str: Nombre de la columna encontrada o None
        """
        if cache_key and cache_key in self.column_cache:
            return self.column_cache[cache_key]

        cols = [str(c) for c in columns]

        for col in cols:
            col_upper = col.upper()
            if any(kw.upper() in col_upper for kw in keywords):
                if cache_key:
                    self.column_cache[cache_key] = col
                self.logger.debug(f"Columna detectada para {keywords}: {col}")
                return col

        self.logger.warning(f"No se encontró columna para palabras clave: {keywords}")
        return None

    # ========================================================
    # VALIDACIÓN DE SOLAPES
    # ========================================================

    def _overlap(self, a_start, a_end, b_start, b_end):
        """
        Verifica si dos rangos se solapan (inclusivo)

        Args:
            a_start, a_end: Inicio y fin del rango A
            b_start, b_end: Inicio y fin del rango B

        Returns:
            bool: True si hay solape
        """
        return (a_start <= b_end) and (b_start <= a_end)

    # ========================================================
    # MÉTODOS ABSTRACTOS (a implementar en subclases)
    # ========================================================

    def procesar_archivo(self, filepath):
        """
        Procesa un archivo Excel

        Debe ser implementado por las subclases

        Args:
            filepath: Ruta al archivo Excel

        Returns:
            list: Lista de resultados procesados
        """
        raise NotImplementedError("Las subclases deben implementar procesar_archivo()")

    def detectar_columnas(self, df, ente):
        """
        Detecta columnas específicas del tipo de análisis

        Debe ser implementado por las subclases

        Args:
            df: DataFrame de pandas
            ente: Nombre del ente

        Returns:
            tuple: Tupla con nombres de columnas detectadas
        """
        raise NotImplementedError("Las subclases deben implementar detectar_columnas()")
