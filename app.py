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
import re
from database import DatabaseManager

# -----------------------------------------------------------
# Configuración básica
# -----------------------------------------------------------
app = Flask(__name__)
app.secret_key = "ofs_sasp_2025"
db_manager = DatabaseManager("scil.db")

# -----------------------------------------------------------
# Middleware: autenticación obligatoria
# -----------------------------------------------------------
@app.before_request
def verificar_autenticacion():
    """Evita acceso sin sesión a rutas protegidas."""
    libre = {"login", "static"}
    if request.endpoint not in libre and not session.get("autenticado"):
        return redirect(url_for("login"))

# -----------------------------------------------------------
# Utilidades básicas
# -----------------------------------------------------------
def _sanitize_text(s):
    if not s:
        return ""
    return str(s).strip().upper().replace("Á","A").replace("É","E").replace("Í","I").replace("Ó","O").replace("Ú","U")

def _allowed_all(entes_usuario):
    """Devuelve True si el usuario tiene acceso total."""
    return any(_sanitize_text(e) == "TODOS" for e in entes_usuario)

# -----------------------------------------------------------
# Catálogo de entes y formatos
# -----------------------------------------------------------
@lru_cache(maxsize=1)
def _entes_cache():
    """Clave → (siglas, nombre)."""
    conn = db_manager._connect(); cur = conn.cursor()
    cur.execute("SELECT clave, siglas, nombre FROM entes")
    cache = {}; by_nombre = {}
    for row in cur.fetchall():
        clave = (row["clave"] or "").strip().upper()
        siglas = (row["siglas"] or "").strip()
        nombre = (row["nombre"] or "").strip().upper()
        cache[clave] = (siglas if siglas else None, nombre if nombre else None)
        if nombre:
            by_nombre[nombre] = siglas if siglas else None
    conn.close()
    return {"by_clave": cache, "by_nombre": by_nombre}

def _ente_sigla(clave_o_nombre: str) -> str:
    """Devuelve SIGLA si existe; si no, nombre; si no, el original."""
    if not clave_o_nombre:
        return ""
    s = str(clave_o_nombre).strip()
    u = s.upper()
    c = _entes_cache()
    by_clave = c["by_clave"]; by_nombre = c["by_nombre"]
    if u in by_clave:
        sig, nom = by_clave[u]
        return sig or (nom or s)
    if u in by_nombre:
        return by_nombre[u] or s
    return s

_qna_pat = re.compile(r'^(?:QNA)?0?([1-9]|1[0-2])$', re.IGNORECASE)
_yq_pat  = re.compile(r'^(\d{4})Q(0[1-9]|1[0-2])$')

def _fmt_quincena(q):
    """Convierte códigos de quincena en texto legible."""
    meses = [
        "Enero","Febrero","Marzo","Abril","Mayo","Junio",
        "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"
    ]
    if not q:
        return ""
    q = str(q).strip().upper()
    if q in {"ALL", "TODO", "TODO EL EJERCICIO"}:
        return "Activo en todo el ejercicio"
    m = _qna_pat.match(q)
    if m:
        n = int(m.group(1))
        mes = meses[(n - 1) % 12]
        mitad = "1ª" if n <= 12 else "2ª"
        return f"{mitad} Quincena de {mes}"
    m = _yq_pat.match(q)
    if m:
        yyyy, mm = m.groups()
        mes = meses[int(mm) - 1]
        return f"Quincena de {mes} {yyyy}"
    if "-" in q:
        partes = [p.strip() for p in q.split("-") if p.strip()]
        return " - ".join(_fmt_quincena(p) for p in partes)
    return q

def _estatus_label(v):
    """Normaliza estados a tres valores: Solventada / No Solventada / Sin valoración."""
    v = (v or "").strip().lower()
    if not v:
        return "Sin valoración"
    if "no" in v:
        return "No Solventada"
    if "solvent" in v:
        return "Solventada"
    if "pend" in v or "sin" in v:
        return "Sin valoración"
    return "Sin valoración"

# -----------------------------------------------------------
# Autenticación
# -----------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario","").strip()
        clave = request.form.get("clave","").strip()
        user = db_manager.get_usuario(usuario, clave)

        if user:
            session["usuario"] = user["usuario"]
            session["nombre"] = user["nombre"]
            session["entes"] = ["TODOS"] if user["usuario"].lower() in ["odilia","victor"] else user["entes"]
            session["autenticado"] = True
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Credenciales inválidas")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -----------------------------------------------------------
# Panel principal
# -----------------------------------------------------------
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", nombre=session.get("nombre"))

