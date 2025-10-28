# ===========================================================
# app.py — SASP / SCIL 2025
# Sistema de Auditoría de Servicios Personales
# Órgano de Fiscalización Superior del Estado de Tlaxcala
# ===========================================================

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, send_file
)
import os
import logging
import pandas as pd
from io import BytesIO
from functools import lru_cache
from core.database import DatabaseManager
from core.data_processor import DataProcessor

# -----------------------------------------------------------
# Logging
# -----------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("SCIL")

# -----------------------------------------------------------
# Configuración
# -----------------------------------------------------------
app = Flask(__name__)
app.secret_key = "ofs_sasp_2025"

DB_PATH = os.environ.get("SCIL_DB", "scil.db")
db_manager = DatabaseManager(DB_PATH)
data_processor = DataProcessor()  # usa el mismo db_path por defecto

log.info("Iniciando SCIL | CWD=%s | DB=%s", os.getcwd(), DB_PATH)

# -----------------------------------------------------------
# Middleware
# -----------------------------------------------------------
@app.before_request
def verificar_autenticacion():
    libres = {"login", "static"}
    if request.endpoint not in libres and not session.get("autenticado"):
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
    data = {}
    for r in cur.fetchall():
        clave = (r["clave"] or "").strip().upper()
        data[clave] = {
            "siglas": (r["siglas"] or "").strip().upper(),
            "nombre": (r["nombre"] or "").strip().upper()
        }
    conn.close()
    return data

def _ente_match(ente_usuario, clave_lista):
    euser = _sanitize_text(ente_usuario)
    for k, d in _entes_cache().items():
        if euser in {k, d["siglas"], d["nombre"]}:
            for c in clave_lista:
                if _sanitize_text(c) in {k, d["siglas"], d["nombre"]}:
                    return True
    return False

def _ente_sigla(clave):
    if not clave:
        return ""
    s = _sanitize_text(clave)
    for k, d in _entes_cache().items():
        if s in {k, d["siglas"], d["nombre"]}:
            return d["siglas"] or d["nombre"] or s
    return s

def _ente_display(v):
    if not v:
        return "Sin Ente"
    s = _sanitize_text(v)
    for k, d in _entes_cache().items():
        if s in {k, d["siglas"], d["nombre"]}:
            return d["siglas"] or d["nombre"] or v
    return v

# -----------------------------------------------------------
# LOGIN / LOGOUT
# -----------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("clave", "").strip()
        user = db_manager.get_usuario(usuario, clave)
        if not user:
            log.warning("Login fallido para usuario=%s", usuario)
            return render_template("login.html", error="Credenciales inválidas")

        session.update({
            "usuario": user["usuario"],
            "nombre": user["nombre"],
            "autenticado": True
        })
        entes = user["entes"]
        session["entes"] = ["TODOS"] if user["usuario"].lower() in {"odilia", "victor"} else entes
        log.info("Login ok usuario=%s entes=%s", user["usuario"], ",".join(session["entes"]))
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    usuario = session.get("usuario")
    session.clear()
    log.info("Logout usuario=%s", usuario)
    return redirect(url_for("login"))

# -----------------------------------------------------------
# DASHBOARD
# -----------------------------------------------------------
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", nombre=session.get("nombre"))

# -----------------------------------------------------------
# CARGA MASIVA (DataProcessor cruza por RFC y QNAs)
# -----------------------------------------------------------
@app.route("/upload_laboral", methods=["POST"])
def upload_laboral():
    if not session.get("autenticado"):
        return jsonify({"error": "No autorizado"}), 403

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No se enviaron archivos"})

    try:
        nombres = [getattr(f, "filename", "archivo.xlsx") for f in files]
        log.info("Upload recibido: %s", nombres)
        resultados = data_processor.procesar_archivos(files)
        log.info("Cruces detectados=%d", len(resultados))
        nuevos_res, repetidos, n_rep = db_manager.comparar_con_historico(resultados)
        nuevos = db_manager.guardar_resultados(nuevos_res)
        log.info("Guardados nuevos=%d | Repetidos=%d", nuevos, n_rep)
        return jsonify({
            "mensaje": "Procesamiento completado",
            "total_resultados": len(resultados),
            "nuevos": nuevos
        })
    except Exception as e:
        log.exception("Error en upload_laboral")
        return jsonify({"error": f"Error al procesar archivos: {e}"}), 500

