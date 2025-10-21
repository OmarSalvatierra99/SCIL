# ===========================================================
# app.py — SASP / Sistema de Auditoría de Servicios Personales
# Versión 2025: estructura base.html + vistas unificadas
# ===========================================================

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
from werkzeug.utils import secure_filename
from database import DatabaseManager
from data_processor import DataProcessor
from horarios_processor import HorariosProcessor
import os, re, hashlib
from math import ceil
from openpyxl import Workbook
from io import BytesIO
from datetime import datetime

# ---------------------------
# Configuración
# ---------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SASP_SECRET", "sasp_tlax_2025")
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db_manager = DatabaseManager()

# ---------------------------
# Utilidades
# ---------------------------
def _sanitize_text(s: str) -> str:
    if not s:
        return ""
    s = s.upper()
    s = re.sub(r"\s+", "", s)
    s = s.replace("-", "").replace("_", "")
    s = s.replace(".", "").replace(",", "")
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

def _row_key(rfc, ente, puesto, fi, fe):
    base = f"{(rfc or '').upper()}|{(ente or '').upper()}|{(puesto or '').upper()}|{fi or ''}|{fe or ''}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def _limpiar_nombre_ente(ente: str) -> str:
    if not ente:
        return ""
    partes = re.split(r"[_.]", ente)
    for p in reversed(partes):
        if len(p) >= 3 and not p.lower().endswith(("xlsx","xls")):
            return p.upper()
    return ente.upper()

def _ensure_solvencias_table():
    conn = db_manager.get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS solvencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT UNIQUE,
            rfc TEXT,
            ente TEXT,
            puesto TEXT,
            fecha_ingreso TEXT,
            fecha_egreso TEXT,
            monto TEXT,
            estado INTEGER DEFAULT 0,
            usuario TEXT,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

def _get_solvencia_map(keys):
    if not keys:
        return {}
    conn = db_manager.get_connection()
    cur = conn.cursor()
    q = ",".join(["?"] * len(keys))
    cur.execute(f"SELECT key_hash, estado FROM solvencias WHERE key_hash IN ({q})", tuple(keys))
    return {row["key_hash"]: row["estado"] for row in cur.fetchall()}

_ensure_solvencias_table()

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
    return render_template("dashboard.html", nombre=session.get("nombre",""))

# ===========================================================
# RESULTADOS LABORALES
# ===========================================================
@app.route("/resultados")
def resultados_patrones():
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    pagina = int(request.args.get("page", 1))
    busqueda = request.args.get("search", "").strip() or None
    limite = 20

    resultados, total = db_manager.obtener_resultados_paginados("laboral", busqueda, pagina, limite)
    entes_usuario = session.get("entes", [])

    if not _allowed_all(entes_usuario) and entes_usuario:
        resultados = [r for r in resultados if any(_ente_match(e, entes_usuario) for e in (r.get("entes") or []))]

    agrupados, row_keys = {}, set()
    for r in resultados:
        rfc = r.get("rfc")
        if not rfc:
            continue
        if rfc not in agrupados:
            agrupados[rfc] = {"nombre": r.get("nombre", ""), "quincenas": set(), "entes": set(), "registros": []}
        if r.get("fecha_comun"):
            agrupados[rfc]["quincenas"].add(r["fecha_comun"])
        for e in r.get("entes", []) or []:
            agrupados[rfc]["entes"].add(_limpiar_nombre_ente(e))
        for reg in r.get("registros", []) or []:
            e = _limpiar_nombre_ente(reg.get("ente",""))
            p = (reg.get("puesto","") or "").strip()
            fi, fe = (reg.get("fecha_ingreso","") or "").strip(), (reg.get("fecha_egreso","") or "").strip()
            monto = str(reg.get("monto","") or "")
            k = (rfc, e.upper(), p.upper(), fi, fe)
            if k not in row_keys:
                row_keys.add(k)
                agrupados[rfc]["registros"].append({
                    "ente": e, "puesto": p,
                    "fecha_ingreso": fi, "fecha_egreso": fe, "monto": monto
                })

    all_keys = [_row_key(rfc, reg["ente"], reg["puesto"], reg["fecha_ingreso"], reg["fecha_egreso"])
                for rfc, info in agrupados.items() for reg in info["registros"]]
    solv_map = _get_solvencia_map(all_keys)

    for rfc, info in agrupados.items():
        info["quincenas"] = sorted(info["quincenas"])
        info["entes"] = sorted(info["entes"])
        for reg in info["registros"]:
            k = _row_key(rfc, reg["ente"], reg["puesto"], reg["fecha_ingreso"], reg["fecha_egreso"])
            reg["solventado"] = 1 if solv_map.get(k, 0) == 1 else 0
            reg["key_hash"] = k

    total_paginas = max(1, ceil(total / limite))
    return render_template("resultados.html",
                           resultados_agrupados=agrupados,
                           busqueda=busqueda or "",
                           pagina_actual=pagina,
                           total_paginas=total_paginas,
                           total=total)

