"""
Configuración centralizada para SCIL
Sistema de Cruce de Información Laboral
"""

import os
from pathlib import Path

# Directorio raíz del proyecto
BASE_DIR = Path(__file__).parent.absolute()


class Config:
    """Configuración base para SCIL"""

    # Seguridad
    SECRET_KEY = os.getenv('SCIL_SECRET_KEY', os.urandom(32).hex())
    PASSWORD = os.getenv('SCIL_PASSWORD', 'scil2024')

    # Flask
    DEBUG = os.getenv('SCIL_DEBUG', 'False').lower() in ('true', '1', 't')
    HOST = os.getenv('SCIL_HOST', '0.0.0.0')
    PORT = int(os.getenv('SCIL_PORT', '4050'))
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32MB

    # Directorios
    UPLOAD_FOLDER = BASE_DIR / 'uploads'
    LOG_FOLDER = BASE_DIR / 'logs'
    DATA_FOLDER = BASE_DIR / 'data'
    STATIC_FOLDER = BASE_DIR / 'static'
    TEMPLATE_FOLDER = BASE_DIR / 'templates'

    # Base de datos
    DATABASE_PATH = DATA_FOLDER / 'scil.db'

    # Logging
    LOG_LEVEL = os.getenv('SCIL_LOG_LEVEL', 'INFO')
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5

    # Paginación
    RESULTS_PER_PAGE = int(os.getenv('SCIL_RESULTS_PER_PAGE', '20'))

    # Archivos permitidos
    ALLOWED_EXTENSIONS = {'.xlsx', '.xls'}

    @classmethod
    def init_app(cls):
        """Inicializa directorios necesarios"""
        for folder in [cls.UPLOAD_FOLDER, cls.LOG_FOLDER, cls.DATA_FOLDER]:
            folder.mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate_file(cls, filename):
        """Valida si un archivo tiene extensión permitida"""
        return Path(filename).suffix.lower() in cls.ALLOWED_EXTENSIONS


class DevelopmentConfig(Config):
    """Configuración para desarrollo"""
    DEBUG = True


class ProductionConfig(Config):
    """Configuración para producción"""
    DEBUG = False


# Mapeo de configuraciones
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config(env=None):
    """Obtiene la configuración según el entorno"""
    if env is None:
        env = os.getenv('SCIL_ENV', 'default')
    return config.get(env, config['default'])