# -----------------------------------------------------------
# Carga masiva de archivos Excel
# -----------------------------------------------------------
@app.route("/upload_laboral", methods=["POST"])
def upload_laboral():
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
                rfc = str(row.get("RFC","")).strip().upper()
                if not rfc:
                    continue
                nombre = str(row.get("NOMBRE","")).strip()
                ente = str(row.get("ENTE","")).strip()
                puesto = str(row.get("PUESTO","")).strip()
                resultado = {
                    "rfc": rfc,
                    "nombre": nombre,
                    "puesto": puesto,
                    "entes": [ente] if ente else [],
                    "registros": [{
                        "ente": ente,
                        "puesto": puesto,
                        "monto": row.get("TOTAL",""),
                        "qnas": row.get("QUINCENA",""),
                        "fecha_ingreso": row.get("FECHA_INGRESO",""),
                        "fecha_egreso": row.get("FECHA_EGRESO","")
                    }],
                    "estado": "Sin valoración"
                }
                resultados.append(resultado)
            nuevos_res, repetidos, _ = db_manager.comparar_con_historico(resultados)
            nuevos += db_manager.guardar_resultados(nuevos_res, "laboral", nombre_archivo)
            total_resultados += len(resultados)
        except Exception as e:
            return jsonify({"error": f"Error procesando {nombre_archivo}: {e}"})
    return jsonify({
        "mensaje": "Procesamiento completado",
        "total_resultados": total_resultados,
        "nuevos": nuevos
    })

# -----------------------------------------------------------
# Reporte general agrupado por ente
# -----------------------------------------------------------
@app.route("/resultados")
def reporte_por_ente():
    resultados, _ = db_manager.obtener_resultados_paginados("laboral", None, 1, 10000)
    entes_usuario = session.get("entes", [])
    agrupado = {}

    conn = db_manager._connect(); cur = conn.cursor()
    for r in resultados:
        entes_reg = r.get("entes", []) or ["Sin Ente"]
        for e in entes_reg:
            ente_nom = db_manager.normalizar_ente(e) or e
            if not (_allowed_all(entes_usuario) or any(
                _sanitize_text(eu) in _sanitize_text(e) or _sanitize_text(eu) in _sanitize_text(ente_nom)
                for eu in entes_usuario
            )):
                continue

            clave_ente = ente_nom.strip().upper()
            agrupado.setdefault(clave_ente, {})

            rfc = r.get("rfc")
            estado = r.get("estado","Sin valoración")
            registros = r.get("registros", [])
            puestos = sorted({reg.get("puesto","").strip() for reg in registros if reg.get("puesto")})
            puesto = ", ".join(puestos) if puestos else "Sin puesto"

            if rfc not in agrupado[clave_ente]:
                agrupado[clave_ente][rfc] = {
                    "rfc": r["rfc"],
                    "nombre": r["nombre"],
                    "puesto": puesto,
                    "entes": set(),
                    "qnas": set(),
                    "estado": estado
                }

            for clave in r.get("entes", []):
                cur.execute("SELECT siglas, nombre FROM entes WHERE clave=?", (clave,))
                row = cur.fetchone()
                if row and row["siglas"]:
                    agrupado[clave_ente][rfc]["entes"].add(row["siglas"])
                elif row and row["nombre"]:
                    agrupado[clave_ente][rfc]["entes"].add(row["nombre"])
                else:
                    agrupado[clave_ente][rfc]["entes"].add(clave)
    conn.close()

    agrupado_final = {}
    for ente, rfcs in agrupado.items():
        agrupado_final[ente] = []
        for r in rfcs.values():
            agrupado_final[ente].append({
                "rfc": r["rfc"],
                "nombre": r["nombre"],
                "puesto": r["puesto"],
                "entes": sorted(r["entes"]),
                "descripcion": "Activo en todo el ejercicio" if len(r["qnas"]) >= 12 else "",
                "estado": r["estado"]
            })

    agrupado_ordenado = dict(sorted(agrupado_final.items(), key=lambda x: x[0].upper()))
    if not agrupado_ordenado:
        return render_template("empty.html", mensaje="Sin registros del ente asignado.")
    return render_template("resultados.html", resultados=agrupado_ordenado)

# -----------------------------------------------------------
# Detalle por RFC
# -----------------------------------------------------------
@app.route("/resultados/<rfc>")
def resultados_por_rfc(rfc):
    info = db_manager.obtener_resultados_por_rfc(rfc)
    if not info:
        return render_template("empty.html", mensaje="No hay registros del trabajador.")
    return render_template("detalle_rfc.html", rfc=rfc, info=info)

# -----------------------------------------------------------
# Solventación
# -----------------------------------------------------------
@app.route("/solventacion/<rfc>")
def solventacion_detalle(rfc):
    info = db_manager.obtener_resultados_por_rfc(rfc)
    return render_template("solventacion.html", rfc=rfc, solventacion=info.get("solventacion",""))