# -----------------------------------------------------------
# RESULTADOS AGRUPADOS
# -----------------------------------------------------------
@app.route("/resultados")
def reporte_por_ente():
    resultados, _ = db_manager.obtener_resultados_paginados("laboral", None, 1, 10000)
    entes_usuario = session.get("entes", [])
    agrupado = {}

    for r in resultados:
        entes_reg = list(set(r.get("entes", []) or ["Sin Ente"]))
        for e in entes_reg:
            if not (_allowed_all(entes_usuario) or any(_ente_match(eu, [e]) for eu in entes_usuario)):
                continue

            ente_nombre = _ente_display(e)
            agrupado.setdefault(ente_nombre, {})

            rfc = r.get("rfc")
            puesto = (
                r.get("puesto")
                or ", ".join({reg.get("puesto", "").strip() for reg in (r.get("registros") or []) if reg.get("puesto")})
                or "Sin puesto"
            )

            if rfc not in agrupado[ente_nombre]:
                agrupado[ente_nombre][rfc] = {
                    "rfc": r["rfc"],
                    "nombre": r["nombre"],
                    "puesto": puesto,
                    "entes": set(),
                    "estado": r.get("estado", "Sin valoración")
                }

            for en in r.get("entes", []):
                agrupado[ente_nombre][rfc]["entes"].add(_ente_sigla(en))

    agrupado_final = {k: list(v.values()) for k, v in agrupado.items()}
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

    # Inyectar estados por ente si existen solventaciones específicas
    mapa_solvs = db_manager.get_solventaciones_por_rfc(rfc)  # {ente_clave: {estado, comentario}}
    if mapa_solvs and info.get("registros"):
        for reg in info["registros"]:
            ente_clave = db_manager.normalizar_ente_clave(reg.get("ente"))
            if ente_clave in mapa_solvs:
                reg["estado_ente"] = mapa_solvs[ente_clave]["estado"]
                reg["comentario_ente"] = mapa_solvs[ente_clave]["comentario"]

        # Estado general: si todos iguales usa uno, si no "Mixto"
        estados_regs = {reg.get("estado_ente") or info.get("estado") for reg in info["registros"]}
        estados_regs = {e for e in estados_regs if e}
        if len(estados_regs) == 1:
            info["estado"] = estados_regs.pop()
        elif len(estados_regs) > 1:
            info["estado"] = "Mixto"

    return render_template("detalle_rfc.html", rfc=rfc, info=info)

# -----------------------------------------------------------
# SOLVENTACIÓN (por RFC o por RFC+Ente)
# -----------------------------------------------------------
@app.route("/solventacion/<rfc>", methods=["GET", "POST"])
def solventacion_detalle(rfc):
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    # opcional ?ente=ENTE_##### para solventar ese ente en particular
    ente_sel = request.args.get("ente")

    if request.method == "POST":
        estado = request.form.get("estado")
        comentario = request.form.get("comentario", "")
        ente_post = request.form.get("ente") or ente_sel
        filas = db_manager.actualizar_solventacion(rfc, estado, comentario, ente=ente_post)
        log.info("Solventación rfc=%s ente=%s filas=%s", rfc, ente_post, filas)
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
    ente = data.get("ente")  # opcional

    if not rfc:
        return jsonify({"error": "Falta el RFC"}), 400
    try:
        filas = db_manager.actualizar_solventacion(rfc, estado, comentario, ente=ente)
        log.info("AJAX solventación rfc=%s ente=%s -> %s", rfc, ente, estado)
        return jsonify({"mensaje": f"Registro actualizado ({filas} filas)", "estatus": estado})
    except Exception as e:
        log.exception("Error en actualizar_estado")
        return jsonify({"error": str(e)}), 500

