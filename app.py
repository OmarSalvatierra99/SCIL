# ===========================================================
# app.py — SCIL QNA 2025 / Sistema de Auditoría de Servicios Personales
# Versión final con paginación, vistas RFC/ente y exportación
# ===========================================================

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
from werkzeug.utils import secure_filename
from database import DatabaseManager
from data_processor import DataProcessor
from io import BytesIO
from openpyxl import Workbook
from datetime import datetime
from math import ceil
import os, re

# ===========================================================
# CONFIGURACIÓN
# ===========================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SCIL_SECRET", "scil_tlax_2025")
db_manager = DatabaseManager()

# ===========================================================
# FUNCIONES AUXILIARES
# ===========================================================
def formato_moneda(valor):
    try:
        v = float(str(valor).replace(",", "").replace("$", ""))
        return f"${v:,.2f}"
    except Exception:
        return valor or ""

def formato_fecha(f):
    if not f:
        return ""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            d = datetime.strptime(f.strip(), fmt)
            return d.strftime("%d/%m/%Y")
        except Exception:
            continue
    return f

def _sanitize_text(s: str) -> str:
    if not s:
        return ""
    s = s.upper()
    s = re.sub(r"\s+", "", s)
    s = s.replace("-", "").replace("_", "").replace(".", "").replace(",", "")
    s = s.replace("Á","A").replace("É","E").replace("Í","I").replace("Ó","O").replace("Ú","U").replace("Ñ","N")
    return s

def _ente_match(ente_str: str, allowed_tokens):
    if not allowed_tokens:
        return False
    ent = _sanitize_text(ente_str)
    for tok in allowed_tokens:
        t = _sanitize_text(tok)
        if t and t in ent:
            return True
    return False

def _allowed_all(allowed_tokens):
    return any(_sanitize_text(x) in {"ALL", "TODOS"} for x in (allowed_tokens or []))

def _limpiar_nombre_ente(ente: str) -> str:
    if not ente:
        return ""
    partes = re.split(r"[_.]", ente)
    for p in reversed(partes):
        if len(p) >= 3 and not p.lower().endswith(("xlsx", "xls")):
            return p.upper()
    return ente.upper()

def _qna_labels(qnas):
    """Devuelve quincenas legibles y ordenadas: Quincena 1, Quincena 2..."""
    if not isinstance(qnas, dict) or not qnas:
        return ""
    def num_qna(k):
        n = re.sub(r"\D", "", k)
        return int(n) if n.isdigit() else 0
    ordenadas = sorted(qnas.keys(), key=num_qna)
    return ", ".join([f"Quincena {num_qna(k)}" for k in ordenadas if num_qna(k) > 0])

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
# SUBIDA DE ARCHIVOS LABORALES
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
# RESULTADOS LABORALES (GENERAL)
# ===========================================================
@app.route("/resultados")
def resultados_generales():
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    pagina = int(request.args.get("page", 1))
    busqueda = request.args.get("search", "").strip() or None
    limite = 10

    resultados, _ = db_manager.obtener_resultados_paginados("laboral", busqueda, 1, 999999)
    entes_usuario = session.get("entes", [])

    if not _allowed_all(entes_usuario) and entes_usuario:
        resultados = [r for r in resultados if any(_ente_match(e, entes_usuario) for e in (r.get("entes") or []))]

    agrupados, row_keys = {}, set()
    for r in resultados:
        rfc = r.get("rfc")
        if not rfc:
            continue
        if rfc not in agrupados:
            agrupados[rfc] = {"nombre": r.get("nombre", ""), "entes": set(), "registros": []}
        for e in r.get("entes", []):
            agrupados[rfc]["entes"].add(_limpiar_nombre_ente(e))
        for reg in r.get("registros", []):
            e = _limpiar_nombre_ente(reg.get("ente", ""))
            fi, fe = formato_fecha(reg.get("fecha_ingreso", "")), formato_fecha(reg.get("fecha_egreso", ""))
            monto = formato_moneda(reg.get("monto", ""))
            qna_labels = _qna_labels(reg.get("qnas", {}))
            k = (rfc, e, fi, fe, qna_labels)
            if k not in row_keys:
                row_keys.add(k)
                agrupados[rfc]["registros"].append({
                    "ente": e, "puesto": reg.get("puesto", ""),
                    "fecha_ingreso": fi, "fecha_egreso": fe,
                    "monto": monto, "qnas": qna_labels
                })

    todos_rfc = sorted(list(agrupados.keys()))
    total_rfc = len(todos_rfc)
    total_paginas = max(1, ceil(total_rfc / limite))
    pagina = max(1, min(pagina, total_paginas))

    inicio = (pagina - 1) * limite
    fin = inicio + limite
    rfc_pagina = todos_rfc[inicio:fin]
    agrupados_paginados = {r: agrupados[r] for r in rfc_pagina}

    return render_template("resultados.html",
                           resultados_agrupados=agrupados_paginados,
                           pagina_actual=pagina,
                           total_paginas=total_paginas,
                           total=total_rfc,
                           busqueda=busqueda or "")

