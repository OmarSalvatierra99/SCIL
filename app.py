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
    """Devuelve True si el usuario tiene acceso total."""
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

            # 🔹 Odilia y Víctor tienen acceso a todo automáticamente
            if user["usuario"].lower() in ["odilia", "victor"]:
                session["entes"] = ["TODOS"]
            else:
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
                    "puesto": puesto,
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
# Reportes generales — agrupados por Ente y RFC
# -----------------------------------------------------------
@app.route("/resultados")
def reporte_por_ente():
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    resultados, _ = db_manager.obtener_resultados_paginados("laboral", None, 1, 10000)
    entes_usuario = session.get("entes", [])
    agrupado = {}

    conn = db_manager._connect()
    cur = conn.cursor()

    for r in resultados:
        entes_reg = r.get("entes", []) or ["Sin Ente"]
        for e in entes_reg:
            ente_nom = db_manager.normalizar_ente(e) or e

            # Filtra entes según permisos
            if not (_allowed_all(entes_usuario) or any(
                _sanitize_text(eu) in _sanitize_text(e) or _sanitize_text(eu) in _sanitize_text(ente_nom)
                for eu in entes_usuario
            )):
                continue

            clave_ente = ente_nom.strip().upper()
            agrupado.setdefault(clave_ente, {})

            rfc = r.get("rfc")
            descripcion = r.get("descripcion", "")
            fecha = r.get("fecha_comun", "")
            estado = r.get("estado", "Sin estado")

            # 🔹 Extraer puesto desde registros
            registros = r.get("registros", [])
            puestos = sorted({reg.get("puesto", "").strip() for reg in registros if reg.get("puesto")})
            puesto = ", ".join(puestos) if puestos else "Sin puesto"

            if rfc not in agrupado[clave_ente]:
                agrupado[clave_ente][rfc] = {
                    "rfc": rfc,
                    "nombre": r.get("nombre", ""),
                    "puesto": puesto,
                    "entes": set(),
                    "descripcion": [],
                    "qnas": set(),
                    "estado": estado
                }

            # --- Traducir claves a siglas ---
            for clave in r.get("entes", []):
                cur.execute("SELECT siglas, nombre FROM entes WHERE clave=?", (clave,))
                row = cur.fetchone()
                if row and row["siglas"]:
                    agrupado[clave_ente][rfc]["entes"].add(row["siglas"])
                elif row and row["nombre"]:
                    agrupado[clave_ente][rfc]["entes"].add(row["nombre"])
                else:
                    agrupado[clave_ente][rfc]["entes"].add(clave)

            agrupado[clave_ente][rfc]["descripcion"].append(descripcion)
            if fecha:
                agrupado[clave_ente][rfc]["qnas"].add(fecha)

    conn.close()

    # 🔹 Consolidar sin duplicados
    agrupado_final = {}
    for ente, rfcs in agrupado.items():
        agrupado_final[ente] = []
        for r in rfcs.values():
            qnas = sorted(r["qnas"])
            if len(qnas) == 12 or set(qnas) == {f"QNA{i}" for i in range(1, 13)}:
                descripcion = "Activo en todo el ejercicio"
            else:
                descripcion = ", ".join(sorted(set(r["descripcion"]))) or "Sin descripción"
            agrupado_final[ente].append({
                "rfc": r["rfc"],
                "nombre": r["nombre"],
                "puesto": r["puesto"],
                "entes": sorted(r["entes"]),
                "descripcion": descripcion,
                "estado": r["estado"]
            })

    agrupado_ordenado = dict(sorted(agrupado_final.items(), key=lambda x: x[0].upper()))

    if not agrupado_ordenado:
        return render_template("empty.html", tipo="ente", mensaje="Sin registros del ente asignado.")

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
        return jsonify({"mensaje": f"Actualizado ({filas} filas) correctamente"})
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
                "Puesto": reg.get("puesto"),
                "Ente": ", ".join(r.get("entes", [])),
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
# Catálogos de ENTES y MUNICIPIOS
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
    return {"_sanitize_text": _sanitize_text, "db_manager": db_manager}

# -----------------------------------------------------------
# Main
# -----------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4050))
    app.run(host="0.0.0.0", port=port, debug=True)

