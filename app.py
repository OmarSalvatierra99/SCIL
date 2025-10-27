# ===========================================================
# app.py — SASP 2025
# Sistema de Auditoría de Servicios Personales
# Órgano de Fiscalización Superior del Estado de Tlaxcala
# ===========================================================

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, send_file
)
import os
import pandas as pd
from io import BytesIO
from functools import lru_cache
from database import DatabaseManager

# -----------------------------------------------------------
# Configuración
# -----------------------------------------------------------
app = Flask(__name__)
app.secret_key = "ofs_sasp_2025"
db_manager = DatabaseManager("scil.db")

# -----------------------------------------------------------
# Middleware
# -----------------------------------------------------------
@app.before_request
def verificar_autenticacion():
    libre = {"login", "static"}
    if request.endpoint not in libre and not session.get("autenticado"):
        if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Sesión expirada o no autorizada"}), 403
        return redirect(url_for("login"))

# -----------------------------------------------------------
# Utilidades
# -----------------------------------------------------------
def _sanitize_text(s):
    return str(s or "").strip().upper()

def _allowed_all(entes_usuario):
    return any(_sanitize_text(e) == "TODOS" for e in entes_usuario)

def _estatus_label(v):
    v = (v or "").strip().lower()
    if not v:
        return "Sin valoración"
    if "no" in v:
        return "No Solventado"
    if "solvent" in v:
        return "Solventado"
    return "Sin valoración"

@lru_cache(maxsize=1)
def _entes_cache():
    conn = db_manager._connect()
    cur = conn.cursor()
    cur.execute("SELECT clave, siglas, nombre FROM entes")
    cache = {}
    for row in cur.fetchall():
        clave = (row["clave"] or "").strip().upper()
        cache[clave] = {
            "siglas": (row["siglas"] or "").strip().upper(),
            "nombre": (row["nombre"] or "").strip().upper()
        }
    conn.close()
    return cache

def _ente_match(ente_usuario, clave_lista):
    euser = _sanitize_text(ente_usuario)
    for k, data in _entes_cache().items():
        if euser in {k, data["siglas"], data["nombre"]}:
            for c in clave_lista:
                if _sanitize_text(c) in {k, data["siglas"], data["nombre"]}:
                    return True
    return False

def _ente_sigla(clave_o_nombre):
    if not clave_o_nombre:
        return ""
    s = _sanitize_text(clave_o_nombre)
    for k, data in _entes_cache().items():
        if s in {k, data["siglas"], data["nombre"]}:
            return data["siglas"] or data["nombre"] or s
    return s

# -----------------------------------------------------------
# LOGIN
# -----------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("clave", "").strip()
        user = db_manager.get_usuario(usuario, clave)
        if not user:
            return render_template("login.html", error="Credenciales inválidas")

        session["usuario"] = user["usuario"]
        session["nombre"] = user["nombre"]
        entes_str = user["entes"]
        if isinstance(entes_str, str):
            entes_list = [e.strip().upper() for e in entes_str.split(",") if e.strip()]
        elif isinstance(entes_str, list):
            entes_list = [str(e).strip().upper() for e in entes_str]
        else:
            entes_list = []

        if user["usuario"].lower() in ["odilia", "victor"]:
            session["entes"] = ["TODOS"]
        else:
            session["entes"] = entes_list
        session["autenticado"] = True
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -----------------------------------------------------------
# DASHBOARD
# -----------------------------------------------------------
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", nombre=session.get("nombre"))

