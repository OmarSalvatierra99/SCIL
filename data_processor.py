# =========================================================
# data_processor.py — SCIL / Auditoría Laboral por Quincenas (QNA)
# Versión 2025 — Detección de cruces entre entes por quincenas no vacías (multiarchivo)
# =========================================================

import pandas as pd
from collections import defaultdict
import re
from datetime import datetime, date


class DataProcessor:
    def __init__(self):
        self.column_cache = {}

    # ----------------------------------------------------
    # LIMPIEZA / NORMALIZACIÓN
    # ----------------------------------------------------
    def limpiar_rfc(self, rfc):
        if pd.isna(rfc):
            return None
        rfc_s = str(rfc).strip().upper()
        rfc_s = re.sub(r"[^A-Z0-9]", "", rfc_s)
        return rfc_s if 10 <= len(rfc_s) <= 13 else None

    def limpiar_fecha(self, fecha):
        if pd.isna(fecha):
            return None
        if isinstance(fecha, (datetime, date)):
            return fecha.strftime("%Y-%m-%d")
        s = str(fecha).strip()
        if not s or s.lower() in ["nan", "nat", "none", "null"]:
            return None
        try:
            f = pd.to_datetime(s, errors="coerce", dayfirst=False)
            return f.strftime("%Y-%m-%d") if not pd.isna(f) else None
        except Exception:
            return None

    # ----------------------------------------------------
    # DETECCIÓN DE COLUMNAS
    # ----------------------------------------------------
    def detectar_columnas(self, df):
        cols = df.columns.astype(str)
        rfc_col = next((c for c in cols if "RFC" in c.upper()), None)
        nombre_col = next((c for c in cols if "NOMBRE" in c.upper()), None)
        puesto_col = next((c for c in cols if "PUESTO" in c.upper()), None)
        f_ing = next((c for c in cols if "FECHA_INGRESO" in c.upper()), None)
        f_egr = next((c for c in cols if "FECHA_EGRESO" in c.upper()), None)
        qnas = [c for c in cols if c.upper().startswith("QNA")]
        return rfc_col, nombre_col, puesto_col, f_ing, f_egr, qnas

    # ----------------------------------------------------
    # PROCESAMIENTO PRINCIPAL (MULTIARCHIVO)
    # ----------------------------------------------------
    def procesar_archivos(self, filepaths):
        print("📊 Procesando varios archivos laborales por quincenas...")
        entes_rfc = defaultdict(list)

        for filepath in filepaths:
            xl = pd.ExcelFile(filepath)
            nombre_archivo = filepath.split("/")[-1]
            print(f"🔹 Analizando archivo: {nombre_archivo}")

            for sheet in xl.sheet_names:
                df = xl.parse(sheet)
                df.columns = df.columns.str.strip().str.upper().str.replace(" ", "_")
                rfc_col, nombre_col, puesto_col, f_ing, f_egr, qnas = self.detectar_columnas(df)

                if not rfc_col or not qnas:
                    continue

                ente_label = f"{nombre_archivo}_{sheet}"
                for _, row in df.iterrows():
                    rfc = self.limpiar_rfc(row.get(rfc_col))
                    if not rfc:
                        continue
                    registro = {
                        "ente": ente_label,
                        "nombre": str(row.get(nombre_col, "")).strip(),
                        "puesto": str(row.get(puesto_col, "")).strip(),
                        "fecha_ingreso": self.limpiar_fecha(row.get(f_ing)) if f_ing else None,
                        "fecha_egreso": self.limpiar_fecha(row.get(f_egr)) if f_egr else None,
                        "qnas": {q: row.get(q) for q in qnas},
                    }
                    entes_rfc[rfc].append(registro)

        resultados = self._cruces_quincenales(entes_rfc)
        print(f"📈 {len(resultados)} hallazgos laborales generados (modelo QNA).")
        return resultados

    # ----------------------------------------------------
    # REGLAS AUDITORAS — CRUCES ENTRE ENTES POR QNA
    # ----------------------------------------------------
    def _cruces_quincenales(self, entes_rfc):
        hallazgos = []
        for rfc, registros in entes_rfc.items():
            if len(registros) < 2:
                continue

            # Detectar quincenas con valor no vacío
            qnas_presentes = sorted(
                {q for r in registros for q, v in r["qnas"].items() if pd.notna(v) and str(v).strip() != ""}
            )
            if not qnas_presentes:
                continue

            for qna in qnas_presentes:
                activos = [
                    r for r in registros
                    if pd.notna(r["qnas"].get(qna)) and str(r["qnas"].get(qna)).strip() != ""
                ]
                entes_activos = sorted({r["ente"] for r in activos})
                if len(entes_activos) > 1:
                    hallazgos.append({
                        "rfc": rfc,
                        "nombre": activos[0].get("nombre", ""),
                        "registros": activos,
                        "entes": entes_activos,
                        "fecha_comun": qna,
                        "tipo_patron": "CRUCE_ENTRE_ENTES_QNA",
                        "descripcion": f"El trabajador tiene datos en la quincena {qna} en más de un ente."
                    })
        return hallazgos

