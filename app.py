# ===========================================================
# app.py — SCIL QNA 2025 / Sistema de Cruce de Información Laboral
# Soporte multiarchivo para análisis laboral y de horarios
# ===========================================================

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
from werkzeug.utils import secure_filename
from database import DatabaseManager
from data_processor import DataProcessor
from horarios_processor import HorariosProcessor
import os
from math import ceil

app = Flask(__name__)
app.secret_key = "scil_tlax_2025"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db_manager = DatabaseManager()
CLAVE_MAESTRA = "scil2024"

# ===========================================================
# LOGIN
# ===========================================================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        clave = request.form.get("clave")
        if clave == CLAVE_MAESTRA:
            session["autenticado"] = True
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Clave incorrecta")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ===========================================================
# DASHBOARD
# ===========================================================
@app.route("/dashboard")
def dashboard():
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    return render_template("dashboard.html")


# ===========================================================
# PROCESAMIENTO LABORAL (multiarchivo)
# ===========================================================
@app.route("/upload", methods=["POST"])
def upload_laboral():
    if not session.get("autenticado"):
        return jsonify({"error": "Sesión expirada. Inicie sesión nuevamente."}), 403

    try:
        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "No se proporcionaron archivos"}), 400

        filepaths = []
        for file in files:
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            filepaths.append(filepath)
            print(f"📁 Guardado archivo laboral: {filename}")

        processor = DataProcessor()
        resultados_totales = processor.procesar_archivos(filepaths)

        nuevos, repetidos, desaparecidos = db_manager.comparar_con_historico(resultados_totales, tipo_analisis="laboral")
        guardados = db_manager.guardar_resultados(nuevos, tipo_analisis="laboral", nombre_archivo=f"{len(files)}_archivos_QNA")

        return jsonify({
            "mensaje": f"Procesamiento de {len(files)} archivo(s) completado",
            "total_resultados": len(resultados_totales),
            "nuevos": len(nuevos),
            "repetidos": len(repetidos),
            "desaparecidos": len(desaparecidos),
            "guardados": guardados
        })

    except Exception as e:
        print(f"❌ Error en /upload: {e}")
        return jsonify({"error": str(e)}), 500


# ===========================================================
# PROCESAMIENTO HORARIOS (multiarchivo)
# ===========================================================
@app.route("/upload_horarios", methods=["POST"])
def upload_horarios():
    if not session.get("autenticado"):
        return jsonify({"error": "Sesión expirada. Inicie sesión nuevamente."}), 403

    try:
        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "No se proporcionaron archivos"}), 400

        filepaths = []
        for file in files:
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            filepaths.append(filepath)
            print(f"📁 Guardado archivo horario: {filename}")

        processor = HorariosProcessor()
        resultados_totales = []
        for filepath in filepaths:
            resultados = processor.procesar_archivo(filepath)
            resultados_totales.extend(resultados)

        nuevos, repetidos, desaparecidos = db_manager.comparar_con_historico(resultados_totales, tipo_analisis="horarios")
        guardados = db_manager.guardar_resultados(nuevos, tipo_analisis="horarios", nombre_archivo=f"{len(files)}_archivos_horarios")

        return jsonify({
            "mensaje": f"Procesamiento de {len(files)} archivo(s) de horarios completado",
            "total_resultados": len(resultados_totales),
            "nuevos": len(nuevos),
            "repetidos": len(repetidos),
            "desaparecidos": len(desaparecidos),
            "guardados": guardados
        })

    except Exception as e:
        print(f"❌ Error en /upload_horarios: {e}")
        return jsonify({"error": str(e)}), 500


# ===========================================================
# RESULTADOS
# ===========================================================
@app.route("/resultados")
def resultados_patrones():
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    pagina = int(request.args.get("page", 1))
    busqueda = request.args.get("search", "").strip() or None
    limite = 20
    resultados, total = db_manager.obtener_resultados_paginados("laboral", busqueda, pagina, limite)
    total_paginas = max(1, ceil(total / limite))
    return render_template("resultados.html", resultados=resultados, busqueda=busqueda or "", pagina_actual=pagina, total_paginas=total_paginas, total=total)


@app.route("/resultados_horarios")
def resultados_horarios():
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    pagina = int(request.args.get("page", 1))
    busqueda = request.args.get("search", "").strip() or None
    limite = 20
    resultados, total = db_manager.obtener_resultados_paginados("horarios", busqueda, pagina, limite)
    total_paginas = max(1, ceil(total / limite))
    return render_template("resultados_horarios.html", resultados=resultados, busqueda=busqueda or "", pagina_actual=pagina, total_paginas=total_paginas, total=total)


# ===========================================================
# EXPORTAR CSV
# ===========================================================
@app.route("/exportar/<tipo>")
def exportar_csv(tipo):
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    resultados, _ = db_manager.obtener_resultados_paginados(tipo, pagina=1, limite=99999)

    def generar():
        yield "RFC,Tipo,Descripción,Entes,Periodo\n"
        for r in resultados:
            yield f"{r.get('rfc','')},{r.get('tipo_patron','')},{r.get('descripcion','')},{'|'.join(r.get('entes',[]))},{r.get('fecha_comun','')}\n"

    return Response(generar(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={tipo}_export.csv"})


# ===========================================================
# EJECUCIÓN
# ===========================================================
if __name__ == "__main__":
    print("🚀 Iniciando SCIL QNA (multiarchivo) en puerto 4050...")
    app.run(host="0.0.0.0", port=4050, debug=True)

