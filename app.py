# ===========================================================
# app.py — SCIL QNA 2025 / Sistema de Auditoría de Servicios Personales
# Versión optimizada — procesamiento en memoria
# ===========================================================

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
from werkzeug.utils import secure_filename
from database import DatabaseManager
from data_processor import DataProcessor
from io import BytesIO
from openpyxl import Workbook
from datetime import datetime
from math import ceil
import os, re, hashlib

# ===========================================================
# CONFIGURACIÓN
# ===========================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SCIL_SECRET", "scil_tlax_2025")

db_manager = DatabaseManager()

# ===========================================================
# UTILIDADES
# ===========================================================
def _sanitize_text(s: str) -> str:
    if not s:
        return ""
    s = s.upper()
    s = re.sub(r"[\s._-]+", "", s)
    s = s.replace("Á","A").replace("É","E").replace("Í","I").replace("Ó","O").replace("Ú","U").replace("Ñ","N")
    return s

def _ente_match(ente_str: str, allowed_tokens):
    """Determina si un ente pertenece a la lista de entes autorizados."""
    if not allowed_tokens:
        return False
    ent = _sanitize_text(ente_str)
    for tok in allowed_tokens:
        if _sanitize_text(tok) in ent:
            return True
    return False

def _allowed_all(allowed_tokens):
    """Detecta si el usuario tiene acceso a todos los entes."""
    return any(_sanitize_text(x) in {"ALL", "TODOS", "*"} for x in (allowed_tokens or []))

def _limpiar_nombre_ente(ente: str) -> str:
    if not ente:
        return ""
    partes = re.split(r"[_.]", ente)
    for p in reversed(partes):
        if len(p) >= 3 and not p.lower().endswith(("xlsx","xls")):
            return p.upper()
    return ente.upper()

# ===========================================================
# LOGIN / LOGOUT / DASHBOARD
# ===========================================================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        clave = request.form.get("clave")
        datos = db_manager.get_usuario(usuario, clave)

        if datos:
            session["autenticado"] = True
            session["usuario"] = usuario
            session["nombre"] = datos["nombre"]
            session["entes"] = datos["entes"]
            return redirect(url_for("dashboard"))
        else:
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

# ===========================================================
# SUBIDA DE ARCHIVOS LABORALES (EN MEMORIA)
# ===========================================================
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

# ===========================================================
# RESULTADOS LABORALES
# ===========================================================
@app.route("/resultados")
def resultados_generales():
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    pagina = int(request.args.get("page", 1))
    busqueda = request.args.get("search", "").strip() or None
    limite = 25

    resultados, total = db_manager.obtener_resultados_paginados("laboral", busqueda, pagina, limite)
    entes_usuario = session.get("entes", [])

    agrupados = {}
    for r in resultados:
        rfc = r.get("rfc")
        if not rfc:
            continue
        if rfc not in agrupados:
            agrupados[rfc] = {"nombre": r.get("nombre", ""), "entes": set(), "registros": []}

        for e in r.get("entes", []):
            agrupados[rfc]["entes"].add(e)

        for reg in r.get("registros", []):
            agrupados[rfc]["registros"].append(reg)

    # Filtra por entes del usuario si aplica
    if entes_usuario and not _allowed_all(entes_usuario):
        agrupados = {
            rfc: data for rfc, data in agrupados.items()
            if any(_ente_match(e, entes_usuario) for e in data["entes"])
        }

    # Ordena los resultados por prioridad (ente autorizado del usuario)
    def prioridad_ente(ente):
        if not entes_usuario:
            return 999
        for i, e in enumerate(entes_usuario):
            if _sanitize_text(e) in _sanitize_text(ente):
                return i
        return 999

    for rfc, data in agrupados.items():
        data["entes"] = sorted(data["entes"], key=prioridad_ente)

    total_paginas = max(1, ceil(total / limite))
    return render_template(
        "resultados.html",
        resultados_agrupados=agrupados,
        busqueda=busqueda or "",
        pagina_actual=pagina,
        total_paginas=total_paginas,
        total=total
    )