# -----------------------------------------------------------
# CARGA MASIVA
# -----------------------------------------------------------
@app.route("/upload_laboral", methods=["POST"])
def upload_laboral():
    if not session.get("autenticado"):
        return jsonify({"error": "No autorizado"}), 403

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No se enviaron archivos"})

    total_resultados, nuevos = 0, 0
    for f in files:
        nombre_archivo = f.filename
        try:
            df = pd.read_excel(f)
            resultados = []
            for _, row in df.iterrows():
                rfc = str(row.get("RFC", "")).strip().upper()
                if not rfc:
                    continue
                resultado = {
                    "rfc": rfc,
                    "nombre": str(row.get("NOMBRE", "")).strip(),
                    "puesto": str(row.get("PUESTO", "")).strip(),
                    "entes": [str(row.get("ENTE", "")).strip()],
                    "registros": [{
                        "ente": str(row.get("ENTE", "")).strip(),
                        "puesto": str(row.get("PUESTO", "")).strip(),
                        "monto": row.get("TOTAL", ""),
                        "qnas": row.get("QUINCENA", ""),
                        "fecha_ingreso": row.get("FECHA_INGRESO", ""),
                        "fecha_egreso": row.get("FECHA_EGRESO", "")
                    }],
                    "estado": "Sin valoración"
                }
                resultados.append(resultado)
            nuevos_res, _, _ = db_manager.comparar_con_historico(resultados)
            nuevos += db_manager.guardar_resultados(nuevos_res, "laboral", nombre_archivo)
            total_resultados += len(resultados)
        except Exception as e:
            return jsonify({"error": f"Error procesando {nombre_archivo}: {e}"})

    return jsonify({"mensaje": "Procesamiento completado", "total_resultados": total_resultados, "nuevos": nuevos})

# -----------------------------------------------------------
# RESULTADOS AGRUPADOS
# -----------------------------------------------------------
@app.route("/resultados")
def reporte_por_ente():
    resultados, _ = db_manager.obtener_resultados_paginados("laboral", None, 1, 10000)
    entes_usuario = session.get("entes", [])
    agrupado = {}

    conn = db_manager._connect()
    cur = conn.cursor()
    for r in resultados:
        entes_reg = list(set(r.get("entes", []) or ["Sin Ente"]))
        for e in entes_reg:
            if not (_allowed_all(entes_usuario) or any(_ente_match(eu, [e]) for eu in entes_usuario)):
                continue

            cur.execute("SELECT siglas, nombre FROM entes WHERE clave=?", (e,))
            row = cur.fetchone()
            ente_nombre = (row["siglas"] or row["nombre"]) if row else e
            agrupado.setdefault(ente_nombre, {})

            rfc = r.get("rfc")
            puesto = (
                r.get("puesto")
                or ", ".join({reg.get("puesto", "").strip() for reg in (r.get("registros") or []) if reg.get("puesto")})
                or "Sin puesto"
            )

            if rfc not in agrupado[ente_nombre]:
                agrupado[ente_nombre][rfc] = {
                    "rfc": r.get("rfc"),
                    "nombre": r.get("nombre"),
                    "puesto": puesto,
                    "entes": set(),
                    "estado": r.get("estado", "Sin valoración")
                }

            for en in r.get("entes", []):
                agrupado[ente_nombre][rfc]["entes"].add(_ente_sigla(en))
    conn.close()

    agrupado_final = {ente: list(valores.values()) for ente, valores in agrupado.items()}
    if not agrupado_final:
        return render_template("empty.html", mensaje="Sin registros del ente asignado.")
    return render_template("resultados.html", resultados=dict(sorted(agrupado_final.items())))

# -----------------------------------------------------------
# DETALLE POR RFC
# -----------------------------------------------------------
@app.route("/resultados/<rfc>")
def resultados_por_rfc(rfc):
    info = db_manager.obtener_resultados_por_rfc(rfc)
    if not info:
        return render_template("empty.html", mensaje="No hay registros del trabajador.")
    return render_template("detalle_rfc.html", rfc=rfc, info=info)

# -----------------------------------------------------------
# SOLVENTACIÓN DETALLE
# -----------------------------------------------------------
@app.route("/solventacion/<rfc>", methods=["GET", "POST"])
def solventacion_detalle(rfc):
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    if request.method == "POST":
        nuevo_estado = request.form.get("estado")
        comentario = request.form.get("comentario", "")
        db_manager.actualizar_solventacion(rfc, nuevo_estado, comentario)
        return redirect(url_for("resultados_por_rfc", rfc=rfc))

    info = db_manager.obtener_resultados_por_rfc(rfc)
    if not info:
        return render_template("empty.html", mensaje="No hay registros para este RFC.")
    return render_template("solventacion.html", rfc=rfc, info=info)

