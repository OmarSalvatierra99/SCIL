# ===========================================================
# horarios_processor.py — SCIL / Auditoría de Cruces de Horarios
# Revisión 2025: lenguaje uniforme y descripciones claras
# ===========================================================

import pandas as pd
from collections import defaultdict
import re
from datetime import datetime, time

class HorariosProcessor:
    def __init__(self):
        self.column_cache = {}

    # -------------------------------------------------------
    # LIMPIEZA
    # -------------------------------------------------------
    def limpiar_rfc(self, rfc):
        if pd.isna(rfc):
            return None
        rfc_s = str(rfc).strip().upper()
        rfc_s = re.sub(r'[^A-Z0-9]', '', rfc_s)
        return rfc_s if 10 <= len(rfc_s) <= 13 else None

    def limpiar_hora(self, valor):
        if pd.isna(valor):
            return None
        if isinstance(valor, time):
            return valor.strftime('%H:%M')
        if isinstance(valor, datetime):
            return valor.strftime('%H:%M')
        s = str(valor).strip()
        if not s:
            return None
        try:
            h = pd.to_datetime(s, errors='coerce').time()
            return h.strftime('%H:%M') if h else None
        except:
            return None

    def limpiar_fecha(self, valor):
        if pd.isna(valor):
            return None
        try:
            f = pd.to_datetime(valor, errors='coerce', dayfirst=True)
            return f.strftime('%Y-%m-%d') if not pd.isna(f) else None
        except:
            return None

    def _to_minutes(self, hora):
        if not hora:
            return None
        try:
            h, m = map(int, hora.split(':'))
            return h * 60 + m
        except:
            return None

    # -------------------------------------------------------
    # PROCESAMIENTO PRINCIPAL
    # -------------------------------------------------------
    def procesar_archivo(self, filepath, with_structure=False):
        xl = pd.ExcelFile(filepath)
        registros_por_rfc = defaultdict(list)
        estructura = []
        print("⏰ Iniciando análisis de cruces de horarios...")

        for sheet in xl.sheet_names:
            df = xl.parse(sheet)
            ente = str(sheet).strip()
            cols = df.columns.astype(str)

            rfc_col = next((c for c in cols if 'RFC' in c.upper()), None)
            nombre_col = next((c for c in cols if 'NOMBRE' in c.upper()), None)
            dia_col = next((c for c in cols if 'DIA' in c.upper()), None)
            h_entrada = next((c for c in cols if 'ENTRADA' in c.upper()), None)
            h_salida = next((c for c in cols if 'SALIDA' in c.upper()), None)
            plantel_col = next((c for c in cols if 'PLANTEL' in c.upper() or 'CENTRO' in c.upper()), None)
            f_ing = next((c for c in cols if 'INGRESO' in c.upper()), None)
            f_egr = next((c for c in cols if 'EGRESO' in c.upper() or 'BAJA' in c.upper()), None)

            if with_structure:
                estructura.append({
                    'hoja': sheet, 'ente': ente, 'total_filas': len(df),
                    'rfc_col': rfc_col, 'entrada_col': h_entrada, 'salida_col': h_salida
                })

            if not rfc_col or not h_entrada or not h_salida:
                continue

            for _, row in df.iterrows():
                rfc = self.limpiar_rfc(row.get(rfc_col))
                if not rfc:
                    continue
                registro = {
                    'ente': ente,
                    'plantel': str(row.get(plantel_col, '') or ''),
                    'nombre': str(row.get(nombre_col, '') or ''),
                    'dia_semana': str(row.get(dia_col, '') or ''),
                    'hora_entrada': self.limpiar_hora(row.get(h_entrada)),
                    'hora_salida': self.limpiar_hora(row.get(h_salida)),
                    'fecha_ingreso': self.limpiar_fecha(row.get(f_ing)),
                    'fecha_egreso': self.limpiar_fecha(row.get(f_egr)),
                    'rfc_original': rfc
                }
                registros_por_rfc[rfc].append(registro)

        resultados = []
        for rfc, registros in registros_por_rfc.items():
            resultados.extend(self._cruces_internos(registros))
            resultados.extend(self._cruces_externos(registros))

        print(f"📈 {len(resultados)} cruces de horario detectados.")
        return (resultados, estructura) if with_structure else resultados

    # -------------------------------------------------------
    # REGLAS AUDITORAS
    # -------------------------------------------------------
    def _cruces_internos(self, registros):
        hallazgos = []
        por_ente = defaultdict(list)
        for r in registros:
            por_ente[r['ente']].append(r)

        for ente, lista in por_ente.items():
            cruces = []
            for i in range(len(lista)):
                a = lista[i]
                for j in range(i + 1, len(lista)):
                    b = lista[j]
                    if a.get('dia_semana') != b.get('dia_semana'):
                        continue
                    a_i, a_o = self._to_minutes(a.get('hora_entrada')), self._to_minutes(a.get('hora_salida'))
                    b_i, b_o = self._to_minutes(b.get('hora_entrada')), self._to_minutes(b.get('hora_salida'))
                    if not all([a_i, a_o, b_i, b_o]):
                        continue
                    if (a_i <= b_o) and (b_i <= a_o):
                        cruces.extend([a, b])

            if cruces:
                unicos = {tuple(r.items()): r for r in cruces}.values()
                hallazgos.append({
                    'rfc': list(unicos)[0]['rfc_original'],
                    'nombre': list(unicos)[0].get('nombre', ''),
                    'registros': list(unicos),
                    'entes': [ente],
                    'fecha_comun': f"Cruce interno en {ente}",
                    'tipo_patron': 'CRUCE_INTERNO',
                    'descripcion': 'Cruce de horario detectado dentro del mismo ente o plantel.'
                })
        return hallazgos

    def _cruces_externos(self, registros):
        hallazgos = []
        por_dia = defaultdict(list)
        for r in registros:
            if r.get('dia_semana'):
                por_dia[r['dia_semana']].append(r)

        for dia, lista in por_dia.items():
            for i in range(len(lista)):
                a = lista[i]
                for j in range(i + 1, len(lista)):
                    b = lista[j]
                    if a['ente'] == b['ente']:
                        continue
                    a_i, a_o = self._to_minutes(a.get('hora_entrada')), self._to_minutes(a.get('hora_salida'))
                    b_i, b_o = self._to_minutes(b.get('hora_entrada')), self._to_minutes(b.get('hora_salida'))
                    if not all([a_i, a_o, b_i, b_o]):
                        continue
                    if (a_i <= b_o) and (b_i <= a_o):
                        hallazgos.append({
                            'rfc': a['rfc_original'],
                            'nombre': a.get('nombre', ''),
                            'registros': [a, b],
                            'entes': [a['ente'], b['ente']],
                            'fecha_comun': dia,
                            'tipo_patron': 'CRUCE_ENTRE_ENTES',
                            'descripcion': f"Cruce de horario entre entes detectado el día {dia}."
                        })
        return hallazgos

