# ========================================================
# data_processor.py - SCIL / Auditoría de relaciones laborales
# Enfoque auditor:
#  - No puede haber dos relaciones ACTIVAS a la vez en entes distintos.
#  - No puede haber dos periodos solapados en el MISMO ente (ni duplicados).
#  - Egreso < Ingreso es incoherencia grave.
#  - Si falta FECHA_EGRESO => relación ACTIVA (debe notificarse).
#  - Si hay reingresos al mismo ente, sólo son válidos si NO se solapan.
# Salida compatible con templates actuales.
# ========================================================

import pandas as pd
from collections import defaultdict, Counter
import re
from datetime import datetime, date

class DataProcessor:
    def __init__(self):
        self.column_cache = {}

    # ----------------------------------------------------
    # LIMPIEZA / NORMALIZACIÓN
    # ----------------------------------------------------
    def limpiar_rfc(self, rfc):
        """Limpia y estandariza un RFC (10-13 caracteres alfanum)."""
        if pd.isna(rfc):
            return None
        rfc_s = str(rfc).strip().upper()
        rfc_s = re.sub(r'[^A-Z0-9]', '', rfc_s)
        return rfc_s if 10 <= len(rfc_s) <= 13 else None

    def limpiar_fecha(self, fecha):
        """Convierte fecha a 'YYYY-MM-DD'. Si no se puede, retorna None."""
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
            # Serial de Excel
            if isinstance(fecha, (int, float)):
                f = pd.to_datetime(fecha, unit='D', origin='1899-12-30')
                return f.strftime('%Y-%m-%d')
            f = pd.to_datetime(s, errors='coerce', dayfirst=True)
            return f.strftime('%Y-%m-%d') if not pd.isna(f) else None
        except:
            return None

    def _to_date(self, ymd):
        """Convierte 'YYYY-MM-DD' a date. None -> None."""
        if not ymd:
            return None
        try:
            return datetime.strptime(ymd, '%Y-%m-%d').date()
        except:
            return None

    # ----------------------------------------------------
    # ENTES / COLUMNAS
    # ----------------------------------------------------
    def extraer_ente_de_nombre_hoja(self, sheet_name):
        """Prefijo previo al '_' se toma como ente."""
        partes = str(sheet_name).split('_')
        return partes[0] if partes else str(sheet_name)

    def detectar_columnas(self, df, ente):
        """
        Detecta columnas clave:
        - RFC
        - NOMBRE
        - PUESTO
        - FECHA_INGRESO
        - FECHA_EGRESO
        """
        cache_key = f"{ente}_{hash(str(df.columns.tolist()))}"
        if cache_key in self.column_cache:
            return self.column_cache[cache_key]

        cols = df.columns.astype(str)
        rfc_col = next((c for c in cols if 'RFC' in c.upper()), None)
        nombre_col = next((c for c in cols if 'NOMBRE' in c.upper()), None)
        puesto_col = next((c for c in cols if 'PUESTO' in c.upper()), None)

        fecha_ingreso_col = next(
            (c for c in cols
             if any(k in c.upper() for k in ['FECHA', 'FCHA'])
             and any(k in c.upper() for k in ['INGRESO', 'ING'])),
            None
        )
        fecha_egreso_col = next(
            (c for c in cols
             if any(k in c.upper() for k in ['FECHA', 'FCHA'])
             and any(k in c.upper() for k in ['EGRESO', 'EGR', 'BAJA', 'SALIDA'])),
            None
        )

        out = (rfc_col, nombre_col, puesto_col, fecha_ingreso_col, fecha_egreso_col)
        self.column_cache[cache_key] = out
        return out

    # ----------------------------------------------------
    # PROCESAMIENTO PRINCIPAL
    # ----------------------------------------------------
    def procesar_archivo(self, filepath, with_structure=False):
        """
        Lee el Excel completo y devuelve:
        - resultados: lista de hallazgos (patrones/incoherencias)
        - estructura (opcional): resumen por hoja/ENTE
        Reglas auditor:
          * SOLAPE_ENTRE_ENTES (sev 5)
          * SOLAPE_MISMO_ENTE (sev 5)
          * DUPLICADO_MISMO_ENTE (sev 4)
          * EGRESO_ANTES_INGRESO (sev 5)
          * RELACION_ACTIVA_SIN_EGRESO (sev 3)
        """
        xl = pd.ExcelFile(filepath)
        entes_rfc = defaultdict(list)   # rfc -> [registros]
        entes_detectados = set()
        estructura = []

        print("📊 Iniciando procesamiento (modo auditor)...")

        for sheet in xl.sheet_names:
            ente = self.extraer_ente_de_nombre_hoja(sheet)
            entes_detectados.add(ente)
            df = xl.parse(sheet)
            rfc_col, nombre_col, puesto_col, f_ing_col, f_egr_col = self.detectar_columnas(df, ente)

            print(f"  🔎 Hoja: {sheet} | Ente: {ente} | RFC: {rfc_col} | Ing: {f_ing_col} | Egr: {f_egr_col}")

            if with_structure:
                estructura.append({
                    'hoja': sheet,
                    'ente': ente,
                    'total_filas': len(df),
                    'columnas': list(map(str, df.columns)),
                    'rfc_col': rfc_col,
                    'fecha_ingreso_col': f_ing_col,
                    'fecha_egreso_col': f_egr_col
                })

            if not rfc_col:
                continue

            for _, row in df.iterrows():
                rfc = self.limpiar_rfc(row.get(rfc_col))
                if not rfc:
                    continue
                fi = self.limpiar_fecha(row.get(f_ing_col)) if f_ing_col else None
                fe = self.limpiar_fecha(row.get(f_egr_col)) if f_egr_col else None

                entes_rfc[rfc].append({
                    'ente': ente,
                    'hoja': sheet,
                    'nombre': str(row.get(nombre_col, '') or ''),
                    'puesto': str(row.get(puesto_col, '') or ''),
                    'fecha_ingreso': fi,
                    'fecha_egreso': fe,
                    'rfc_original': str(row.get(rfc_col, '')),
                    'fecha_ingreso_columna': f_ing_col or 'No encontrada',
                    'fecha_egreso_columna': f_egr_col or 'No encontrada'
                })

        print(f"🎯 RFCs únicos: {len(entes_rfc)} | Entes detectados: {len(entes_detectados)}")

        resultados = []

        for rfc, regs in entes_rfc.items():
            # --- contexto por RFC ---
            entes_del_rfc = sorted({r['ente'] for r in regs})

            # 1) incoherencias básicas registro a registro
            incoh = self._incoherencias_basicas(regs)
            for p in incoh:
                p['entes_detectados'] = entes_del_rfc
            resultados.extend(incoh)

            # 2) análisis por ente (duplicados/solapes internos)
            por_ente = defaultdict(list)
            for r in regs:
                por_ente[r['ente']].append(r)

            for ente, lista in por_ente.items():
                patrones_mismo = self._conflictos_mismo_ente(lista)
                for p in patrones_mismo:
                    p['entes_detectados'] = entes_del_rfc
                resultados.extend(patrones_mismo)

            # 3) solapamientos entre entes
            solapes_cross = self._solapes_entre_entes(por_ente)
            for p in solapes_cross:
                p['entes_detectados'] = entes_del_rfc
            resultados.extend(solapes_cross)

            # 4) notificación de relaciones activas sin egreso (informativa)
            activos = [r for r in regs if r.get('fecha_egreso') is None]
            if activos:
                resultados.append({
                    'rfc': regs[0]['rfc_original'],
                    'registros': activos,
                    'total_entes': len({r['ente'] for r in activos}),
                    'entes': list({r['ente'] for r in activos}),
                    'fecha_comun': 'RELACIONES_ACTIVAS',
                    'tipo_patron': 'RELACION_ACTIVA_SIN_EGRESO',
                    'severidad': 3,
                    'descripcion': 'Existen relaciones activas (sin FECHA_EGRESO) que deben ser verificadas',
                    'entes_detectados': entes_del_rfc
                })

        # Ordenar por prioridad auditoría
        resultados.sort(key=lambda x: (x['severidad'], x.get('total_entes', 1)), reverse=True)
        print(f"📈 Listo: {len(resultados)} hallazgos generados (auditoría).")

        return (resultados, estructura) if with_structure else resultados

    # ----------------------------------------------------
    # REGLAS AUDITORAS
    # ----------------------------------------------------
    def _incoherencias_basicas(self, registros):
        """
        - EGRESO_ANTES_INGRESO (sev 5)
        """
        hallazgos = []
        for r in registros:
            fi, fe = r.get('fecha_ingreso'), r.get('fecha_egreso')
            dfi, dfe = self._to_date(fi), self._to_date(fe)
            if dfi and dfe and dfe < dfi:
                hallazgos.append({
                    'rfc': r['rfc_original'],
                    'registros': [r],
                    'total_entes': 1,
                    'entes': [r['ente']],
                    'fecha_comun': f"{fi}→{fe}",
                    'tipo_patron': 'EGRESO_ANTES_INGRESO',
                    'severidad': 5,
                    'descripcion': 'Fecha de egreso anterior a la de ingreso (incoherencia grave)'
                })
        return hallazgos

    def _conflictos_mismo_ente(self, registros_ente):
        """
        Dentro del MISMO ente para un RFC:
        - DUPLICADO_MISMO_ENTE (fi,fe) idénticos en >1 registros (sev 4)
        - SOLAPE_MISMO_ENTE (periodos que se traslapan) (sev 5)
        Nota: reingreso es válido si NO hay solape.
        """
        hallazgos = []
        # Duplicados exactos por pareja (fi,fe)
        by_pair = defaultdict(list)
        for r in registros_ente:
            key = (r.get('fecha_ingreso'), r.get('fecha_egreso'))
            by_pair[key].append(r)
        for pair, items in by_pair.items():
            if len(items) > 1:
                hallazgos.append({
                    'rfc': items[0]['rfc_original'],
                    'registros': items,
                    'total_entes': 1,
                    'entes': [items[0]['ente']],
                    'fecha_comun': f"{pair[0]}→{pair[1]}",
                    'tipo_patron': 'DUPLICADO_MISMO_ENTE',
                    'severidad': 4,
                    'descripcion': 'Registros duplicados con las mismas fechas dentro del mismo ente'
                })

        # Solapes internos
        # Construir periodos como (start, end_inclusive, record)
        periods = []
        for r in registros_ente:
            fi, fe = self._to_date(r.get('fecha_ingreso')), self._to_date(r.get('fecha_egreso'))
            if not fi and not fe:
                # si no hay fechas, no podemos evaluar solape
                continue
            start = fi or self._to_date(r.get('fecha_egreso'))  # raro, pero evita None total
            end = fe or date.max  # sin egreso = activo
            if not start:
                # si no hay ingreso, pero sí egreso, ponemos start=egreso (no podremos detectar bien, pero evitamos crashes)
                start = end
            periods.append((start, end, r))

        # verificar solapes (inclusive)
        overlapping_set = set()
        for i in range(len(periods)):
            a_s, a_e, a_r = periods[i]
            for j in range(i+1, len(periods)):
                b_s, b_e, b_r = periods[j]
                if self._overlap(a_s, a_e, b_s, b_e):
                    overlapping_set.add(i); overlapping_set.add(j)

        if overlapping_set:
            regs = [periods[i][2] for i in sorted(overlapping_set)]
            ente = regs[0]['ente']
            # rango aproximado de conflicto
            starts = [self._to_date(r.get('fecha_ingreso')) or self._to_date(r.get('fecha_egreso')) for r in regs]
            ends = [self._to_date(r.get('fecha_egreso')) or date.max for r in regs]
            rango = f"{min([d for d in starts if d])}→{max(ends)}"
            hallazgos.append({
                'rfc': regs[0]['rfc_original'],
                'registros': regs,
                'total_entes': 1,
                'entes': [ente],
                'fecha_comun': rango,
                'tipo_patron': 'SOLAPE_MISMO_ENTE',
                'severidad': 5,
                'descripcion': 'Solapamientos de periodos dentro del mismo ente (no se puede ingresar dos veces a la vez)'
            })

        return hallazgos

    def _solapes_entre_entes(self, registros_por_ente):
        """
        Entre entes distintos para un RFC:
        - SOLAPE_ENTRE_ENTES (sev 5)
        Criterio: cualquier intersección entre [ingreso, egreso] de ente A y B.
        Egreso ausente = activo => solapa con cualquier ingreso de otro ente.
        """
        hallazgos = []
        entes = list(registros_por_ente.keys())
        if len(entes) < 2:
            return hallazgos

        # construir periodos por ente
        periods_by_ente = {}
        for ente, regs in registros_por_ente.items():
            ps = []
            for r in regs:
                fi, fe = self._to_date(r.get('fecha_ingreso')), self._to_date(r.get('fecha_egreso'))
                if not fi and not fe:
                    continue
                start = fi or self._to_date(r.get('fecha_egreso'))
                end = fe or date.max
                if not start:
                    start = end
                ps.append((start, end, r))
            periods_by_ente[ente] = ps

        # detectar solapes entre pares de entes
        overlapping_records = []
        overlapping_entes = set()
        overlap_ranges = []

        for i in range(len(entes)):
            for j in range(i+1, len(entes)):
                a, b = entes[i], entes[j]
                for s1, e1, r1 in periods_by_ente.get(a, []):
                    for s2, e2, r2 in periods_by_ente.get(b, []):
                        if self._overlap(s1, e1, s2, e2):
                            overlapping_records.extend([r1, r2])
                            overlapping_entes.update([a, b])
                            # calcular intersección aproximada
                            inter_s = max(s1, s2)
                            inter_e = min(e1, e2)
                            overlap_ranges.append((inter_s, inter_e))

        if overlapping_records:
            # dedupe manteniendo orden
            seen = set()
            uniq_records = []
            for r in overlapping_records:
                ident = (r['ente'], r['hoja'], r['fecha_ingreso'], r['fecha_egreso'])
                if ident not in seen:
                    uniq_records.append(r); seen.add(ident)

            if overlap_ranges:
                start_min = min(r[0] for r in overlap_ranges)
                end_max = max(r[1] for r in overlap_ranges)
                rango = f"{start_min}→{end_max}"
            else:
                rango = "PERIODOS_SOLAPADOS"

            hallazgos.append({
                'rfc': uniq_records[0]['rfc_original'],
                'registros': uniq_records,
                'total_entes': len(overlapping_entes),
                'entes': sorted(list(overlapping_entes)),
                'fecha_comun': rango,
                'tipo_patron': 'SOLAPE_ENTRE_ENTES',
                'severidad': 5,
                'descripcion': 'Relaciones activas en entes distintos con periodos solapados (no puede trabajar simultáneamente en varios entes)'
            })

        return hallazgos

    # ----------------------------------------------------
    # UTILIDADES
    # ----------------------------------------------------
    def _overlap(self, a_s, a_e, b_s, b_e):
        """
        Solape inclusivo: [a_s, a_e] ∩ [b_s, b_e] != ∅
        (Si egreso == ingreso del otro => cuenta como solape)
        """
        return (a_s <= b_e) and (b_s <= a_e)