@app.route("/actualizar_estado", methods=["POST"])
def actualizar_estado():
    data = request.get_json(silent=True) or {}
    rfc = data.get("rfc")
    estado = _estatus_label(data.get("estado"))
    solventacion = data.get("solventacion","")
    try:
        filas = db_manager.actualizar_solventacion(rfc, estado, solventacion)
        return jsonify({"mensaje": f"Actualizado ({filas} filas) correctamente", "estatus": estado})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -----------------------------------------------------------
# Exportar general (Excel)
# -----------------------------------------------------------
@app.route("/exportar_general")
def exportar_excel_general():
    resultados, _ = db_manager.obtener_resultados_paginados("laboral", None, 1, 100000)
    rows = []
    for r in resultados:
        rfc = r.get("rfc")
        nombre = r.get("nombre")
        estatus = _estatus_label(r.get("estado"))
        entes_siglas = [_ente_sigla(e) for e in (r.get("entes") or [])]
        for reg in (r.get("registros") or [{}]):
            q = reg.get("qnas") or "-"
            rows.append({
                "RFC": rfc,
                "Nombre": nombre,
                "Entes incompatibilidad": ", ".join(entes_siglas),
                "Puesto": reg.get("puesto"),
                "Fecha Alta": reg.get("fecha_ingreso"),
                "Fecha Baja": reg.get("fecha_egreso"),
                "Monto": reg.get("monto"),
                "Cruce quincena": _fmt_quincena(q),
                "Estatus": estatus
            })
    if not rows:
        return jsonify({"error": "Sin datos para exportar."}), 404

    df = pd.DataFrame(rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        sheet_name = "Resultados Generales"
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.sheets[sheet_name]
        for col in ws.columns:
            maxlen = max(len(str(c.value)) if c.value else 0 for c in col)
            ws.column_dimensions[col[0].column_letter].width = min(maxlen + 2, 42)
    output.seek(0)
    return send_file(
        output,
        download_name="SASP_Resultados_Generales.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# -----------------------------------------------------------
# Exportar por ente (Excel)
# -----------------------------------------------------------
@app.route("/exportar_por_ente")
def exportar_excel_por_ente():
    ente_sel = request.args.get("ente")
    if not ente_sel:
        return jsonify({"error": "No se seleccionó un ente"}), 400

    ente_target = ente_sel.strip().upper()
    resultados, _ = db_manager.obtener_resultados_paginados("laboral", None, 1, 100000)
    rows = []
    for r in resultados:
        entes_norm = [db_manager.normalizar_ente(e) or e for e in (r.get("entes") or [])]
        if not any(ente_target in (e or "").upper() for e in entes_norm):
            continue
        estatus = _estatus_label(r.get("estado"))
        entes_siglas = [_ente_sigla(e) for e in (r.get("entes") or [])]
        for reg in (r.get("registros") or [{}]):
            q = reg.get("qnas") or "-"
            rows.append({
                "RFC": r.get("rfc"),
                "Nombre": r.get("nombre"),
                "Puesto": reg.get("puesto"),
                "Fecha Alta": reg.get("fecha_ingreso"),
                "Fecha Baja": reg.get("fecha_egreso"),
                "Monto": reg.get("monto"),
                "Cruce quincena": _fmt_quincena(q),
                "Estatus": estatus,
                "Entes incompatibilidad": ", ".join(entes_siglas)
            })
    if not rows:
        return jsonify({"error": "No se encontraron registros para el ente seleccionado."}), 404

    df = pd.DataFrame(rows)
    sigla_hoja = _ente_sigla(ente_sel)
    hoja = f"Ente - {sigla_hoja}"[:31]

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=hoja)
        ws = writer.sheets[hoja]
        for col in ws.columns:
            maxlen = max(len(str(c.value)) if c.value else 0 for c in col)
            ws.column_dimensions[col[0].column_letter].width = min(maxlen + 2, 42)
    output.seek(0)
    filename = f"SASP_{sigla_hoja.replace(' ','_')}.xlsx"
    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# -----------------------------------------------------------
# Catálogos
# -----------------------------------------------------------
@app.route("/catalogos")
def catalogos_home():
    entes = db_manager.listar_entes()
    municipios = db_manager.listar_municipios()
    return render_template("catalogos.html", entes=entes, municipios=municipios)

# -----------------------------------------------------------
# Context Processor
# -----------------------------------------------------------
@app.context_processor
def inject_helpers():
    return {"_sanitize_text": _sanitize_text, "db_manager": db_manager}

# -----------------------------------------------------------
# Main
# -----------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4050))
    app.run(host="0.0.0.0", port=port, debug=True)

