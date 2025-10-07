# ===========================================================
# app.py  —  SCIL (Sistema de Cruce de Información Laboral)
# Versión completa con análisis de patrones y cruces de horarios
# ===========================================================

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import os
import secrets
import csv
import io
from math import ceil
from datetime import datetime

from data_processor import DataProcessor
from horarios_processor import HorariosProcessor
from database import DatabaseManager

# -----------------------------------------------------------
# Configuración base
# -----------------------------------------------------------
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB

SECRET_PASSWORD = os.getenv('SCIL_PASSWORD', 'scil2024')
RESULTS_PER_PAGE = 20

# -----------------------------------------------------------
# Inicialización de componentes
# -----------------------------------------------------------
try:
    db_manager = DatabaseManager()
    data_processor = DataProcessor()
    horarios_processor = HorariosProcessor()
    print("✅ Componentes inicializados correctamente")
except Exception as e:
    print(f"❌ Error inicializando componentes: {e}")
    raise

# -----------------------------------------------------------
# Utilidades
# -----------------------------------------------------------
@app.before_request
def ensure_directories():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)

# -----------------------------------------------------------
# Autenticación
# -----------------------------------------------------------
@app.route('/')
def index():
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == SECRET_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Clave incorrecta")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# -----------------------------------------------------------
# Dashboard principal
# -----------------------------------------------------------
@app.route('/dashboard')
def dashboard():
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

# ===========================================================
# 1️⃣ ANÁLISIS DE PATRONES LABORALES
# ===========================================================
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'logged_in' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'No se encontró archivo'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó archivo'}), 400
    if not file.filename.endswith('.xlsx'):
        return jsonify({'error': 'Solo se permiten archivos Excel (.xlsx)'}), 400

    filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filename)

    try:
        print(f"🔄 Procesando archivo de patrones: {filename}")
        resultados = data_processor.procesar_archivo(filename)

        nuevos, repetidos, _ = db_manager.comparar_con_historico(resultados, tipo_analisis='patrones')
        db_manager.guardar_resultados(resultados, tipo_analisis='patrones', nombre_archivo=file.filename)

        mensaje = (
            f"Se procesaron {len(resultados)} hallazgos totales. "
            f"Nuevos: {len(nuevos)} | Repetidos: {len(repetidos)}."
        )
        print(f"✅ Análisis completado: {mensaje}")

        return jsonify({
            'success': True,
            'mensaje': mensaje,
            'total_resultados': len(resultados),
            'nuevos': len(nuevos),
            'repetidos': len(repetidos)
        })

    except Exception as e:
        print(f"❌ Error procesando archivo: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(filename):
            os.remove(filename)

@app.route('/resultados')
def mostrar_resultados():
    if 'logged_in' not in session:
        return redirect(url_for('login'))

    try:
        page = int(request.args.get('page', 1))
        search_query = request.args.get('search', '').lower()
        resultados = db_manager.obtener_resultados(tipo_analisis='patrones')

        # Filtro simple por RFC o descripción
        if search_query:
            resultados = [
                r for r in resultados
                if search_query in r.get('rfc', '').lower()
                or search_query in r.get('descripcion', '').lower()
            ]

        total_resultados = len(resultados)
        total_paginas = ceil(total_resultados / RESULTS_PER_PAGE)
        start = (page - 1) * RESULTS_PER_PAGE
        end = start + RESULTS_PER_PAGE
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
        print(f"❌ Error mostrando resultados: {e}")
        return render_template('resultados.html', resultados=[], total_paginas=1, total_resultados=0)

# ===========================================================
# 2️⃣ ANÁLISIS DE CRUCE DE HORARIOS DOCENTES
# ===========================================================
@app.route('/upload_horarios', methods=['POST'])
def upload_horarios():
    if 'logged_in' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'No se encontró archivo'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó archivo'}), 400
    if not file.filename.endswith('.xlsx'):
        return jsonify({'error': 'Solo se permiten archivos Excel (.xlsx)'}), 400

    filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filename)

    try:
        print(f"🔄 Procesando archivo de horarios: {filename}")
        resultados = horarios_processor.procesar_archivo(filename)

        nuevos, repetidos, _ = db_manager.comparar_con_historico(resultados, tipo_analisis='horarios')
        db_manager.guardar_resultados(resultados, tipo_analisis='horarios', nombre_archivo=file.filename)

        mensaje = (
            f"Se analizaron {len(resultados)} posibles cruces de horario. "
            f"Nuevos: {len(nuevos)} | Repetidos: {len(repetidos)}."
        )
        print(f"✅ Análisis de horarios completado: {mensaje}")

        return jsonify({
            'success': True,
            'mensaje': mensaje,
            'total_resultados': len(resultados),
            'nuevos': len(nuevos),
            'repetidos': len(repetidos)
        })

    except Exception as e:
        print(f"❌ Error procesando horarios: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(filename):
            os.remove(filename)

@app.route('/resultados_horarios')
def mostrar_resultados_horarios():
    if 'logged_in' not in session:
        return redirect(url_for('login'))

    try:
        page = int(request.args.get('page', 1))
        search_query = request.args.get('search', '').lower()
        resultados = db_manager.obtener_resultados(tipo_analisis='horarios')

        if search_query:
            resultados = [
                r for r in resultados
                if search_query in r.get('rfc', '').lower()
                or search_query in r.get('descripcion', '').lower()
            ]

        total_resultados = len(resultados)
        total_paginas = ceil(total_resultados / RESULTS_PER_PAGE)
        start = (page - 1) * RESULTS_PER_PAGE
        end = start + RESULTS_PER_PAGE
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
        print(f"❌ Error mostrando resultados de horarios: {e}")
        return render_template('resultados_horarios.html', resultados=[], total_paginas=1, total_resultados=0)

# ===========================================================
# Exportación CSV
# ===========================================================
@app.route('/exportar/csv/<tipo>')
def exportar_csv(tipo):
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    try:
        resultados = db_manager.obtener_resultados(tipo_analisis=tipo)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['RFC', 'Tipo de patrón', 'Severidad', 'Entes', 'Descripción', 'Fecha'])

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
        return send_file(
            csv_bytes,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f"{tipo}_resultados_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        )
    except Exception as e:
        print(f"❌ Error exportando CSV: {e}")
        return jsonify({'error': str(e)}), 500

# -----------------------------------------------------------
# Inicialización
# -----------------------------------------------------------
def init_app():
    print("🚀 Inicializando aplicación SCIL...")
    os.makedirs('uploads', exist_ok=True)
    db_manager.ensure_initialized()
    print("✅ SCIL listo para análisis")

if __name__ == '__main__':
    init_app()
    app.run(host='0.0.0.0', port=4050, debug=True)

