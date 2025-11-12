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
    """
    Procesador de archivos Excel laborales.

    Funcionalidad principal:
    - Lee archivos Excel con datos de empleados por ente público
    - Detecta empleados activos en múltiples entes en la misma quincena
    - Genera registros de cruces (duplicaciones) y empleados únicos
    """

    def __init__(self):
        self.db = DatabaseManager("scil.db")
        self.mapa_siglas = self.db.get_mapa_siglas()
        self.mapa_inverso = self.db.get_mapa_claves_inverso()

    # -------------------------------------------------------
    # Limpieza y normalización
    # -------------------------------------------------------
    def limpiar_rfc(self, rfc):
        """Valida y limpia RFC mexicano (10-13 caracteres alfanuméricos)."""
        if pd.isna(rfc):
            return None
        s = re.sub(r"[^A-Z0-9]", "", str(rfc).strip().upper())
        return s if 10 <= len(s) <= 13 else None

    def limpiar_fecha(self, fecha):
        """Convierte fechas de Excel a formato ISO (YYYY-MM-DD)."""
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
        """
        Convierte etiqueta de ente (sigla, nombre o clave) a CLAVE única.
        Usa cache de mapas para optimizar búsquedas repetidas.
        """
        if not etiqueta:
            return None
        val = str(etiqueta).strip().upper()
        # Intenta primero con cache rápido
        if val in self.mapa_siglas:
            return self.mapa_siglas[val]
        # Fallback a búsqueda en base de datos
        return self.db.normalizar_ente_clave(val)

    # -------------------------------------------------------
    # Procesamiento principal
    # -------------------------------------------------------
    def procesar_archivos(self, archivos):
        """
        Procesa uno o más archivos Excel con datos laborales.

        Formato esperado:
        - Cada hoja representa un ente público
        - Columnas requeridas: RFC, NOMBRE, PUESTO, FECHA_ALTA, FECHA_BAJA
        - Columnas opcionales: QNA1-QNA24 (indicadores de actividad quincenal)

        Retorna tupla: (resultados, alertas)
        - resultados: lista de registros con empleados y sus cruces detectados
        - alertas: lista de advertencias sobre entes no encontrados o errores
        """
        print(f"📊 Procesando {len(archivos)} archivo(s) laborales...")
        entes_rfc = defaultdict(list)  # {RFC: [registros por ente]}
        alertas = []  # Lista de alertas para el usuario

        for f in archivos:
            nombre_archivo = getattr(f, "filename", getattr(f, "name", "archivo.xlsx"))
            print(f"📘 Leyendo archivo: {nombre_archivo}")
            xl = pd.ExcelFile(f)

            for hoja in xl.sheet_names:
                ente_label = hoja.strip().upper()
                clave_ente = self.normalizar_ente_clave(ente_label)

                if not clave_ente:
                    alerta = f"⚠️ Hoja '{hoja}' no encontrada en catálogo de entes. Verifique el nombre."
                    print(alerta)
                    alertas.append({
                        "tipo": "ente_no_encontrado",
                        "mensaje": alerta,
                        "hoja": hoja,
                        "archivo": nombre_archivo
                    })
                    continue

                df = xl.parse(hoja).rename(columns=lambda x: str(x).strip().upper().replace(" ", "_"))
                columnas_base = {"RFC", "NOMBRE", "PUESTO", "FECHA_ALTA", "FECHA_BAJA"}
                if not columnas_base.issubset(df.columns):
                    alerta = f"⚠️ Hoja '{hoja}' omitida: faltan columnas requeridas (RFC, NOMBRE, PUESTO, FECHA_ALTA, FECHA_BAJA)."
                    print(alerta)
                    alertas.append({
                        "tipo": "columnas_faltantes",
                        "mensaje": alerta,
                        "hoja": hoja,
                        "archivo": nombre_archivo
                    })
                    continue

                # Acepta QNA1–QNA24
                qnas = [c for c in df.columns if re.match(r"^QNA([1-9]|1[0-9]|2[0-4])$", c)]
                registros_validos = 0

                for _, row in df.iterrows():
                    rfc = self.limpiar_rfc(row.get("RFC"))
                    if not rfc:
                        continue

                    # Solo guardar quincenas activas (no vacías, no 0, no NA)
                    qnas_activas = {q: row.get(q) for q in qnas if self._es_activo(row.get(q))}

                    entes_rfc[rfc].append({
                        "ente": clave_ente,
                        "nombre": str(row.get("NOMBRE", "")).strip(),
                        "puesto": str(row.get("PUESTO", "")).strip(),
                        "fecha_ingreso": self.limpiar_fecha(row.get("FECHA_ALTA")),
                        "fecha_egreso": self.limpiar_fecha(row.get("FECHA_BAJA")),
                        "qnas": qnas_activas,
                        "monto": row.get("TOT_PERC"),
                    })
                    registros_validos += 1

                print(f"✅ Hoja '{hoja}': {registros_validos} registros procesados.")

        # Siempre genera registros de empleados (aunque no haya cruces)
        resultados = self._cruces_quincenales(entes_rfc)
        sin_cruce = self._empleados_sin_cruce(entes_rfc, resultados)
        resultados.extend(sin_cruce)

        print(f"📈 {len(resultados)} registros totales (incluye no duplicados).")
        return resultados, alertas

    # -------------------------------------------------------
    # Empleados sin cruce
    # -------------------------------------------------------
    def _empleados_sin_cruce(self, entes_rfc, hallazgos):
        """Agrega RFC sin duplicidad para trazabilidad."""
        hallados = {h["rfc"] for h in hallazgos}
        faltantes = []
        for rfc, registros in entes_rfc.items():
            if rfc in hallados:
                continue
            faltantes.append({
                "rfc": rfc,
                "nombre": registros[0].get("nombre", ""),
                "entes": sorted({r["ente"] for r in registros}),
                "tipo_patron": "SIN_DUPLICIDAD",
                "descripcion": "Empleado sin cruce detectado",
                "registros": registros,
                "estado": "Sin valoración",
                "solventacion": ""
            })
        return faltantes

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

            qnas_presentes = sorted({
                q for r in registros for q, v in r["qnas"].items() if self._es_activo(v)
            })
            if not qnas_presentes:
                continue

            for qna in qnas_presentes:
                activos = [r for r in registros if self._es_activo(r["qnas"].get(qna))]
                entes_activos = sorted({r["ente"] for r in activos})
                if len(entes_activos) > 1:
                    num = int(re.sub(r"\D", "", qna))
                    hallazgos.append({
                        "rfc": rfc,
                        "nombre": activos[0].get("nombre", ""),
                        "entes": entes_activos,
                        "fecha_comun": f"{año_actual}Q{num:02d}",
                        "tipo_patron": "CRUCE_ENTRE_ENTES_QNA",
                        "descripcion": f"Activo en más de un ente en la quincena {qna}.",
                        "registros": activos,
                        "estado": "Sin valoración",
                        "solventacion": ""
                    })
        return hallazgos