# -----------------------------------------------------------
# UTIL: construir filas agregadas por (RFC, ENTE_ORIGEN, PUESTO, FECHAS, MONTO)
#       acumulando QUINCENAS y ENTES INCOMPATIBILIDAD a través de todos los hallazgos
# -----------------------------------------------------------
def _construir_filas_export(resultados):
    agregados = {}  # key -> dict fila
    for r in resultados:
        # r representa UN cruce en UNA quincena (DataProcessor genera 1 hallazgo por quincena)
        # Ej: r["fecha_comun"] = "2025Q03" → qna_num = 3
        qna_num = None
        fc = (r.get("fecha_comun") or "").upper()
        if "Q" in fc:
            try:
                qna_num = int(fc.split("Q")[-1])
            except Exception:
                qna_num = None

        entes_cruce = r.get("entes") or []  # todos los entes involucrados en esa quincena
        for reg in (r.get("registros") or []):
            ente_origen = reg.get("ente") or "Sin Ente"
            key = (
                r.get("rfc"),
                _sanitize_text(ente_origen),
                reg.get("puesto"),
                reg.get("fecha_ingreso"),
                reg.get("fecha_egreso"),
                reg.get("monto"),
            )
            if key not in agregados:
                agregados[key] = {
                    "RFC": r.get("rfc"),
                    "Nombre": r.get("nombre"),
                    "Puesto": reg.get("puesto"),
                    "Fecha Alta": reg.get("fecha_ingreso"),
                    "Fecha Baja": reg.get("fecha_egreso"),
                    "Total Percepciones": reg.get("monto"),
                    "Ente Origen": _ente_display(ente_origen),
                    "_ente_origen_raw": ente_origen,  # para filtros/estado
                    "_entes_incomp_set": set(),
                    "_qnas_set": set(),
                    "_estado_base": _estatus_label(r.get("estado")),
                }
            # acumular quincena del cruce
            if qna_num:
                agregados[key]["_qnas_set"].add(qna_num)

            # acumular entes incompatibles (todos menos el origen)
            for e in entes_cruce:
                if _sanitize_text(e) != _sanitize_text(ente_origen):
                    agregados[key]["_entes_incomp_set"].add(e)

    # materializar filas finales
    filas = []
    for key, item in agregados.items():
        # Quincenas
        if len(item["_qnas_set"]) >= 12:
            quincenas = "Activo en Todo el Ejercicio"
        elif item["_qnas_set"]:
            quincenas = ", ".join(str(q) for q in sorted(item["_qnas_set"]))
        else:
            quincenas = "N/A"

        # Entes incompatibles (ya excluye origen)
        entes_incomp = ", ".join(
            sorted({_ente_sigla(e) for e in item["_entes_incomp_set"]})
        ) or "Sin otros entes"

        # Estado (da prioridad a solventación por RFC+ente origen si existe)
        ente_clave = db_manager.normalizar_ente_clave(item["_ente_origen_raw"])
        est_ente = db_manager.get_estado_rfc_ente(item["RFC"], ente_clave)
        est_final = est_ente or item["_estado_base"]

        filas.append({
            "RFC": item["RFC"],
            "Nombre": item["Nombre"],
            "Puesto": item["Puesto"],
            "Fecha Alta": item["Fecha Alta"],
            "Fecha Baja": item["Fecha Baja"],
            "Total Percepciones": item["Total Percepciones"],
            "Ente Origen": item["Ente Origen"],
            "Entes Incompatibilidad": entes_incomp,
            "Quincenas": quincenas,
            "Estatus": est_final,
        })
    return filas


# -----------------------------------------------------------
# EXPORTAR POR ENTE (filtra por ENTE ORIGEN)
# -----------------------------------------------------------
@app.route("/exportar_por_ente")
def exportar_por_ente():
    ente_sel = request.args.get("ente", "").strip()
    if not ente_sel:
        return jsonify({"error": "No se seleccionó un ente"}), 400

    resultados, _ = db_manager.obtener_resultados_paginados("laboral", None, 1, 100000)
    filas = _construir_filas_export(resultados)

    # Filtrar por Ente Origen seleccionado (acepta sigla/nombre/clave)
    filas = [f for f in filas if _ente_match(ente_sel, [f["Ente Origen"]])]
    if not filas:
        return jsonify({"error": "No se encontraron registros para el ente seleccionado."}), 404

    df = pd.DataFrame(filas)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        hoja = f"Ente_{_ente_sigla(ente_sel)}"[:31]
        df.to_excel(writer, index=False, sheet_name=hoja)
    output.seek(0)
    return send_file(output, download_name=f"SASP_{_ente_sigla(ente_sel)}.xlsx", as_attachment=True)


# -----------------------------------------------------------
# EXPORTAR GENERAL (todas las filas)
# -----------------------------------------------------------
@app.route("/exportar_general")
def exportar_excel_general():
    resultados, _ = db_manager.obtener_resultados_paginados("laboral", None, 1, 100000)
    filas = _construir_filas_export(resultados)
    if not filas:
        return jsonify({"error": "Sin datos para exportar."}), 404

    df = pd.DataFrame(filas)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Resultados_Generales")
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
# CONTEXTO GLOBAL
# -----------------------------------------------------------
@app.context_processor
def inject_helpers():
    return {"_sanitize_text": _sanitize_text, "db_manager": db_manager}

# -----------------------------------------------------------
# MAIN
# -----------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4050))
    log.info("Levantando Flask en 0.0.0.0:%s (debug=%s)", port, True)
    app.run(host="0.0.0.0", port=port, debug=True)

