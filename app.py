# ===========================================================
# app.py — SCIL QNA 2025 / Sistema de Auditoría de Servicios Personales
# ===========================================================

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
from werkzeug.utils import secure_filename
from database import DatabaseManager
from data_processor import DataProcessor
from io import BytesIO
from math import ceil
from openpyxl import Workbook
from datetime import datetime
import os, re

# -----------------------------------------------------------
# Configuración general
# -----------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SCIL_SECRET", "scil_tlax_2025")

db_manager = DatabaseManager()

# -----------------------------------------------------------
# Utilidades
# -----------------------------------------------------------
def formato_fecha(fecha):
    if not fecha:
        return ""
    try:
        if isinstance(fecha, datetime):
            return fecha.strftime("%d/%m/%Y")
        return str(fecha)
    except Exception:
        return str(fecha)


def formato_moneda(valor):
    try:
        return "${:,.2f}".format(float(valor))
    except Exception:
        return valor or ""


def _sanitize_text(s):
    return re.sub(r"\s+", "", s.upper()) if s else ""


def _limpiar_nombre_ente(ente):
    if not ente:
        return ""
    partes = re.split(r"[_.]", ente)
    for p in reversed(partes):
        if len(p) >= 3 and not p.lower().endswith(("xlsx", "xls")):
            return p.upper()
    return ente.upper()


def _allowed_all(entes):
    return any(_sanitize_text(x) in {"ALL", "TODOS"} for x in (entes or []))


def _qna_labels(qnas_dict):
    if not qnas_dict:
        return ""
    qnas = list(qnas_dict.keys())
    try:
        ordenadas = sorted(qnas, key=lambda k: int(re.sub(r"\D", "", k)))
    except Exception:
        ordenadas = sorted(qnas)
    if len(ordenadas) == 12:
        return "Activo todo el periodo"
    return ", ".join(
        [f"Quincena {int(re.sub(r'\\D', '', k))}" for k in ordenadas if re.search(r"\d+", k)]
    )

# -----------------------------------------------------------
# Login / Logout / Dashboard
# -----------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        clave = request.form.get("clave")
        datos = db_manager.get_usuario(usuario, clave)
        if datos:
            session.update({
                "autenticado": True,
                "usuario": usuario,
                "nombre": datos["nombre"],
                "entes": datos["entes"],
            })
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Usuario o clave incorrectos")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    return render_template("dashboard.html", nombre=session.get("nombre", ""))

# -----------------------------------------------------------
# Subida de archivos laborales
# -----------------------------------------------------------
def _get_uploaded_buffers(field_name="files"):
    files = request.files.getlist(field_name)
    if not files:
        return [], "No se recibieron archivos"
    buffers = []
    for f in files:
        if not f.filename.strip():
            continue
        data = BytesIO(f.read())
        data.name = secure_filename(f.filename)
        buffers.append(data)
    if not buffers:
        return [], "No se recibieron archivos válidos (.xlsx)"
    return buffers, None


@app.route("/upload_laboral", methods=["POST"])
def upload_laboral():
    if not session.get("autenticado"):
        return jsonify({"error": "No autorizado"}), 403

    buffers, err = _get_uploaded_buffers("files")
    if err:
        return jsonify({"error": err}), 400

    processor = DataProcessor()
    resultados = processor.procesar_archivos(buffers, from_memory=True)

    nuevos, repetidos, _ = db_manager.comparar_con_historico(resultados, "laboral")
    db_manager.guardar_resultados(nuevos, "laboral")

    return jsonify({
        "mensaje": "Archivos procesados correctamente",
        "total_resultados": len(resultados),
        "nuevos": len(nuevos)
    })

