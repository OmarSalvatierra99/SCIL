"""
SCIL - Sistema de Cruce de Información Laboral
Aplicación principal Flask

Sistema de auditoría de relaciones laborales y horarios docentes
"""

import secrets
from flask import Flask
from pathlib import Path

from config import Config, get_config
from src.database.manager import DatabaseManager
from src.processors.patterns import PatternsProcessor
from src.processors.schedules import SchedulesProcessor
from src.utils.logger import SCILLogger
from src.web.routes import main_bp, patterns_bp, schedules_bp, init_routes


def create_app(config_name='default'):
    """
    Factory para crear la aplicación Flask

    Args:
        config_name: Nombre de la configuración ('development', 'production', 'default')

    Returns:
        Flask: Aplicación configurada
    """
    # Obtener configuración
    config_class = get_config(config_name)

    # Inicializar directorios
    config_class.init_app()

    # Logger principal
    logger = SCILLogger.get_logger('SCIL')
    logger.info("=" * 80)
    logger.info("Inicializando SCIL - Sistema de Cruce de Información Laboral")
    logger.info("=" * 80)

    # Crear app Flask
    app = Flask(
        __name__,
        template_folder=str(config_class.TEMPLATE_FOLDER),
        static_folder=str(config_class.STATIC_FOLDER)
    )

    # Configurar Flask
    app.secret_key = config_class.SECRET_KEY
    app.config['UPLOAD_FOLDER'] = str(config_class.UPLOAD_FOLDER)
    app.config['MAX_CONTENT_LENGTH'] = config_class.MAX_CONTENT_LENGTH

    logger.info(f"Configuración: {config_name}")
    logger.info(f"Debug: {config_class.DEBUG}")
    logger.info(f"Host: {config_class.HOST}:{config_class.PORT}")

    # Inicializar componentes
    try:
        logger.info("Inicializando componentes...")

        db_manager = DatabaseManager(db_path=str(config_class.DATABASE_PATH))
        patterns_processor = PatternsProcessor()
        schedules_processor = SchedulesProcessor()

        logger.info("✅ Base de datos inicializada")
        logger.info("✅ Procesador de patrones inicializado")
        logger.info("✅ Procesador de horarios inicializado")

        # Inicializar rutas con dependencias
        init_routes(db_manager, patterns_processor, schedules_processor)
        logger.info("✅ Rutas web configuradas")

    except Exception as e:
        logger.error(f"❌ Error inicializando componentes: {e}")
        raise

    # Registrar blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(patterns_bp)
    app.register_blueprint(schedules_bp)

    logger.info("✅ Blueprints registrados")

    # Hook antes de cada request
    @app.before_request
    def ensure_directories():
        """Asegura que existan los directorios necesarios"""
        config_class.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

    # Manejador de errores
    @app.errorhandler(404)
    def not_found(error):
        logger.warning(f"Página no encontrada: {error}")
        return "Página no encontrada", 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Error interno del servidor: {error}")
        return "Error interno del servidor", 500

    logger.info("=" * 80)
    logger.info("✅ SCIL inicializado correctamente")
    logger.info("=" * 80)

    return app


def main():
    """Función principal para ejecutar la aplicación"""
    import os

    # Obtener configuración del entorno
    env = os.getenv('SCIL_ENV', 'default')
    config_class = get_config(env)

    # Crear y ejecutar app
    app = create_app(env)

    print("\n" + "=" * 80)
    print("🚀 SCIL - Sistema de Cruce de Información Laboral")
    print("=" * 80)
    print(f"📊 Servidor: http://{config_class.HOST}:{config_class.PORT}")
    print(f"🔐 Contraseña: {config_class.PASSWORD}")
    print(f"📁 Base de datos: {config_class.DATABASE_PATH}")
    print(f"📝 Logs: {config_class.LOG_FOLDER}")
    print("=" * 80 + "\n")

    app.run(
        host=config_class.HOST,
        port=config_class.PORT,
        debug=config_class.DEBUG
    )


if __name__ == '__main__':
    main()
