"""
Rutas web para SCIL
Maneja todos los endpoints de la aplicación Flask
"""

import os
import csv
import io
from math import ceil
from datetime import datetime
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, jsonify, send_file
)
from werkzeug.utils import secure_filename

from config import Config
from src.utils.logger import SCILLogger


# Crear blueprints
main_bp = Blueprint('main', __name__)
patterns_bp = Blueprint('patterns', __name__)
schedules_bp = Blueprint('schedules', __name__)

# Logger
logger = SCILLogger.get_logger('WebRoutes')

# Se inyectarán desde app.py
db_manager = None
patterns_processor = None
schedules_processor = None


def init_routes(db, patterns, schedules):
    """
    Inicializa las rutas con las dependencias necesarias

    Args:
        db: DatabaseManager instance
        patterns: PatternsProcessor instance
        schedules: SchedulesProcessor instance
    """
    global db_manager, patterns_processor, schedules_processor
    db_manager = db
    patterns_processor = patterns
    schedules_processor = schedules
    logger.info("Rutas inicializadas con dependencias")


# ========================================================
# RUTAS PRINCIPALES
# ========================================================

@main_bp.route('/')
def index():
    """Página principal - redirige a dashboard o login"""
    if 'logged_in' not in session:
        return redirect(url_for('main.login'))
    return redirect(url_for('main.dashboard'))


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login"""
    if request.method == 'POST':
        password = request.form.get('password')

        if password == Config.PASSWORD:
            session['logged_in'] = True
            logger.info("Usuario autenticado correctamente")
            return redirect(url_for('main.dashboard'))
        else:
            logger.warning("Intento de login fallido")
            return render_template('login.html', error="Contraseña incorrecta")

    return render_template('login.html')


@main_bp.route('/logout')
def logout():
    """Cerrar sesión"""
    session.pop('logged_in', None)
    logger.info("Usuario cerró sesión")
    return redirect(url_for('main.login'))


@main_bp.route('/dashboard')
def dashboard():
    """Dashboard principal"""
    if 'logged_in' not in session:
        return redirect(url_for('main.login'))

    # Obtener estadísticas
    stats = db_manager.obtener_estadisticas()

    return render_template('dashboard.html', stats=stats)


# ========================================================
# ANÁLISIS DE PATRONES LABORALES
# ========================================================

@patterns_bp.route('/upload', methods=['POST'])
def upload_patterns():
    """Subir y procesar archivo de patrones laborales"""
    if 'logged_in' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'No se encontró archivo'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No se seleccionó archivo'}), 400

    if not Config.validate_file(file.filename):
        return jsonify({'error': 'Solo se permiten archivos Excel (.xlsx, .xls)'}), 400

    # Guardar archivo temporalmente
    filename = secure_filename(file.filename)
    filepath = Config.UPLOAD_FOLDER / filename
    file.save(str(filepath))

    try:
        logger.info(f"Procesando archivo de patrones: {filename}")

        # Procesar archivo
        resultados = patterns_processor.procesar_archivo(str(filepath))

        # Comparar con histórico
        nuevos, repetidos, _ = db_manager.comparar_con_historico(
            resultados,
            tipo_analisis='patrones'
        )

        # Guardar resultados
        db_manager.guardar_resultados(
            resultados,
            tipo_analisis='patrones',
            nombre_archivo=filename
        )

        mensaje = (
            f"Se procesaron {len(resultados)} hallazgos totales. "
            f"Nuevos: {len(nuevos)} | Repetidos: {len(repetidos)}"
        )

        logger.info(f"Análisis de patrones completado: {mensaje}")

        return jsonify({
            'success': True,
            'mensaje': mensaje,
            'total_resultados': len(resultados),
            'nuevos': len(nuevos),
            'repetidos': len(repetidos)
        })

    except Exception as e:
        logger.error(f"Error procesando archivo de patrones: {e}")
        return jsonify({'error': str(e)}), 500

    finally:
        # Limpiar archivo temporal
        if filepath.exists():
            filepath.unlink()


@patterns_bp.route('/resultados')
def show_patterns_results():
    """Mostrar resultados de análisis de patrones"""
    if 'logged_in' not in session:
        return redirect(url_for('main.login'))

    try:
        page = int(request.args.get('page', 1))
        search_query = request.args.get('search', '').lower()

        resultados = db_manager.obtener_resultados(tipo_analisis='patrones')

        # Filtrar por búsqueda
        if search_query:
            resultados = [
                r for r in resultados
                if search_query in r.get('rfc', '').lower()
                or search_query in r.get('descripcion', '').lower()
            ]

        # Paginación
        total_resultados = len(resultados)
        total_paginas = ceil(total_resultados / Config.RESULTS_PER_PAGE)
        start = (page - 1) * Config.RESULTS_PER_PAGE
        end = start + Config.RESULTS_PER_PAGE
        resultados_paginados = resultados[start:end]

        return render_template(
            'resultados.html',
            resultados=resultados_paginados,
            pagina_actual=page,
            total_paginas=total_paginas,
            total_resultados=total_resultados,
            busqueda=search_query
        )

    except Exception as e:
        logger.error(f"Error mostrando resultados de patrones: {e}")
        return render_template(
            'resultados.html',
            resultados=[],
            pagina_actual=1,
            total_paginas=1,
            total_resultados=0,
            busqueda=''
        )


# ========================================================
# ANÁLISIS DE HORARIOS
# ========================================================

@schedules_bp.route('/upload_horarios', methods=['POST'])
def upload_schedules():
    """Subir y procesar archivo de horarios"""
    if 'logged_in' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'No se encontró archivo'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No se seleccionó archivo'}), 400

    if not Config.validate_file(file.filename):
        return jsonify({'error': 'Solo se permiten archivos Excel (.xlsx, .xls)'}), 400

    # Guardar archivo temporalmente
    filename = secure_filename(file.filename)
    filepath = Config.UPLOAD_FOLDER / filename
    file.save(str(filepath))

    try:
        logger.info(f"Procesando archivo de horarios: {filename}")

        # Procesar archivo
        resultados = schedules_processor.procesar_archivo(str(filepath))

        # Comparar con histórico
        nuevos, repetidos, _ = db_manager.comparar_con_historico(
            resultados,
            tipo_analisis='horarios'
        )

        # Guardar resultados
        db_manager.guardar_resultados(
            resultados,
            tipo_analisis='horarios',
            nombre_archivo=filename
        )

        mensaje = (
            f"Se analizaron {len(resultados)} posibles cruces de horario. "
            f"Nuevos: {len(nuevos)} | Repetidos: {len(repetidos)}"
        )

        logger.info(f"Análisis de horarios completado: {mensaje}")

        return jsonify({
            'success': True,
            'mensaje': mensaje,
            'total_resultados': len(resultados),
            'nuevos': len(nuevos),
            'repetidos': len(repetidos)
        })

    except Exception as e:
        logger.error(f"Error procesando archivo de horarios: {e}")
        return jsonify({'error': str(e)}), 500

    finally:
        # Limpiar archivo temporal
        if filepath.exists():
            filepath.unlink()


@schedules_bp.route('/resultados_horarios')
def show_schedules_results():
    """Mostrar resultados de análisis de horarios"""
    if 'logged_in' not in session:
        return redirect(url_for('main.login'))

    try:
        page = int(request.args.get('page', 1))
        search_query = request.args.get('search', '').lower()

        resultados = db_manager.obtener_resultados(tipo_analisis='horarios')

        # Filtrar por búsqueda
        if search_query:
            resultados = [
                r for r in resultados
                if search_query in r.get('rfc', '').lower()
                or search_query in r.get('descripcion', '').lower()
            ]

        # Paginación
        total_resultados = len(resultados)
        total_paginas = ceil(total_resultados / Config.RESULTS_PER_PAGE)
        start = (page - 1) * Config.RESULTS_PER_PAGE
        end = start + Config.RESULTS_PER_PAGE
        resultados_paginados = resultados[start:end]

        return render_template(
            'resultados_horarios.html',
            resultados=resultados_paginados,
            pagina_actual=page,
            total_paginas=total_paginas,
            total_resultados=total_resultados,
            busqueda=search_query
        )

    except Exception as e:
        logger.error(f"Error mostrando resultados de horarios: {e}")
        return render_template(
            'resultados_horarios.html',
            resultados=[],
            pagina_actual=1,
            total_paginas=1,
            total_resultados=0,
            busqueda=''
        )


# ========================================================
# EXPORTACIÓN
# ========================================================

@main_bp.route('/exportar/csv/<tipo>')
def export_csv(tipo):
    """Exportar resultados a CSV"""
    if 'logged_in' not in session:
        return redirect(url_for('main.login'))

    try:
        resultados = db_manager.obtener_resultados(tipo_analisis=tipo)

        output = io.StringIO()
        writer = csv.writer(output)

        # Encabezados
        writer.writerow([
            'RFC', 'Tipo de patrón', 'Severidad',
            'Entes', 'Descripción', 'Fecha'
        ])

        # Datos
        for r in resultados:
            writer.writerow([
                r.get('rfc', ''),
                r.get('tipo_patron', ''),
                r.get('severidad', ''),
                ', '.join(r.get('entes', [])),
                r.get('descripcion', ''),
                r.get('fecha_comun', '')
            ])

        output.seek(0)
        csv_bytes = io.BytesIO(output.getvalue().encode('utf-8-sig'))

        filename = f"{tipo}_resultados_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

        logger.info(f"Exportando {len(resultados)} resultados a CSV: {filename}")

        return send_file(
            csv_bytes,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"Error exportando CSV: {e}")
        return jsonify({'error': str(e)}), 500