# -----------------------------------------------------------
# ACTUALIZAR ESTADO (AJAX)
# -----------------------------------------------------------
@app.route("/actualizar_estado", methods=["POST"])
def actualizar_estado():
    data = request.get_json(silent=True) or {}
    rfc = data.get("rfc")
    estado = data.get("estado")
    comentario = data.get("solventacion", "")

    if not rfc:
        return jsonify({"error": "Falta el RFC"}), 400

    try:
        filas = db_manager.actualizar_solventacion(rfc, estado, comentario)
        return jsonify({"mensaje": f"Registro actualizado ({filas} filas)", "estatus": estado})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -----------------------------------------------------------
# EXPORTAR POR ENTE
# -----------------------------------------------------------
@app.route("/exportar_por_ente")
def exportar_por_ente():
    ente_sel = request.args.get("ente", "").strip()
    if not ente_sel:
        return jsonify({"error": "No se seleccionó un ente"}), 400

    resultados, _ = db_manager.obtener_resultados_paginados("laboral", None, 1, 100000)
    seen, rows = set(), []
    for r in resultados:
        if not any(_ente_match(ente_sel, [e]) for e in (r.get("entes") or [])):
            continue
        for reg in (r.get("registros") or [{}]):
            key = (r.get("rfc"), reg.get("fecha_ingreso"), reg.get("fecha_egreso"), reg.get("monto"))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "RFC": r.get("rfc"),
                "Nombre": r.get("nombre"),
                "Puesto": reg.get("puesto"),
                "Fecha Alta": reg.get("fecha_ingreso"),
                "Fecha Baja": reg.get("fecha_egreso"),
                "Monto": reg.get("monto"),
                "Entes incompatibilidad": ", ".join(sorted({_ente_sigla(e) for e in (r.get("entes") or [])})),
                "Estatus": _estatus_label(r.get("estado"))
            })

    if not rows:
        return jsonify({"error": "No se encontraron registros para el ente seleccionado."}), 404

    df = pd.DataFrame(rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        hoja = f"Ente_{_ente_sigla(ente_sel)}"[:31]
        df.to_excel(writer, index=False, sheet_name=hoja)
    output.seek(0)
    return send_file(output, download_name=f"SASP_{_ente_sigla(ente_sel)}.xlsx", as_attachment=True)

# -----------------------------------------------------------
# EXPORTAR GENERAL
# -----------------------------------------------------------
@app.route("/exportar_general")
def exportar_excel_general():
    resultados, _ = db_manager.obtener_resultados_paginados("laboral", None, 1, 100000)
    seen, rows = set(), []
    for r in resultados:
        for reg in (r.get("registros") or [{}]):
            key = (r.get("rfc"), reg.get("fecha_ingreso"), reg.get("fecha_egreso"), reg.get("monto"))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "RFC": r.get("rfc"),
                "Nombre": r.get("nombre"),
                "Puesto": reg.get("puesto"),
                "Fecha Alta": reg.get("fecha_ingreso"),
                "Fecha Baja": reg.get("fecha_egreso"),
                "Monto": reg.get("monto"),
                "Entes incompatibilidad": ", ".join(sorted({_ente_sigla(e) for e in (r.get("entes") or [])})),
                "Estatus": _estatus_label(r.get("estado"))
            })

    if not rows:
        return jsonify({"error": "Sin datos para exportar."}), 404

    df = pd.DataFrame(rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Resultados")
    output.seek(0)
    return send_file(output, download_name="SASP_Resultados_Generales.xlsx", as_attachment=True)

# -----------------------------------------------------------
# CATÁLOGOS
# -----------------------------------------------------------
@app.route("/catalogos")
def catalogos_home():
    entes = db_manager.listar_entes()
    municipios = db_manager.listar_municipios()
    return render_template("catalogos.html", entes=entes, municipios=municipios)

# -----------------------------------------------------------
# CONTEXT PROCESSOR
# -----------------------------------------------------------
@app.context_processor
def inject_helpers():
    return {"_sanitize_text": _sanitize_text, "db_manager": db_manager}

# -----------------------------------------------------------
# MAIN
# -----------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4050))
    app.run(host="0.0.0.0", port=port, debug=True)

