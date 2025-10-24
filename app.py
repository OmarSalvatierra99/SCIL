# ===========================================================
# app.py — SCIL / SASP 2025
# Sistema de Auditoría de Servicios Personales
# Integrado con catálogos de ENTES y MUNICIPIOS
# ===========================================================

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, send_file
)
import os
import pandas as pd
from datetime import datetime
from io import BytesIO
from database import DatabaseManager

# -----------------------------------------------------------
# Configuración básica
# -----------------------------------------------------------
app = Flask(__name__)
app.secret_key = "ofs_sasp_2025"
db_manager = DatabaseManager("scil.db")

# -----------------------------------------------------------
# Utilidades simples
# -----------------------------------------------------------
def _sanitize_text(s):
    if not s:
        return ""
    return str(s).strip().upper().replace("Á","A").replace("É","E").replace("Í","I").replace("Ó","O").replace("Ú","U")

def _allowed_all(entes_usuario):
    return any(_sanitize_text(e) == "TODOS" for e in entes_usuario)

# -----------------------------------------------------------
# Rutas de autenticación
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
            session["entes"] = user["entes"]
            session["autenticado"] = True
            return redirect(url_for("dashboard"))
        else:
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
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    return render_template("dashboard.html", nombre=session.get("nombre"))

# -----------------------------------------------------------
# Carga de archivos Excel
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
                rfc = str(row.get("RFC","")).strip().upper()
                nombre = str(row.get("NOMBRE","")).strip()
                ente = str(row.get("ENTE","")).strip()
                puesto = str(row.get("PUESTO","")).strip()
                if not rfc:
                    continue
                resultado = {
                    "rfc": rfc,
                    "nombre": nombre,
                    "entes": [ente] if ente else [],
                    "registros": [{
                        "ente": ente,
                        "puesto": puesto,
                        "monto": row.get("TOTAL", ""),
                        "qnas": row.get("QUINCENA", ""),
                        "fecha_ingreso": row.get("FECHA_INGRESO", ""),
                        "fecha_egreso": row.get("FECHA_EGRESO", "")
                    }],
                    "estado": "Pendiente"
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
# Reportes generales — agrupados y ordenados por Ente
# -----------------------------------------------------------
@app.route("/resultados")
def reporte_por_ente():
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    resultados, _ = db_manager.obtener_resultados_paginados("laboral", None, 1, 10000)
    entes_usuario = session.get("entes", [])
    agrupado = {}

    for r in resultados:
        for e in r.get("entes", []) or ["Sin Ente"]:
            ente_nom = db_manager.normalizar_ente(e) or e
            if _allowed_all(entes_usuario) or any(_sanitize_text(eu) in _sanitize_text(e) or _sanitize_text(eu) in _sanitize_text(ente_nom) for eu in entes_usuario):
                agrupado.setdefault(ente_nom, []).append(r)

    if not agrupado:
        return render_template("empty.html", tipo="ente", mensaje="Sin registros del ente asignado.")

    agrupado_ordenado = dict(sorted(agrupado.items(), key=lambda x: x[0].upper()))
    return render_template("resultados.html", resultados=agrupado_ordenado)

# -----------------------------------------------------------
# Detalle por RFC
# -----------------------------------------------------------
@app.route("/resultados/<rfc>")
def resultados_por_rfc(rfc):
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    info = db_manager.obtener_resultados_por_rfc(rfc)
    if not info:
        return render_template("empty.html", tipo="rfc", mensaje="No hay registros del trabajador.")
    return render_template("detalle_rfc.html", rfc=rfc, info=info)

# -----------------------------------------------------------
# Solventación
# -----------------------------------------------------------
@app.route("/solventacion/<rfc>")
def solventacion_detalle(rfc):
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    info = db_manager.obtener_resultados_por_rfc(rfc)
    return render_template("solventacion.html", rfc=rfc, solventacion=info.get("solventacion",""))

@app.route("/actualizar_estado", methods=["POST"])
def actualizar_estado():
    if not session.get("autenticado"):
        return jsonify({"error": "No autorizado"}), 403
    data = request.get_json(silent=True) or {}
    rfc = data.get("rfc")
    estado = data.get("estado", "Solventado")
    solventacion = data.get("solventacion", "")
    try:
        filas = db_manager.actualizar_solventacion(rfc, estado, solventacion)
        return jsonify({"mensaje": f"Actualizado ({filas} filas)"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -----------------------------------------------------------
# Descarga en Excel
# -----------------------------------------------------------
@app.route("/exportar")
def exportar_excel():
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    resultados, _ = db_manager.obtener_resultados_paginados("laboral", None, 1, 10000)
    rows = []
    for r in resultados:
        for reg in (r.get("registros") or []):
            rows.append({
                "RFC": r.get("rfc"),
                "Nombre": r.get("nombre"),
                "Ente": ", ".join(r.get("entes", [])),
                "Puesto": reg.get("puesto"),
                "Monto": reg.get("monto"),
                "Quincenas": reg.get("qnas"),
                "Estado": r.get("estado")
            })
    df = pd.DataFrame(rows)
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, download_name="reporte.xlsx", as_attachment=True)

# -----------------------------------------------------------
# Catálogos de ENTES y MUNICIPIOS (solo consulta)
# -----------------------------------------------------------
@app.route("/catalogos")
def catalogos_home():
    if not session.get("autenticado"):
        return redirect(url_for("login"))
    entes = db_manager.listar_entes()
    municipios = db_manager.listar_municipios()
    return render_template("catalogos.html", entes=entes, municipios=municipios)

# -----------------------------------------------------------
# Context Processor
# -----------------------------------------------------------
@app.context_processor
def inject_helpers():
    return {
        "_sanitize_text": _sanitize_text,
        "db_manager": db_manager
    }

# -----------------------------------------------------------
# Main
# -----------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4050))
    app.run(host="0.0.0.0", port=port, debug=True)