# ===========================================================
# VISTA POR RFC
# ===========================================================
@app.route("/resultados/rfc/<rfc>")
def resultados_por_rfc(rfc):
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    data = db_manager.obtener_resultados_por_rfc(rfc)
    if not data:
        return render_template("empty.html", mensaje=f"No hay registros para RFC {rfc}")
    for d in data:
        d["fecha_ingreso"] = formato_fecha(d.get("fecha_ingreso"))
        d["fecha_egreso"] = formato_fecha(d.get("fecha_egreso"))
        d["monto"] = formato_moneda(d.get("monto"))
        d["qnas"] = _qna_labels(d.get("qnas", {}))
    return render_template("detalle_rfc.html", rfc=rfc, datos=data)

# ===========================================================
# VISTA POR ENTE
# ===========================================================
@app.route("/resultados/ente/<ente>")
def resultados_por_ente(ente):
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    data = db_manager.obtener_resultados_por_ente(ente)
    if not data:
        return render_template("empty.html", mensaje=f"No hay registros para el ente {ente}")
    for d in data:
        d["fecha_ingreso"] = formato_fecha(d.get("fecha_ingreso"))
        d["fecha_egreso"] = formato_fecha(d.get("fecha_egreso"))
        d["monto"] = formato_moneda(d.get("monto"))
        d["qnas"] = _qna_labels(d.get("qnas", {}))
    return render_template("detalle_ente.html", ente=ente, datos=data)

# ===========================================================
# EXPORTAR RESULTADOS
# ===========================================================
@app.route("/exportar/laboral")
def exportar_laboral():
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    resultados, _ = db_manager.obtener_resultados_paginados("laboral", pagina=1, limite=999999)
    filas, vistos = [], set()

    for r in resultados:
        rfc = (r.get("rfc") or "").upper()
        nombre = r.get("nombre", "") or ""
        entes = sorted(list({_limpiar_nombre_ente(e) for e in (r.get("entes") or []) if e}))
        while len(entes) < 5:
            entes.append("")
        for reg in r.get("registros", []):
            qna_labels = _qna_labels(reg.get("qnas", {}))
            fila = [
                rfc, nombre, reg.get("puesto", ""),
                formato_fecha(reg.get("fecha_ingreso", "")),
                formato_fecha(reg.get("fecha_egreso", "")),
                formato_moneda(reg.get("monto", "")),
                qna_labels, *entes[:5]
            ]
            if tuple(map(str, fila)) not in vistos:
                vistos.add(tuple(map(str, fila)))
                filas.append(fila)

    if not filas:
        return jsonify({"error": "No hay datos para exportar"}), 404

    wb = Workbook()
    ws = wb.active
    ws.title = "Laborales"
    ws.append(["RFC","Nombre","Puesto","Fecha Alta","Fecha Baja","Monto","Cruce Quincenas","Ente 1","Ente 2","Ente 3","Ente 4","Ente 5"])
    for f in filas:
        ws.append(f)
    for col in ws.columns:
        width = min(max(len(str(c.value)) if c.value else 0 for c in col) + 2, 50)
        ws.column_dimensions[col[0].column_letter].width = width
    out = BytesIO()
    wb.save(out)
    out.seek(0)
    filename = f"SCIL_Laborales_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(out, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ===========================================================
# MAIN
# ===========================================================
if __name__ == "__main__":
    print("🚀 Iniciando SCIL QNA 2025...")
    app.run(host="0.0.0.0", port=4050, debug=True)

