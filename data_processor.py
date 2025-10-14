# =========================================================
# data_processor.py — SCIL / Auditoría de relaciones laborales
# Revisión 2025: lenguaje auditor claro (“cruce”, no “solape”)
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
        rfc_s = re.sub(r'[^A-Z0-9]', '', rfc_s)
        return rfc_s if 10 <= len(rfc_s) <= 13 else None

    def limpiar_fecha(self, fecha):
        if pd.isna(fecha):
            return None
        if isinstance(fecha, datetime):
            return fecha.strftime('%Y-%m-%d')
        if isinstance(fecha, date):
            return fecha.strftime('%Y-%m-%d')

        s = str(fecha).strip()
        if not s or s.lower() in ['nan', 'nat', 'none', 'null']:
            return None
        try:
            if isinstance(fecha, (int, float)):
                f = pd.to_datetime(fecha, unit='D', origin='1899-12-30')
                return f.strftime('%Y-%m-%d')
            f = pd.to_datetime(s, errors='coerce', dayfirst=True)
            return f.strftime('%Y-%m-%d') if not pd.isna(f) else None
        except:
            return None

    def _to_date(self, ymd):
        if not ymd:
            return None
        try:
            return datetime.strptime(ymd, '%Y-%m-%d').date()
        except:
            return None

    # ----------------------------------------------------
    # DETECCIÓN DE COLUMNAS
    # ----------------------------------------------------
    def extraer_ente_de_nombre_hoja(self, sheet_name):
        partes = str(sheet_name).split('_')
        return partes[0] if partes else str(sheet_name)

    def detectar_columnas(self, df, ente):
        cache_key = f"{ente}_{hash(str(df.columns.tolist()))}"
        if cache_key in self.column_cache:
            return self.column_cache[cache_key]

        cols = df.columns.astype(str)
        rfc_col = next((c for c in cols if 'RFC' in c.upper()), None)
        nombre_col = next((c for c in cols if 'NOMBRE' in c.upper()), None)
        puesto_col = next((c for c in cols if 'PUESTO' in c.upper()), None)
        f_ing = next((c for c in cols if 'INGRESO' in c.upper() and 'FECHA' in c.upper()), None)
        f_egr = next((c for c in cols if any(x in c.upper() for x in ['EGRESO','BAJA','SALIDA']) and 'FECHA' in c.upper()), None)
        out = (rfc_col, nombre_col, puesto_col, f_ing, f_egr)
        self.column_cache[cache_key] = out
        return out

    # ----------------------------------------------------
    # PROCESAMIENTO PRINCIPAL
    # ----------------------------------------------------
    def procesar_archivo(self, filepath, with_structure=False):
        xl = pd.ExcelFile(filepath)
        entes_rfc = defaultdict(list)
        entes_detectados = set()
        estructura = []

        print("📊 Iniciando procesamiento laboral...")

        for sheet in xl.sheet_names:
            ente = self.extraer_ente_de_nombre_hoja(sheet)
            entes_detectados.add(ente)
            df = xl.parse(sheet)
            rfc_col, nombre_col, puesto_col, f_ing, f_egr = self.detectar_columnas(df, ente)

            if with_structure:
                estructura.append({
                    'hoja': sheet, 'ente': ente, 'total_filas': len(df),
                    'rfc_col': rfc_col, 'fecha_ingreso_col': f_ing, 'fecha_egreso_col': f_egr
                })

            if not rfc_col:
                continue

            for _, row in df.iterrows():
                rfc = self.limpiar_rfc(row.get(rfc_col))
                if not rfc:
                    continue
                fi = self.limpiar_fecha(row.get(f_ing)) if f_ing else None
                fe = self.limpiar_fecha(row.get(f_egr)) if f_egr else None

                entes_rfc[rfc].append({
                    'ente': ente,
                    'hoja': sheet,
                    'nombre': str(row.get(nombre_col, '') or ''),
                    'puesto': str(row.get(puesto_col, '') or ''),
                    'fecha_ingreso': fi,
                    'fecha_egreso': fe,
                    'rfc_original': str(row.get(rfc_col, ''))
                })

        resultados = []
        for rfc, registros in entes_rfc.items():
            entes_del_rfc = sorted({r['ente'] for r in registros})
            resultados.extend(self._incoherencias_basicas(registros))
            resultados.extend(self._cruces_mismo_ente(registros, entes_del_rfc))
            resultados.extend(self._cruces_entre_entes(registros, entes_del_rfc))
            activos = [r for r in registros if r.get('fecha_egreso') is None]
            if activos:
                resultados.append({
                    'rfc': registros[0]['rfc_original'],
                    'nombre': registros[0].get('nombre',''),
                    'registros': activos,
                    'total_entes': len({r['ente'] for r in activos}),
                    'entes': list({r['ente'] for r in activos}),
                    'fecha_comun': 'RELACIÓN ACTIVA',
                    'tipo_patron': 'RELACION_ACTIVA',
                    'descripcion': 'El trabajador mantiene una relación activa sin fecha de egreso registrada.'
                })

        resultados.sort(key=lambda x: x.get('tipo_patron',''))
        print(f"📈 {len(resultados)} hallazgos laborales generados.")
        return (resultados, estructura) if with_structure else resultados

    # ----------------------------------------------------
    # REGLAS AUDITORAS
    # ----------------------------------------------------
    def _incoherencias_basicas(self, registros):
        hallazgos = []
        for r in registros:
            fi, fe = self._to_date(r.get('fecha_ingreso')), self._to_date(r.get('fecha_egreso'))
            if fi and fe and fe < fi:
                hallazgos.append({
                    'rfc': r['rfc_original'],
                    'nombre': r.get('nombre',''),
                    'registros': [r],
                    'entes': [r['ente']],
                    'fecha_comun': f"{r['fecha_ingreso']}→{r['fecha_egreso']}",
                    'tipo_patron': 'FECHAS_INVERTIDAS',
                    'descripcion': 'La fecha de egreso es anterior a la de ingreso.'
                })
        return hallazgos

    def _cruces_mismo_ente(self, registros, entes_del_rfc):
        hallazgos = []
        por_ente = defaultdict(list)
        for r in registros:
            por_ente[r['ente']].append(r)

        for ente, lista in por_ente.items():
            # Duplicados exactos
            pares = defaultdict(list)
            for r in lista:
                key = (r.get('fecha_ingreso'), r.get('fecha_egreso'))
                pares[key].append(r)
            for pair, items in pares.items():
                if len(items) > 1:
                    hallazgos.append({
                        'rfc': items[0]['rfc_original'],
                        'nombre': items[0].get('nombre',''),
                        'registros': items,
                        'entes': [ente],
                        'fecha_comun': f"{pair[0]}→{pair[1]}",
                        'tipo_patron': 'REGISTRO_DUPLICADO',
                        'descripcion': 'Registros duplicados dentro del mismo ente.'
                    })

            # Cruces internos
            periods = []
            for r in lista:
                fi, fe = self._to_date(r.get('fecha_ingreso')), self._to_date(r.get('fecha_egreso'))
                if not fi and not fe:
                    continue
                start = fi or self._to_date(r.get('fecha_egreso'))
                end = fe or date.max
                if not start:
                    start = end
                periods.append((start, end, r))

            overlapping = set()
            for i in range(len(periods)):
                a_s, a_e, a_r = periods[i]
                for j in range(i+1, len(periods)):
                    b_s, b_e, b_r = periods[j]
                    if (a_s <= b_e) and (b_s <= a_e):
                        overlapping.update([i, j])

            if overlapping:
                regs = [periods[i][2] for i in sorted(overlapping)]
                hallazgos.append({
                    'rfc': regs[0]['rfc_original'],
                    'nombre': regs[0].get('nombre',''),
                    'registros': regs,
                    'entes': [ente],
                    'fecha_comun': f"{min([self._to_date(r.get('fecha_ingreso')) for r in regs if r.get('fecha_ingreso')])}→{max([self._to_date(r.get('fecha_egreso')) or date.max for r in regs])}",
                    'tipo_patron': 'CRUCE_INTERNO',
                    'descripcion': 'Cruce de periodos dentro del mismo ente.'
                })
        return hallazgos

    def _cruces_entre_entes(self, registros, entes_del_rfc):
        hallazgos = []
        por_ente = defaultdict(list)
        for r in registros:
            por_ente[r['ente']].append(r)
        entes = list(por_ente.keys())
        if len(entes) < 2:
            return []

        overlapping = []
        overlapping_entes = set()
        for i in range(len(entes)):
            for j in range(i+1, len(entes)):
                a, b = entes[i], entes[j]
                for r1 in por_ente[a]:
                    for r2 in por_ente[b]:
                        f1i, f1e = self._to_date(r1.get('fecha_ingreso')), self._to_date(r1.get('fecha_egreso'))
                        f2i, f2e = self._to_date(r2.get('fecha_ingreso')), self._to_date(r2.get('fecha_egreso'))
                        if not f1i and not f1e or not f2i and not f2e:
                            continue
                        s1, e1 = f1i or f1e, f1e or date.max
                        s2, e2 = f2i or f2e, f2e or date.max
                        if (s1 <= e2) and (s2 <= e1):
                            overlapping.extend([r1, r2])
                            overlapping_entes.update([a,b])

        if overlapping:
            seen = set()
            uniq = []
            for r in overlapping:
                key = (r['ente'], r['fecha_ingreso'], r['fecha_egreso'])
                if key not in seen:
                    uniq.append(r); seen.add(key)
            hallazgos.append({
                'rfc': uniq[0]['rfc_original'],
                'nombre': uniq[0].get('nombre',''),
                'registros': uniq,
                'entes': sorted(list(overlapping_entes)),
                'fecha_comun': 'CRUCE_ENTRE_ENTES',
                'tipo_patron': 'CRUCE_ENTRE_ENTES',
                'descripcion': 'Cruce de periodos laborales entre diferentes entes.'
            })
        return hallazgos