# ===========================================================
# RESULTADOS HORARIOS
# ===========================================================
@app.route("/resultados_horarios")
def resultados_horarios():
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    resultados, total = db_manager.obtener_resultados_paginados("horarios", pagina=1, limite=100)
    return render_template("resultados_horarios.html",
                           resultados=resultados,
                           busqueda=request.args.get("search", ""),
                           pagina_actual=1,
                           total_paginas=1,
                           total=total)

# ===========================================================
# SUBIDA DE ARCHIVOS
# ===========================================================
def _save_uploads(field_name="files"):
    files = request.files.getlist(field_name)
    if not files:
        return [], "No se recibieron archivos"
    paths = []
    for f in files:
        fname = secure_filename(f.filename)
        path = os.path.join(UPLOAD_FOLDER, fname)
        f.save(path)
        paths.append(path)
    return paths, None

@app.route("/upload", methods=["POST"])
def upload_laboral():
    if not session.get("autenticado"):
        return jsonify({"error": "No autorizado"}), 403
    paths, err = _save_uploads("files")
    if err:
        return jsonify({"error": err}), 400
    processor = DataProcessor()
    resultados = processor.procesar_archivos(paths)
    nuevos, repetidos, _ = db_manager.comparar_con_historico(resultados, "laboral")
    db_manager.guardar_resultados(nuevos, "laboral", nombre_archivo=os.path.basename(paths[0]) if paths else None)
    return jsonify({"mensaje": "Archivos procesados correctamente",
                    "total_resultados": len(resultados), "nuevos": len(nuevos)})

@app.route("/upload_horarios", methods=["POST"])
def upload_horarios():
    if not session.get("autenticado"):
        return jsonify({"error": "No autorizado"}), 403
    paths, err = _save_uploads("files")
    if err:
        return jsonify({"error": err}), 400
    try:
        hp = HorariosProcessor()
        resultados = hp.procesar_archivos(paths)
    except Exception as e:
        return jsonify({"error": f"Error procesando horarios: {e}"}), 500
    nuevos, repetidos, _ = db_manager.comparar_con_historico(resultados, "horarios")
    db_manager.guardar_resultados(nuevos, "horarios", nombre_archivo=os.path.basename(paths[0]) if paths else None)
    return jsonify({"mensaje": "Horarios procesados correctamente",
                    "total_resultados": len(resultados), "nuevos": len(nuevos)})

# ===========================================================
# EXPORTAR LABORAL
# ===========================================================
@app.route("/exportar/laboral")
def exportar_laboral():
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    resultados, _ = db_manager.obtener_resultados_paginados("laboral", pagina=1, limite=999999)
    filas = []
    for r in resultados:
        rfc = (r.get("rfc") or "").upper()
        nombre = r.get("nombre", "")
        quincena = r.get("fecha_comun", "")
        for reg in r.get("registros", []):
            filas.append([
                rfc, nombre, quincena,
                reg.get("ente",""), reg.get("puesto",""),
                reg.get("fecha_ingreso",""), reg.get("fecha_egreso",""),
                reg.get("monto","")
            ])
    wb = Workbook(); ws = wb.active; ws.title = "Laborales"
    ws.append(["RFC","Nombre","Quincena","Ente","Puesto","Fecha Alta","Fecha Baja","Monto"])
    for f in filas: ws.append(f)
    out = BytesIO(); wb.save(out); out.seek(0)
    filename = f"SASP_Laborales_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(out, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ===========================================================
# MAIN
# ===========================================================
if __name__ == "__main__":
    print("🚀 Iniciando SASP 2025...")
    app.run(host="0.0.0.0", port=4050, debug=True)

