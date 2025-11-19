"""
Sistema de logging centralizado para SCIL
Crea logs rotativos con diferentes niveles de detalle
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime


class SCILLogger:
    """
    Gestor centralizado de logs para SCIL

    Características:
    - Logs rotativos (max 10MB por archivo, 5 backups)
    - Formato consistente con timestamps
    - Niveles: DEBUG, INFO, WARNING, ERROR, CRITICAL
    - Logs tanto en archivo como consola
    """

    _loggers = {}

    @classmethod
    def get_logger(cls, name='SCIL', log_dir='logs', level=logging.INFO):
        """
        Obtiene o crea un logger configurado

        Args:
            name: Nombre del logger (módulo/componente)
            log_dir: Directorio donde guardar los logs
            level: Nivel mínimo de logging

        Returns:
            logging.Logger configurado
        """
        if name in cls._loggers:
            return cls._loggers[name]

        # Asegurar que existe el directorio de logs
        os.makedirs(log_dir, exist_ok=True)

        # Crear logger
        logger = logging.getLogger(name)
        logger.setLevel(level)

        # Evitar duplicación de handlers
        if logger.handlers:
            return logger

        # Formato detallado para logs
        formatter = logging.Formatter(
            '%(asctime)s | %(name)-12s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Handler para archivo principal (rotativo)
        log_file = os.path.join(log_dir, f'{name.lower()}.log')
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Handler para errores (archivo separado)
        error_file = os.path.join(log_dir, f'{name.lower()}_errors.log')
        error_handler = RotatingFileHandler(
            error_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)

        # Handler para consola (más simple)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            '%(levelname)s | %(name)s | %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        cls._loggers[name] = logger
        logger.info(f"Logger '{name}' inicializado correctamente")

        return logger

    @classmethod
    def log_session_start(cls, logger, session_info):
        """Registra el inicio de una sesión de análisis"""
        logger.info("=" * 80)
        logger.info(f"NUEVA SESIÓN DE ANÁLISIS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)
        for key, value in session_info.items():
            logger.info(f"  {key}: {value}")
        logger.info("=" * 80)

    @classmethod
    def log_processing_stats(cls, logger, stats):
        """Registra estadísticas de procesamiento"""
        logger.info("-" * 80)
        logger.info("ESTADÍSTICAS DE PROCESAMIENTO:")
        for key, value in stats.items():
            logger.info(f"  {key}: {value}")
        logger.info("-" * 80)
