# ===========================================================
# core/data_processor.py — SCIL / SASP 2025
# Procesamiento de archivos laborales y cruces quincenales
# ===========================================================

import pandas as pd
import re
from datetime import datetime, date
from collections import defaultdict
from core.database import DatabaseManager


class DataProcessor:
    def __init__(self):
        self.db = DatabaseManager("scil.db")
        self.mapa_siglas = self.db.get_mapa_siglas()
        self.mapa_inverso = self.db.get_mapa_claves_inverso()

    # -------------------------------------------------------
    # Limpieza y normalización
    # -------------------------------------------------------
    def limpiar_rfc(self, rfc):
        if pd.isna(rfc):
            return None
        s = re.sub(r"[^A-Z0-9]", "", str(rfc).strip().upper())
        return s if 10 <= len(s) <= 13 else None

    def limpiar_fecha(self, fecha):
        if pd.isna(fecha):
            return None
        if isinstance(fecha, (datetime, date)):
            return fecha.strftime("%Y-%m-%d")
        s = str(fecha).strip()
        if s.lower() in {"", "nan", "nat", "none", "null"}:
            return None
        f = pd.to_datetime(s, errors="coerce", dayfirst=True)
        return f.strftime("%Y-%m-%d") if not pd.isna(f) else None

    def normalizar_ente_clave(self, etiqueta):
        if not etiqueta:
            return None
        val = str(etiqueta).strip().upper()
        if val in self.mapa_siglas:
            return self.mapa_siglas[val]
        return self.db.normalizar_ente_clave(val)

    # -------------------------------------------------------
    # Procesamiento principal
    # -------------------------------------------------------
    def procesar_archivos(self, archivos):
        print(f"📊 Procesando {len(archivos)} archivo(s) laborales...")
        entes_rfc = defaultdict(list)

        for f in archivos:
            nombre_archivo = getattr(f, "filename", getattr(f, "name", "archivo.xlsx"))
            print(f"📘 Leyendo archivo: {nombre_archivo}")
            xl = pd.ExcelFile(f)

            for hoja in xl.sheet_names:
                ente_label = hoja.strip().upper()
                clave_ente = self.normalizar_ente_clave(ente_label)
                if not clave_ente:
                    print(f"⚠️  {ente_label} omitido (no coincide con catálogo).")
                    continue

                df = xl.parse(hoja).rename(columns=lambda x: str(x).strip().upper().replace(" ", "_"))
                columnas_base = {"RFC", "NOMBRE", "PUESTO", "FECHA_ALTA", "FECHA_BAJA"}
                if not columnas_base.issubset(df.columns):
                    print(f"⚠️  {ente_label} omitido (faltan columnas base).")
                    continue

                qnas = [c for c in df.columns if re.match(r"^QNA([1-9]|1[0-2])$", c)]
                if not qnas:
                    print(f"⚠️  {ente_label} sin columnas quincenales válidas.")
                    continue

                for _, row in df.iterrows():
                    rfc = self.limpiar_rfc(row.get("RFC"))
                    if not rfc:
                        continue
                    entes_rfc[rfc].append({
                        "ente": clave_ente,
                        "nombre": str(row.get("NOMBRE", "")).strip(),
                        "puesto": str(row.get("PUESTO", "")).strip(),
                        "fecha_ingreso": self.limpiar_fecha(row.get("FECHA_ALTA")),
                        "fecha_egreso": self.limpiar_fecha(row.get("FECHA_BAJA")),
                        "qnas": {q: row.get(q) for q in qnas},
                        "monto": row.get("TOT_PERC"),
                    })

        resultados = self._cruces_quincenales(entes_rfc)
        print(f"📈 {len(resultados)} posibles duplicidades detectadas.")
        return resultados

    # -------------------------------------------------------
    # Cruces entre entes por quincenas
    # -------------------------------------------------------
    def _es_activo(self, valor):
        if pd.isna(valor):
            return False
        s = str(valor).strip().upper()
        return s not in {"", "0", "0.0", "NO", "N/A", "NA", "NONE"}

    def _cruces_quincenales(self, entes_rfc):
        hallazgos = []
        año_actual = datetime.now().year

        for rfc, registros in entes_rfc.items():
            if len(registros) < 2:
                continue

            qnas_presentes = sorted({q for r in registros for q, v in r["qnas"].items() if self._es_activo(v)})
            if not qnas_presentes:
                continue

            for qna in qnas_presentes:
                activos = [r for r in registros if self._es_activo(r["qnas"].get(qna))]
                entes_activos = sorted({r["ente"] for r in activos})
                if len(entes_activos) > 1:
                    hallazgos.append({
                        "rfc": rfc,
                        "nombre": activos[0].get("nombre", ""),
                        "entes": entes_activos,
                        "fecha_comun": f"{año_actual}Q{qna[-2:]}",
                        "tipo_patron": "CRUCE_ENTRE_ENTES_QNA",
                        "descripcion": f"Registros activos en la quincena {qna} en más de un ente.",
                        "registros": activos,
                        "estado": "Sin valoración",
                        "solventacion": ""
                    })
        return hallazgos