# -----------------------------------------------------------
# Reporte por Ente (sin duplicados)
# -----------------------------------------------------------
@app.route("/resultados")
def reporte_por_ente():
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    resultados, _ = db_manager.obtener_resultados_paginados("laboral", pagina=1, limite=999999)
    if not resultados:
        return render_template("resultados.html", reporte_por_ente={})

    entes_usuario = session.get("entes", [])
    if not _allowed_all(entes_usuario) and entes_usuario:
        resultados = [
            r for r in resultados
            if any(e for e in (r.get("entes") or [])
                   if any(_sanitize_text(x) in _sanitize_text(e) for x in entes_usuario))
        ]

    # Agrupar por ente sin duplicar
    reporte = {}
    filas_vistas = set()

    for r in resultados:
        for ente in r.get("entes", []):
            ente_nom = _limpiar_nombre_ente(ente)
            if ente_nom not in reporte:
                reporte[ente_nom] = []

            for reg in r.get("registros", []):
                clave = (r["rfc"], r.get("nombre"), reg.get("puesto"), ente_nom)
                if clave in filas_vistas:
                    continue
                filas_vistas.add(clave)

                reporte[ente_nom].append({
                    "rfc": r["rfc"],
                    "nombre": r.get("nombre", ""),
                    "puesto": reg.get("puesto", ""),
                    "entes_incompatibles": ", ".join(sorted(r.get("entes", []))),
                })

    return render_template("resultados.html", reporte_por_ente=reporte)

# -----------------------------------------------------------
# Detalle por RFC (trabajador)
# -----------------------------------------------------------
@app.route("/resultados/rfc/<rfc>")
def resultados_por_rfc(rfc):
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    if not re.match(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{2,3}$", rfc.upper()):
        return render_template("empty.html", tipo="ente", mensaje=f"'{rfc}' no es un RFC válido")

    info = db_manager.obtener_resultados_por_rfc(rfc.upper())
    if not info:
        return render_template("empty.html", tipo="persona", mensaje=f"No se encontraron registros para {rfc}")

    vistos = set()
    registros_unicos = []
    for reg in info.get("registros", []):
        clave = (reg.get("ente"), reg.get("puesto"), reg.get("fecha_ingreso"))
        if clave in vistos:
            continue
        vistos.add(clave)
        reg["fecha_ingreso"] = formato_fecha(reg.get("fecha_ingreso"))
        reg["fecha_egreso"] = formato_fecha(reg.get("fecha_egreso"))
        reg["monto"] = formato_moneda(reg.get("monto"))
        reg["qnas"] = _qna_labels(reg.get("qnas", {}))
        registros_unicos.append(reg)
    info["registros"] = registros_unicos

    return render_template("detalle_rfc.html", rfc=rfc.upper(), info=info)

# -----------------------------------------------------------
# Exportar a Excel
# -----------------------------------------------------------
@app.route("/exportar/laboral")
def exportar_laboral():
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    resultados, _ = db_manager.obtener_resultados_paginados("laboral", pagina=1, limite=999999)
    filas, vistos = [], set()

    for r in resultados:
        rfc = r.get("rfc", "")
        nombre = r.get("nombre", "")
        entes = sorted(list({_limpiar_nombre_ente(e) for e in (r.get("entes") or []) if e}))
        while len(entes) < 2:
            entes.append("")

        for reg in r.get("registros", []):
            qnas = _qna_labels(reg.get("qnas", {}))
            fila = [
                rfc, nombre, entes[0], entes[1],
                reg.get("puesto", ""), reg.get("fecha_ingreso", ""),
                reg.get("fecha_egreso", ""), reg.get("monto", ""), qnas
            ]
            clave = tuple(map(str, fila))
            if clave in vistos:
                continue
            vistos.add(clave)
            filas.append(fila)

    if not filas:
        return jsonify({"error": "No hay datos para exportar"}), 404

    wb = Workbook()
    ws = wb.active
    ws.title = "Laborales"
    ws.append(["RFC", "Nombre", "Ente 1", "Ente 2", "Puesto", "Fecha Alta", "Fecha Baja", "Monto", "Cruce Quincenas"])
    for f in filas:
        ws.append(f)

    for col in ws.columns:
        width = min(max(len(str(c.value)) if c.value else 0 for c in col) + 2, 50)
        ws.column_dimensions[col[0].column_letter].width = width

    out = BytesIO()
    wb.save(out)
    out.seek(0)
    filename = f"SCIL_Laborales_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        out,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# -----------------------------------------------------------
# Main
# -----------------------------------------------------------
if __name__ == "__main__":
    print("🚀 Iniciando SCIL QNA 2025...")
    app.run(host="0.0.0.0", port=4050, debug=True)