# ===========================================================
# EXPORTAR RESULTADOS A EXCEL (completo)
# ===========================================================
@app.route("/exportar/laboral")
def exportar_laboral():
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    resultados, _ = db_manager.obtener_resultados_paginados("laboral", pagina=1, limite=999999)
    entes_usuario = session.get("entes", [])

    filas, vistos = [], set()
    for r in resultados:
        if not isinstance(r, dict):
            continue
        rfc = (r.get("rfc") or "").upper()
        nombre = r.get("nombre", "") or ""
        entes = sorted(list({e for e in (r.get("entes") or []) if e}), key=lambda e: e)

        # Filtrar por permisos de usuario
        if entes_usuario and not _allowed_all(entes_usuario):
            if not any(_ente_match(e, entes_usuario) for e in entes):
                continue

        for reg in r.get("registros", []):
            fila = [
                rfc,
                nombre,
                reg.get("ente", ""),
                reg.get("puesto", ""),
                reg.get("fecha_ingreso", ""),
                reg.get("fecha_egreso", ""),
                reg.get("monto", ""),
                ", ".join(reg.get("qnas", {}).keys()) if isinstance(reg.get("qnas"), dict) else ""
            ]
            if tuple(fila) not in vistos:
                vistos.add(tuple(fila))
                filas.append(fila)

    if not filas:
        return jsonify({"error": "No hay datos para exportar"}), 404

    wb = Workbook()
    ws = wb.active
    ws.title = "Laborales"
    ws.append(["RFC", "Nombre", "Ente", "Puesto", "Fecha Alta", "Fecha Baja", "Monto", "Quincenas"])

    for f in filas:
        ws.append(f)

    # Ajustar ancho de columnas
    for col in ws.columns:
        width = min(max(len(str(c.value)) if c.value else 0 for c in col) + 2, 50)
        ws.column_dimensions[col[0].column_letter].width = width

    out = BytesIO()
    wb.save(out)
    out.seek(0)

    filename = f"SASP_Laborales_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        out,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ===========================================================
# RESULTADOS POR PERSONA (RFC)
# ===========================================================
@app.route("/resultados/rfc/<rfc>")
def resultados_por_rfc(rfc):
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    info = db_manager.obtener_resultados_por_rfc(rfc)
    if not info:
        return render_template("empty.html", mensaje="No se encontró información del trabajador")

    # Filtra según permisos del usuario
    entes_usuario = session.get("entes", [])
    if entes_usuario and not _allowed_all(entes_usuario):
        info["registros"] = [
            r for r in info["registros"]
            if _ente_match(r.get("ente", ""), entes_usuario)
        ]
        info["entes"] = [
            e for e in info["entes"] if _ente_match(e, entes_usuario)
        ]

    # Ordenar por prioridad de ente del usuario
    def prioridad_ente(ente):
        if not entes_usuario:
            return 999
        for i, e in enumerate(entes_usuario):
            if _sanitize_text(e) in _sanitize_text(ente):
                return i
        return 999

    info["entes"] = sorted(info["entes"], key=prioridad_ente)
    return render_template("resultados_personal.html", rfc=rfc, info=info)


# ===========================================================
# RESULTADOS POR ENTE
# ===========================================================
@app.route("/resultados/ente/<ente>")
def resultados_por_ente(ente):
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    resultados_agrupados = db_manager.obtener_resultados_por_ente(ente)
    if not resultados_agrupados:
        return render_template("empty.html", mensaje=f"No se encontraron registros del ente {ente}")

    entes_usuario = session.get("entes", [])
    if entes_usuario and not _allowed_all(entes_usuario):
        # Mostrar solo si el ente está autorizado
        if not any(_ente_match(ente, entes_usuario) for ente_aut in entes_usuario):
            return render_template("empty.html", mensaje="No autorizado para ver este ente")

    return render_template("resultados_ente.html", ente=ente, resultados_agrupados=resultados_agrupados)


# ===========================================================
# MAIN
# ===========================================================
if __name__ == "__main__":
    print("🚀 Iniciando SCIL QNA 2025...")
    app.run(host="0.0.0.0", port=4050, debug=True)

