# ===========================================================
# app.py — SCIL QNA 2025 / Sistema de Cruce de Información Laboral
# Versión final — Agrupación limpia, deduplicación total, exportación auditada
# ===========================================================

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
from werkzeug.utils import secure_filename
from database import DatabaseManager
from data_processor import DataProcessor
from horarios_processor import HorariosProcessor
import os
from math import ceil
from openpyxl import Workbook
from io import BytesIO
from datetime import datetime

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
            fname = secure_filename(file.filename)
            path = os.path.join(UPLOAD_FOLDER, fname)
            file.save(path)
            filepaths.append(path)
            print(f"📁 Guardado archivo laboral: {fname}")

        processor = DataProcessor()
        resultados_totales = []
        if hasattr(processor, "procesar_archivos"):
            resultados_totales = processor.procesar_archivos(filepaths)
        else:
            for p in filepaths:
                resultados_totales.extend(processor.procesar_archivo(p))

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

        processor = HorariosProcessor()
        resultados_totales = []
        for file in files:
            fname = secure_filename(file.filename)
            path = os.path.join(UPLOAD_FOLDER, fname)
            file.save(path)
            print(f"📁 Procesando horarios: {fname}")
            resultados = processor.procesar_archivo(path)
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
# RESULTADOS LABORALES (agrupados y deduplicados)
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

    agrupados = {}

    for r in resultados:
        rfc = r.get("rfc")
        if not rfc:
            continue
        if rfc not in agrupados:
            agrupados[rfc] = {
                "nombre": r.get("nombre", ""),
                "quincenas": set(),
                "entes": set(),
                "registros": set()
            }

        agrupados[rfc]["quincenas"].add((r.get("fecha_comun", "") or "").strip())
        for e in r.get("entes", []):
            agrupados[rfc]["entes"].add((e or "").strip().upper())

        for reg in r.get("registros", []):
            clave = (
                (reg.get("ente", "") or "").strip().upper(),
                (reg.get("puesto", "") or "").strip().upper(),
                (reg.get("fecha_ingreso", "") or "").strip(),
                (reg.get("fecha_egreso", "") or "").strip()
            )
            agrupados[rfc]["registros"].add(clave)

    # Convertir sets a listas limpias y ordenadas
    for rfc, data in agrupados.items():
        data["quincenas"] = sorted(list({q for q in data["quincenas"] if q}))
        data["entes"] = sorted(list({e for e in data["entes"] if e}))
        data["registros"] = [
            {"ente": e, "puesto": p, "fecha_ingreso": fi, "fecha_egreso": fe}
            for (e, p, fi, fe) in sorted(data["registros"])
        ]

    return render_template(
        "resultados.html",
        resultados_agrupados=agrupados,
        busqueda=busqueda or "",
        pagina_actual=pagina,
        total_paginas=total_paginas,
        total=total
    )


# ===========================================================
# RESULTADOS HORARIOS
# ===========================================================
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
# EXPORTAR EXCEL (Robusto y auditado)
# ===========================================================
@app.route("/exportar/<tipo>")
def exportar_excel(tipo):
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    TIPO_ALIAS = {
        "patron": "laboral", "patrones": "laboral", "laborales": "laboral",
        "laboral": "laboral", "horario": "horarios", "horarios": "horarios"
    }
    tipo_db = TIPO_ALIAS.get(tipo.lower(), tipo.lower())

    resultados, _ = db_manager.obtener_resultados_paginados(tipo_db, pagina=1, limite=999999)
    if not resultados and hasattr(db_manager, "obtener_todos"):
        resultados = db_manager.obtener_todos(tipo_db)
    if not resultados:
        return jsonify({"error": f"No hay datos para exportar del tipo '{tipo_db}'"}), 404

    wb = Workbook()
    ws = wb.active
    ws.title = "Resultados"

    headers = [
        "RFC", "Nombre", "Tipo de Hallazgo", "Descripción",
        "Entes Involucrados", "Quincena", "Ente", "Puesto",
        "Fecha Ingreso", "Fecha Egreso"
    ]
    ws.append(headers)

    vistos = set()
    for r in resultados:
        rfc = r.get("rfc", "").strip().upper()
        nombre = (r.get("nombre", "") or "").strip()
        tipo_patron = (r.get("tipo_patron", "") or "").strip()
        descripcion = (r.get("descripcion", "") or "").strip()
        entes_str = " | ".join(sorted(set(e.strip().upper() for e in r.get("entes", []) if e)))
        quincena = (r.get("fecha_comun", "") or "").strip()

        for reg in (r.get("registros", []) or [{}]):
            clave = (
                rfc, nombre, tipo_patron, descripcion, entes_str, quincena,
                (reg.get("ente", "") or "").strip().upper(),
                (reg.get("puesto", "") or "").strip().upper(),
                (reg.get("fecha_ingreso", "") or "").strip(),
                (reg.get("fecha_egreso", "") or "").strip()
            )
            if clave in vistos:
                continue
            vistos.add(clave)
            ws.append(list(clave))

    for col in ws.columns:
        width = min(max(len(str(c.value)) if c.value else 0 for c in col) + 2, 50)
        ws.column_dimensions[col[0].column_letter].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"Resultados_{tipo_db.upper()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ===========================================================
# EJECUCIÓN
# ===========================================================
if __name__ == "__main__":
    print("🚀 Iniciando SCIL QNA (multiarchivo) en puerto 4050...")
    app.run(host="0.0.0.0", port=4050, debug=True)

