from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import os
from data_processor import DataProcessor
from database import DatabaseManager
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Clave de acceso (puedes cambiarla)
SECRET_PASSWORD = "scil2024"

# Inicializar componentes
db_manager = DatabaseManager()
data_processor = DataProcessor()

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

@app.route('/dashboard')
def dashboard():
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'logged_in' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'No se encontró archivo'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó archivo'}), 400

    if file and file.filename.endswith('.xlsx'):
        filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filename)

        # Procesar el archivo
        try:
            resultados = data_processor.procesar_archivo(filename)

            # Guardar en base de datos
            db_manager.guardar_resultados(resultados)

            # Calcular estadísticas
            total_duplicados = len(resultados)
            total_conflictos_fecha = sum(1 for r in resultados if r['tiene_conflicto_fecha'])
            entes_detectados = resultados[0]['entes_detectados'] if resultados else []

            return jsonify({
                'success': True,
                'resultados': resultados,
                'total_duplicados': total_duplicados,
                'total_conflictos_fecha': total_conflictos_fecha,
                'entes_detectados': entes_detectados,
                'mensaje': f'Se analizaron {len(entes_detectados)} entes: {", ".join(entes_detectados)}. Se encontraron {total_duplicados} duplicados, {total_conflictos_fecha} con conflictos de fecha'
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Formato no válido'}), 400

@app.route('/resultados')
def mostrar_resultados():
    if 'logged_in' not in session:
        return redirect(url_for('login'))

    resultados = db_manager.obtener_resultados()
    return render_template('resultados.html', resultados=resultados)

@app.route('/api/duplicados')
def api_duplicados():
    if 'logged_in' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    resultados = db_manager.obtener_resultados()
    return jsonify(resultados)

if __name__ == '__main__':
    # Crear directorios necesarios
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)

    app.run(host='0.0.0.0', port=4050, debug=True)
