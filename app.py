# ===========================================================
# app.py — SCIL / Sistema de Cruce de Información Laboral
# Autenticación simple con clave maestra "scil2024"
# Comparación histórica y dashboard web
# Puerto configurado: 4050
# ===========================================================

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.utils import secure_filename
from database import DatabaseManager
from data_processor import DataProcessor
from horarios_processor import HorariosProcessor
import os
from math import ceil

# -----------------------------------------------------------
# Configuración general
# -----------------------------------------------------------
app = Flask(__name__)
app.secret_key = "scil_tlax_2025"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db_manager = DatabaseManager()

# Clave maestra única
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
# DASHBOARD PRINCIPAL
# ===========================================================
@app.route("/dashboard")
def dashboard():
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    return render_template("dashboard.html")


# ===========================================================
# PROCESAMIENTO LABORAL
# ===========================================================
@app.route("/upload", methods=["POST"])
def upload_laboral():
    if not session.get("autenticado"):
        return jsonify({"error": "Sesión expirada. Inicie sesión nuevamente."}), 403

    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No se proporcionó archivo"})

        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        print(f"📁 Procesando {filename}")
        print("📊 Iniciando procesamiento laboral...")

        processor = DataProcessor()
        resultados = processor.procesar_archivo(filepath)

        nuevos, repetidos, desaparecidos = db_manager.comparar_con_historico(resultados, tipo_analisis="laboral")
        guardados = db_manager.guardar_resultados(nuevos, tipo_analisis="laboral", nombre_archivo=filename)

        return jsonify({
            "mensaje": "Procesamiento laboral completado",
            "total_resultados": len(resultados),
            "nuevos": len(nuevos),
            "repetidos": len(repetidos),
            "desaparecidos": len(desaparecidos),
            "guardados": guardados
        })

    except Exception as e:
        print(f"❌ Error en /upload: {e}")
        return jsonify({"error": str(e)}), 500


# ===========================================================
# PROCESAMIENTO DE HORARIOS
# ===========================================================
@app.route("/upload_horarios", methods=["POST"])
def upload_horarios():
    if not session.get("autenticado"):
        return jsonify({"error": "Sesión expirada. Inicie sesión nuevamente."}), 403

    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No se proporcionó archivo"})

        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        print(f"📁 Procesando horarios: {filename}")
        print("⏰ Iniciando análisis de cruces de horarios...")

        processor = HorariosProcessor()
        resultados = processor.procesar_archivo(filepath)

        nuevos, repetidos, desaparecidos = db_manager.comparar_con_historico(resultados, tipo_analisis="horarios")
        guardados = db_manager.guardar_resultados(nuevos, tipo_analisis="horarios", nombre_archivo=filename)

        return jsonify({
            "mensaje": "Procesamiento de horarios completado",
            "total_resultados": len(resultados),
            "nuevos": len(nuevos),
            "repetidos": len(repetidos),
            "desaparecidos": len(desaparecidos),
            "guardados": guardados
        })

    except Exception as e:
        print(f"❌ Error en /upload_horarios: {e}")
        return jsonify({"error": str(e)}), 500


# ===========================================================
# RESULTADOS LABORALES (paginados y filtrables)
# ===========================================================
@app.route("/resultados")
def resultados_patrones():
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    pagina = int(request.args.get("page", 1))
    busqueda = request.args.get("search", "").strip() or None
    limite = 20

    resultados, total = db_manager.obtener_resultados_paginados(
        tipo_analisis="laboral",
        busqueda=busqueda,
        pagina=pagina,
        limite=limite
    )

    total_paginas = max(1, ceil(total / limite))
    return render_template(
        "resultados.html",
        resultados=resultados,
        busqueda=busqueda or "",
        pagina_actual=pagina,
        total_paginas=total_paginas,
        total=total
    )


# ===========================================================
# RESULTADOS DE HORARIOS (paginados y filtrables)
# ===========================================================
@app.route("/resultados_horarios")
def resultados_horarios():
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    pagina = int(request.args.get("page", 1))
    busqueda = request.args.get("search", "").strip() or None
    limite = 20

    resultados, total = db_manager.obtener_resultados_paginados(
        tipo_analisis="horarios",
        busqueda=busqueda,
        pagina=pagina,
        limite=limite
    )

    total_paginas = max(1, ceil(total / limite))
    return render_template(
        "resultados_horarios.html",
        resultados=resultados,
        busqueda=busqueda or "",
        pagina_actual=pagina,
        total_paginas=total_paginas,
        total=total
    )


# ===========================================================
# EXPORTACIÓN CSV
# ===========================================================
@app.route("/exportar/<tipo>")
def exportar_csv(tipo):
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    import csv
    from flask import Response

    resultados, _ = db_manager.obtener_resultados_paginados(
        tipo_analisis=tipo,
        pagina=1,
        limite=99999
    )

    def generar():
        yield "RFC,Tipo,Descripción,Entes,Periodo\n"
        for r in resultados:
            yield f"{r.get('rfc','')},{r.get('tipo_patron','')},{r.get('descripcion','')},{'|'.join(r.get('entes',[]))},{r.get('fecha_comun','')}\n"

    return Response(
        generar(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={tipo}_export.csv"}
    )


# ===========================================================
# INICIO DEL SERVIDOR
# ===========================================================
if __name__ == "__main__":
    print("🚀 Iniciando SCIL (puerto 4050)...")
    app.run(host="0.0.0.0", port=4050, debug=True)

