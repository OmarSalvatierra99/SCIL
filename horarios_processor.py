# ========================================================
# horarios_processor.py - Auditoría de cruces de horario
# Enfoque auditor (OFS Tlaxcala)
# ========================================================

import pandas as pd
from collections import defaultdict
import re
from datetime import datetime, time, date

class HorariosProcessor:
    def __init__(self):
        self.column_cache = {}

    # ----------------------------------------------------
    # Limpieza y normalización
    # ----------------------------------------------------
    def limpiar_rfc(self, rfc):
        if pd.isna(rfc):
            return None
        rfc = str(rfc).strip().upper()
        rfc = re.sub(r'[^A-Z0-9]', '', rfc)
        return rfc if 10 <= len(rfc) <= 13 else None

    def limpiar_fecha(self, fecha):
        if pd.isna(fecha):
            return None
        if isinstance(fecha, datetime):
            return fecha.strftime('%Y-%m-%d')
        s = str(fecha).strip()
        if not s or s.lower() in ['nan', 'nat', 'none', 'null']:
            return None
        try:
            f = pd.to_datetime(s, errors='coerce', dayfirst=True)
            return f.strftime('%Y-%m-%d') if not pd.isna(f) else None
        except:
            return None

    def limpiar_hora(self, valor):
        if pd.isna(valor):
            return None
        s = str(valor).strip()
        if not s:
            return None
        try:
            if isinstance(valor, datetime):
                return valor.strftime('%H:%M')
            if ':' in s:
                h, m = s.split(':')[:2]
                return f"{int(h):02d}:{int(m):02d}"
            if len(s) == 4:  # ej. 730 -> 07:30
                return f"{s[:2]}:{s[2:]}"
        except:
            return None
        return None

    def _to_time(self, s):
        if not s:
            return None
        try:
            h, m = map(int, s.split(':'))
            return time(h, m)
        except:
            return None

    def extraer_ente(self, hoja):
        return str(hoja).split('_')[0]

    # ----------------------------------------------------
    # Detección de columnas
    # ----------------------------------------------------
    def detectar_columnas(self, df, ente):
        cols = df.columns.astype(str)
        cache_key = f"{ente}_{hash(str(cols.tolist()))}"
        if cache_key in self.column_cache:
            return self.column_cache[cache_key]

        rfc_col = next((c for c in cols if 'RFC' in c.upper()), None)
        nombre_col = next((c for c in cols if 'NOMBRE' in c.upper()), None)
        f_ing_col = next((c for c in cols if 'INGRESO' in c.upper()), None)
        f_egr_col = next((c for c in cols if 'EGRESO' in c.upper()), None)
        dia_col = next((c for c in cols if 'DIA' in c.upper()), None)
        h_ent_col = next((c for c in cols if 'ENTRADA' in c.upper()), None)
        h_sal_col = next((c for c in cols if 'SALIDA' in c.upper()), None)
        plantel_col = next((c for c in cols if 'PLANTEL' in c.upper()), None)

        out = (rfc_col, nombre_col, f_ing_col, f_egr_col,
               dia_col, h_ent_col, h_sal_col, plantel_col)
        self.column_cache[cache_key] = out
        return out

    # ----------------------------------------------------
    # Procesamiento principal
    # ----------------------------------------------------
    def procesar_archivo(self, filepath):
        xl = pd.ExcelFile(filepath)
        maestros = defaultdict(list)
        entes_detectados = set()
        print("📊 Iniciando procesamiento de horarios...")

        for hoja in xl.sheet_names:
            ente = self.extraer_ente(hoja)
            entes_detectados.add(ente)
            df = xl.parse(hoja)
            rfc_col, nombre_col, f_ing, f_egr, dia, h_ent, h_sal, plantel = self.detectar_columnas(df, ente)

            if not rfc_col:
                continue

            for _, row in df.iterrows():
                rfc = self.limpiar_rfc(row.get(rfc_col))
                if not rfc:
                    continue

                registro = {
                    'ente': ente,
                    'hoja': hoja,
                    'rfc_original': str(row.get(rfc_col, '')),
                    'nombre': str(row.get(nombre_col, '') or ''),
                    'fecha_ingreso': self.limpiar_fecha(row.get(f_ing)) if f_ing else None,
                    'fecha_egreso': self.limpiar_fecha(row.get(f_egr)) if f_egr else None,
                    'dia_semana': str(row.get(dia, '')).strip().capitalize() if dia else '',
                    'hora_entrada': self.limpiar_hora(row.get(h_ent)) if h_ent else None,
                    'hora_salida': self.limpiar_hora(row.get(h_sal)) if h_sal else None,
                    'plantel': str(row.get(plantel, '') or '')
                }
                maestros[rfc].append(registro)

        print(f"🎯 Maestros únicos: {len(maestros)} | Entes: {len(entes_detectados)}")

        resultados = []
        for rfc, registros in maestros.items():
            entes_rfc = {r['ente'] for r in registros}

            # Reglas auditoras
            resultados.extend(self._validar_incoherencias(rfc, registros))
            resultados.extend(self._solape_mismo_ente(rfc, registros))
            if len(entes_rfc) > 1:
                resultados.extend(self._solape_entre_entes(rfc, registros))
            activos = [r for r in registros if not r.get('fecha_egreso')]
            if activos:
                resultados.append({
                    'rfc': rfc,
                    'registros': activos,
                    'total_entes': len(entes_rfc),
                    'entes': list(entes_rfc),
                    'fecha_comun': 'SIN_FECHA_EGRESO',
                    'tipo_patron': 'RELACION_ACTIVA_SIN_EGRESO',
                    'severidad': 2,
                    'descripcion': 'El docente mantiene relación activa sin fecha de egreso'
                })

        resultados.sort(key=lambda x: x['severidad'], reverse=True)
        print(f"📈 Procesamiento completado con {len(resultados)} hallazgos.")
        return resultados

    # ----------------------------------------------------
    # Reglas auditoras
    # ----------------------------------------------------
    def _validar_incoherencias(self, rfc, registros):
        hallazgos = []
        for r in registros:
            h_in = self._to_time(r.get('hora_entrada'))
            h_out = self._to_time(r.get('hora_salida'))
            if not r.get('dia_semana') or not h_in or not h_out:
                hallazgos.append({
                    'rfc': rfc,
                    'registros': [r],
                    'total_entes': 1,
                    'entes': [r['ente']],
                    'fecha_comun': 'FALTANTE_DE_HORARIO',
                    'tipo_patron': 'HORARIO_FALTANTE',
                    'severidad': 3,
                    'descripcion': 'Registro con día u horas incompletas'
                })
                continue
            if h_out < h_in:
                hallazgos.append({
                    'rfc': rfc,
                    'registros': [r],
                    'total_entes': 1,
                    'entes': [r['ente']],
                    'fecha_comun': f"{r['hora_entrada']}→{r['hora_salida']}",
                    'tipo_patron': 'HORARIO_INCOHERENTE',
                    'severidad': 5,
                    'descripcion': 'Hora de salida anterior a la de entrada'
                })
        return hallazgos

    def _solape_mismo_ente(self, rfc, registros):
        hallazgos = []
        por_ente_dia = defaultdict(list)
        for r in registros:
            if r.get('hora_entrada') and r.get('hora_salida') and r.get('dia_semana'):
                por_ente_dia[(r['ente'], r['dia_semana'])].append(r)

        for key, lista in por_ente_dia.items():
            if len(lista) < 2:
                continue
            solapados = self._buscar_solapes(lista)
            if solapados:
                hallazgos.append({
                    'rfc': rfc,
                    'registros': solapados,
                    'total_entes': 1,
                    'entes': [key[0]],
                    'fecha_comun': key[1],
                    'tipo_patron': 'SOLAPE_HORARIO_MISMO_ENTE',
                    'severidad': 4,
                    'descripcion': f'Solapamiento de horarios en el mismo ente el {key[1]}'
                })
        return hallazgos

    def _solape_entre_entes(self, rfc, registros):
        hallazgos = []
        por_dia = defaultdict(list)
        for r in registros:
            if r.get('hora_entrada') and r.get('hora_salida') and r.get('dia_semana'):
                por_dia[r['dia_semana']].append(r)

        for dia, lista in por_dia.items():
            entes = {r['ente'] for r in lista}
            if len(entes) < 2:
                continue
            solapados = self._buscar_solapes(lista)
            if solapados:
                hallazgos.append({
                    'rfc': rfc,
                    'registros': solapados,
                    'total_entes': len(entes),
                    'entes': list(entes),
                    'fecha_comun': dia,
                    'tipo_patron': 'SOLAPE_HORARIO_ENTRE_ENTES',
                    'severidad': 5,
                    'descripcion': f'Solapamiento de horarios entre entes el {dia}'
                })
        return hallazgos

    def _buscar_solapes(self, registros):
        result = []
        times = []
        for r in registros:
            start = self._to_time(r.get('hora_entrada'))
            end = self._to_time(r.get('hora_salida'))
            if not start or not end:
                continue
            times.append((start, end, r))
        for i in range(len(times)):
            s1, e1, r1 = times[i]
            for j in range(i + 1, len(times)):
                s2, e2, r2 = times[j]
                if (s1 <= e2) and (s2 <= e1):  # solape inclusivo
                    result.extend([r1, r2])
        # quitar duplicados
        uniq = []
        seen = set()
        for r in result:
            key = (r['ente'], r['dia_semana'], r['hora_entrada'], r['hora_salida'])
            if key not in seen:
                uniq.append(r)
                seen.add(key)
        return uniq

