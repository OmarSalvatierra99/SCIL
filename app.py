# ===========================================================
# app.py — SCIL QNA 2025 / Sistema de Cruce de Información Laboral
# Multiusuario, control por entes, deduplicación, solvencias, export sólo no-solventadas
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
# Config
# ---------------------------
app = Flask(__name__)
app.secret_key = "scil_tlax_2025"
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
    """Coincidencia por subcadenas: si cualquiera de los tokens aparece dentro del nombre del ente."""
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
            estado INTEGER DEFAULT 0,  -- 0 = No solventado, 1 = Solventado
            usuario TEXT,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_solv_key ON solvencias(key_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_solv_rfc ON solvencias(rfc)")
    conn.commit()

def _get_solvencia_map(keys):
    """Devuelve dict key_hash -> estado (0/1)."""
    if not keys:
        return {}
    conn = db_manager.get_connection()
    cur = conn.cursor()
    q = ",".join(["?"] * len(keys))
    cur.execute(f"SELECT key_hash, estado FROM solvencias WHERE key_hash IN ({q})", tuple(keys))
    return {row["key_hash"]: row["estado"] for row in cur.fetchall()}

_ensure_solvencias_table()

# ===========================================================
# LOGIN MULTIUSUARIO
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
            session["entes"] = datos["entes"]  # lista de tokens
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Usuario o clave incorrectos")
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
    return render_template("dashboard.html", nombre=session.get("nombre",""))

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
# RESULTADOS LABORALES (con filtro de entes por subcadenas)
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
        filtrados = []
        for r in resultados:
            entes_r = r.get("entes", []) or []
            if any(_ente_match(e, entes_usuario) for e in entes_r):
                filtrados.append(r)
        resultados = filtrados

    # Agrupar por RFC y deduplicar registros
    agrupados = {}
    row_keys = set()
    for r in resultados:
        rfc = r.get("rfc")
        if not rfc:
            continue
        if rfc not in agrupados:
            agrupados[rfc] = {
                "nombre": r.get("nombre", ""),
                "quincenas": set(),
                "entes": set(),
                "registros": []  # dicts
            }
        q = (r.get("fecha_comun", "") or "").strip()
        if q:
            agrupados[rfc]["quincenas"].add(q)
        for e in r.get("entes", []) or []:
            if e:
                agrupados[rfc]["entes"].add(e)

        for reg in r.get("registros", []) or []:
            e = (reg.get("ente","") or "").strip()
            p = (reg.get("puesto","") or "").strip()
            fi = (reg.get("fecha_ingreso","") or "").strip()
            fe = (reg.get("fecha_egreso","") or "").strip()
            k = (rfc, e.upper(), p.upper(), fi, fe)
            if k in row_keys:
                continue
            row_keys.add(k)
            agrupados[rfc]["registros"].append({
                "ente": e, "puesto": p, "fecha_ingreso": fi, "fecha_egreso": fe
            })

    # Cargar solvencias para marcar estado
    all_keys = []
    for rfc, info in agrupados.items():
        for reg in info["registros"]:
            all_keys.append(_row_key(rfc, reg["ente"], reg["puesto"], reg["fecha_ingreso"], reg["fecha_egreso"]))
    solv_map = _get_solvencia_map(all_keys)

    for rfc, info in agrupados.items():
        info["quincenas"] = sorted(list(info["quincenas"]))
        info["entes"] = sorted(list(info["entes"]))
        for reg in info["registros"]:
            k = _row_key(rfc, reg["ente"], reg["puesto"], reg["fecha_ingreso"], reg["fecha_egreso"])
            reg["solventado"] = 1 if solv_map.get(k, 0) == 1 else 0
            reg["key_hash"] = k  # útil para el front

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
# RESULTADOS HORARIOS (ruta básica para evitar BuildError)
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
    return render_template(
        "resultados_horarios.html",
        resultados=resultados,
        busqueda=busqueda or "",
        pagina_actual=pagina,
        total_paginas=total_paginas,
        total=total
    )

# ===========================================================
# API: Toggle Solvencia (sólo entes del usuario)
# ===========================================================
@app.route("/api/solvencia/toggle", methods=["POST"])
def api_toggle_solvencia():
    if not session.get("autenticado"):
        return jsonify({"ok": False, "error": "Sesión expirada"}), 403

    data = request.get_json(force=True) or {}
    rfc = (data.get("rfc") or "").strip().upper()
    ente = (data.get("ente") or "").strip()
    puesto = (data.get("puesto") or "").strip()
    fi = (data.get("fecha_ingreso") or "").strip()
    fe = (data.get("fecha_egreso") or "").strip()
    estado = 1 if str(data.get("estado","0")) in {"1","true","True"} else 0

    # Verificación de permisos por ente
    entes_usuario = session.get("entes", [])
    if not _allowed_all(entes_usuario):
        if not _ente_match(ente, entes_usuario):
            return jsonify({"ok": False, "error": "No autorizado para marcar este ente"}), 403

    key = _row_key(rfc, ente, puesto, fi, fe)
    conn = db_manager.get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO solvencias (key_hash, rfc, ente, puesto, fecha_ingreso, fecha_egreso, estado, usuario)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(key_hash) DO UPDATE SET estado=excluded.estado, usuario=excluded.usuario, ts=CURRENT_TIMESTAMP
    """, (key, rfc, ente, puesto, fi, fe, estado, session.get("usuario","")))
    conn.commit()
    return jsonify({"ok": True, "key": key, "estado": estado})

# ===========================================================
# EXPORTAR EXCEL — Sólo NO solventadas
# ===========================================================
@app.route("/exportar/<tipo>")
def exportar_excel(tipo):
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    alias = {
        "patron": "laboral", "patrones": "laboral", "laborales": "laboral",
        "laboral": "laboral", "horario": "horarios", "horarios": "horarios"
    }
    tipo_db = alias.get(tipo.lower(), tipo.lower())

    resultados, _ = db_manager.obtener_resultados_paginados(tipo_db, pagina=1, limite=999999)

    # Filtro por entes del usuario (subcadenas)
    entes_usuario = session.get("entes", [])
    if tipo_db == "laboral" and not _allowed_all(entes_usuario) and entes_usuario:
        filtrados = []
        for r in resultados:
            entes_r = r.get("entes", []) or []
            if any(_ente_match(e, entes_usuario) for e in entes_r):
                filtrados.append(r)
        resultados = filtrados

    if tipo_db == "laboral":
        # Sólo no solventadas
        filas = []
        vistos = set()
        all_keys = []

        # Preparar mapa de solvencias
        temp_keys = []
        temp_rows = []
        for r in resultados:
            rfc = (r.get("rfc","") or "").upper()
            nombre = (r.get("nombre","") or "")
            tipo_patron = (r.get("tipo_patron","") or "")
            descripcion = (r.get("descripcion","") or "")
            quincena = (r.get("fecha_comun","") or "")
            entes_str = " | ".join(sorted(set([e for e in (r.get("entes") or []) if e])))

            regs = r.get("registros", []) or [{}]
            for reg in regs:
                ente = reg.get("ente","")
                puesto = reg.get("puesto","")
                fi = reg.get("fecha_ingreso","")
                fe = reg.get("fecha_egreso","")
                k = _row_key(rfc, ente, puesto, fi, fe)
                temp_keys.append(k)
                temp_rows.append((k, [rfc, nombre, tipo_patron, descripcion, entes_str, quincena, ente, puesto, fi, fe]))

        solv_map = _get_solvencia_map(temp_keys)

        for k, row in temp_rows:
            if solv_map.get(k, 0) == 1:
                continue  # solventada -> NO se exporta
            t = tuple(row)
            if t in vistos:
                continue
            vistos.add(t)
            filas.append(row)

        if not filas:
            return jsonify({"error": "No hay no-solventadas para exportar"}), 404

        wb = Workbook()
        ws = wb.active
        ws.title = "No Solventadas"
        ws.append(["RFC","Nombre","Tipo de Hallazgo","Descripción","Entes Involucrados","Quincena","Ente","Puesto","Fecha Ingreso","Fecha Egreso"])
        for f in filas:
            ws.append(f)
        for col in ws.columns:
            width = min(max(len(str(c.value)) if c.value else 0 for c in col) + 2, 50)
            ws.column_dimensions[col[0].column_letter].width = width
        out = BytesIO()
        wb.save(out)
        out.seek(0)
        filename = f"NoSolventadas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(out, as_attachment=True, download_name=filename,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    else:
        # Export básico para horarios
        if not resultados:
            return jsonify({"error": f"No hay datos para exportar del tipo '{tipo_db}'"}), 404
        wb = Workbook()
        ws = wb.active
        ws.title = "Resultados Horarios"
        ws.append(["RFC","Nombre","Tipo","Descripción","Día","Ente/Plantel","Entrada","Salida","Fecha Ingreso","Fecha Egreso"])
        vistos = set()
        for r in resultados:
            base = [r.get("rfc",""), r.get("nombre",""), r.get("tipo_patron",""), r.get("descripcion",""), r.get("fecha_comun","")]
            regs = r.get("registros", []) or [{}]
            for reg in regs:
                row = base + [
                    reg.get("ente",""),
                    reg.get("hora_entrada","") or reg.get("puesto",""),
                    reg.get("hora_salida","") or "",
                    reg.get("fecha_ingreso",""),
                    reg.get("fecha_egreso","")
                ]
                t = tuple(row)
                if t in vistos: 
                    continue
                vistos.add(t)
                ws.append(row)
        for col in ws.columns:
            width = min(max(len(str(c.value)) if c.value else 0 for c in col) + 2, 50)
            ws.column_dimensions[col[0].column_letter].width = width
        out = BytesIO()
        wb.save(out)
        out.seek(0)
        filename = f"Resultados_HORARIOS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(out, as_attachment=True, download_name=filename,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ===========================================================
# EJECUCIÓN
# ===========================================================
if __name__ == "__main__":
    print("🚀 Iniciando SCIL QNA (multiusuario, control por entes, solvencias) en puerto 4050...")
    app.run(host="0.0.0.0", port=4050, debug=True)

