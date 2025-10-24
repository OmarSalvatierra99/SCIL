# ===========================================================
# data_processor.py — SCIL QNA 2025 / Auditoría Laboral por Quincenas
# Versión integrada con claves ENTE_##### desde el catálogo oficial
# ===========================================================

import pandas as pd
import re
from datetime import datetime, date
from collections import defaultdict
from database import DatabaseManager


class DataProcessor:
    def __init__(self):
        self.column_cache = {}
        self.db = DatabaseManager("scil.db")
        self.mapa_siglas = self.db.get_mapa_siglas()  # {'CEAS': 'ENTE_49806', ...}

    # ----------------------------------------------------
    # LIMPIEZA / NORMALIZACIÓN
    # ----------------------------------------------------
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
        f = pd.to_datetime(s, errors="coerce", dayfirst=False)
        return f.strftime("%Y-%m-%d") if not pd.isna(f) else None

    def normalizar_ente_clave(self, etiqueta):
        """Convierte sigla/nombre/clave detectada en el Excel a ENTE_#####."""
        if not etiqueta:
            return None
        val = str(etiqueta).strip().upper()
        # Buscar en mapa de siglas
        if val in self.mapa_siglas:
            return self.mapa_siglas[val]
        # Buscar por nombre o clave directamente
        return self.db.normalizar_ente_clave(val, self.mapa_siglas)

    # ----------------------------------------------------
    # PROCESAMIENTO PRINCIPAL
    # ----------------------------------------------------
    def procesar_archivos(self, fileobjs, from_memory=False):
        """
        Procesa uno o varios archivos Excel directamente desde memoria (BytesIO).
        Cada hoja representa un ENTE.
        Analiza columnas RFC, NOMBRE, PUESTO, FECHA_ALTA, FECHA_BAJA, QNA1–QNA12, TOT_NETO.
        """
        print("📊 Procesando archivos laborales...")
        entes_rfc = defaultdict(list)

        for f in fileobjs:
            nombre_archivo = getattr(f, "name", "archivo_memoria.xlsx")
            print(f"🔹 Analizando {nombre_archivo}")

            xl = pd.ExcelFile(f)

            for sheet in xl.sheet_names:
                ente_label = sheet.strip().upper()  # El nombre de la hoja es el ENTE o sigla
                clave_ente = self.normalizar_ente_clave(ente_label)
                if not clave_ente:
                    print(f"⚠️  Hoja {ente_label} omitida (no coincide con ningún ente registrado).")
                    continue

                df = xl.parse(sheet).rename(columns=lambda x: str(x).strip().upper().replace(" ", "_"))

                columnas_necesarias = {"RFC", "NOMBRE", "PUESTO", "FECHA_ALTA", "FECHA_BAJA"}
                if not columnas_necesarias.issubset(df.columns):
                    print(f"⚠️  Hoja {ente_label} omitida (faltan columnas base).")
                    continue

                # Solo tomar QNA1–QNA12 (ignorar QNA12E u otras)
                qnas = [c for c in df.columns if re.match(r"^QNA([1-9]|1[0-2])$", c)]
                if not qnas:
                    print(f"⚠️  Hoja {ente_label} sin quincenas válidas.")
                    continue

                validos = 0
                for _, row in df.iterrows():
                    rfc = self.limpiar_rfc(row.get("RFC"))
                    if not rfc:
                        continue

                    entes_rfc[rfc].append({
                        "ente": clave_ente,  # ← usamos la CLAVE
                        "nombre": str(row.get("NOMBRE", "")).strip(),
                        "puesto": str(row.get("PUESTO", "")).strip(),
                        "fecha_ingreso": self.limpiar_fecha(row.get("FECHA_ALTA")),
                        "fecha_egreso": self.limpiar_fecha(row.get("FECHA_BAJA")),
                        "qnas": {q: row.get(q) for q in qnas},
                        "monto": row.get("TOT_NETO"),
                    })
                    validos += 1

                print(f"   → {ente_label} ({clave_ente}): {validos} registros válidos")

        resultados = self._cruces_quincenales(entes_rfc)
        print(f"📈 {len(resultados)} cruces detectados.")
        return resultados

    # ----------------------------------------------------
    # REGLAS AUDITORAS — CRUCES ENTRE ENTES POR QNA
    # ----------------------------------------------------
    def _es_activo(self, v):
        if pd.isna(v):
            return False
        s = str(v).strip().upper()
        return s not in {"", "0", "0.0", "NO", "N/A", "NA", "NONE"}

    def _cruces_quincenales(self, entes_rfc):
        hallazgos = []
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
                        "entes": entes_activos,  # ← todas CLAVES ENTE_#####
                        "fecha_comun": qna,
                        "tipo_patron": "CRUCE_ENTRE_ENTES_QNA",
                        "descripcion": f"El trabajador tiene registros activos en la quincena {qna} en más de un ente.",
                        "registros": activos
                    })
        return hallazgos

