"""
Procesador de análisis de patrones laborales
Detecta inconsistencias en relaciones laborales entre entes
"""

import pandas as pd
from collections import defaultdict
from datetime import date
from .base import BaseProcessor


class PatternsProcessor(BaseProcessor):
    """
    Analiza patrones y inconsistencias en relaciones laborales

    Reglas de auditoría:
    - SOLAPE_ENTRE_ENTES (severidad 5): Relaciones simultáneas en diferentes entes
    - SOLAPE_MISMO_ENTE (severidad 5): Periodos solapados en el mismo ente
    - DUPLICADO_MISMO_ENTE (severidad 4): Registros duplicados exactos
    - EGRESO_ANTES_INGRESO (severidad 5): Fecha de egreso anterior al ingreso
    - RELACION_ACTIVA_SIN_EGRESO (severidad 3): Relaciones sin fecha de egreso
    """

    def __init__(self):
        super().__init__(logger_name='PatternsProcessor')

    # ========================================================
    # DETECCIÓN DE COLUMNAS
    # ========================================================

    def detectar_columnas(self, df, ente):
        """
        Detecta columnas relevantes para análisis de patrones

        Args:
            df: DataFrame con datos del ente
            ente: Nombre del ente

        Returns:
            tuple: (rfc_col, nombre_col, puesto_col, fecha_ingreso_col, fecha_egreso_col)
        """
        cache_key = f"{ente}_{hash(str(df.columns.tolist()))}"
        if cache_key in self.column_cache:
            return self.column_cache[cache_key]

        cols = df.columns.astype(str)

        # Detectar columnas una por una
        rfc_col = self.detectar_columna(cols, ['RFC'])
        nombre_col = self.detectar_columna(cols, ['NOMBRE'])
        puesto_col = self.detectar_columna(cols, ['PUESTO'])

        # Fecha de ingreso
        fecha_ingreso_col = next(
            (c for c in cols
             if any(k in c.upper() for k in ['FECHA', 'FCHA'])
             and any(k in c.upper() for k in ['INGRESO', 'ING'])),
            None
        )

        # Fecha de egreso
        fecha_egreso_col = next(
            (c for c in cols
             if any(k in c.upper() for k in ['FECHA', 'FCHA'])
             and any(k in c.upper() for k in ['EGRESO', 'EGR', 'BAJA', 'SALIDA'])),
            None
        )

        resultado = (rfc_col, nombre_col, puesto_col, fecha_ingreso_col, fecha_egreso_col)
        self.column_cache[cache_key] = resultado

        self.logger.info(f"Columnas detectadas en {ente}: RFC={rfc_col}, "
                        f"Ingreso={fecha_ingreso_col}, Egreso={fecha_egreso_col}")

        return resultado

    # ========================================================
    # PROCESAMIENTO PRINCIPAL
    # ========================================================

    def procesar_archivo(self, filepath, with_structure=False):
        """
        Procesa archivo Excel y detecta patrones de inconsistencias

        Args:
            filepath: Ruta al archivo Excel
            with_structure: Si True, retorna también la estructura del archivo

        Returns:
            list o tuple: Lista de hallazgos, opcionalmente con estructura
        """
        self.logger.info(f"Iniciando procesamiento de patrones: {filepath}")

        xl = pd.ExcelFile(filepath)
        entes_rfc = defaultdict(list)
        entes_detectados = set()
        estructura = []

        # Procesar cada hoja del Excel
        for sheet in xl.sheet_names:
            ente = self.extraer_ente_de_nombre_hoja(sheet)
            entes_detectados.add(ente)

            df = xl.parse(sheet)
            rfc_col, nombre_col, puesto_col, f_ing_col, f_egr_col = self.detectar_columnas(df, ente)

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
                self.logger.warning(f"Hoja '{sheet}' omitida: no se encontró columna RFC")
                continue

            # Procesar cada fila
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

        self.logger.info(f"RFCs únicos: {len(entes_rfc)} | Entes detectados: {len(entes_detectados)}")

        # Analizar cada RFC
        resultados = []
        for rfc, registros in entes_rfc.items():
            entes_del_rfc = sorted({r['ente'] for r in registros})

            # 1. Incoherencias básicas
            hallazgos_basicos = self._incoherencias_basicas(registros)
            for h in hallazgos_basicos:
                h['entes_detectados'] = entes_del_rfc
            resultados.extend(hallazgos_basicos)

            # 2. Conflictos dentro del mismo ente
            por_ente = defaultdict(list)
            for r in registros:
                por_ente[r['ente']].append(r)

            for ente, lista in por_ente.items():
                hallazgos_mismo = self._conflictos_mismo_ente(lista)
                for h in hallazgos_mismo:
                    h['entes_detectados'] = entes_del_rfc
                resultados.extend(hallazgos_mismo)

            # 3. Solapes entre diferentes entes
            hallazgos_cross = self._solapes_entre_entes(por_ente)
            for h in hallazgos_cross:
                h['entes_detectados'] = entes_del_rfc
            resultados.extend(hallazgos_cross)

            # 4. Relaciones activas sin egreso
            activos = [r for r in registros if r.get('fecha_egreso') is None]
            if activos:
                resultados.append({
                    'rfc': registros[0]['rfc_original'],
                    'registros': activos,
                    'total_entes': len({r['ente'] for r in activos}),
                    'entes': list({r['ente'] for r in activos}),
                    'fecha_comun': 'RELACIONES_ACTIVAS',
                    'tipo_patron': 'RELACION_ACTIVA_SIN_EGRESO',
                    'severidad': 3,
                    'descripcion': 'Relaciones activas sin fecha de egreso (verificar vigencia)',
                    'entes_detectados': entes_del_rfc
                })

        # Ordenar por severidad
        resultados.sort(key=lambda x: (x['severidad'], x.get('total_entes', 1)), reverse=True)

        self.logger.info(f"Procesamiento completado: {len(resultados)} hallazgos detectados")

        return (resultados, estructura) if with_structure else resultados

    # ========================================================
    # REGLAS DE AUDITORÍA
    # ========================================================

    def _incoherencias_basicas(self, registros):
        """Detecta egreso anterior al ingreso"""
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
                    'descripcion': 'Fecha de egreso anterior a la de ingreso (inconsistencia crítica)'
                })

                self.logger.warning(f"RFC {r['rfc_original']}: Egreso antes de ingreso en {r['ente']}")

        return hallazgos

    def _conflictos_mismo_ente(self, registros_ente):
        """Detecta duplicados y solapes dentro del mismo ente"""
        hallazgos = []

        if not registros_ente:
            return hallazgos

        # Duplicados exactos
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
                    'descripcion': 'Registros duplicados con las mismas fechas'
                })

        # Solapes internos
        periods = []
        for r in registros_ente:
            fi, fe = self._to_date(r.get('fecha_ingreso')), self._to_date(r.get('fecha_egreso'))

            if not fi and not fe:
                continue

            start = fi or fe
            end = fe or date.max

            if not start:
                start = end

            periods.append((start, end, r))

        # Verificar solapes
        overlapping_set = set()
        for i in range(len(periods)):
            a_s, a_e, a_r = periods[i]
            for j in range(i + 1, len(periods)):
                b_s, b_e, b_r = periods[j]
                if self._overlap(a_s, a_e, b_s, b_e):
                    overlapping_set.add(i)
                    overlapping_set.add(j)

        if overlapping_set:
            regs = [periods[i][2] for i in sorted(overlapping_set)]
            ente = regs[0]['ente']

            starts = [self._to_date(r.get('fecha_ingreso')) or self._to_date(r.get('fecha_egreso'))
                     for r in regs]
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
                'descripcion': 'Periodos solapados dentro del mismo ente'
            })

            self.logger.warning(f"RFC {regs[0]['rfc_original']}: Solape en {ente}")

        return hallazgos

    def _solapes_entre_entes(self, registros_por_ente):
        """Detecta solapes entre diferentes entes"""
        hallazgos = []
        entes = list(registros_por_ente.keys())

        if len(entes) < 2:
            return hallazgos

        # Construir periodos por ente
        periods_by_ente = {}
        for ente, regs in registros_por_ente.items():
            ps = []
            for r in regs:
                fi, fe = self._to_date(r.get('fecha_ingreso')), self._to_date(r.get('fecha_egreso'))

                if not fi and not fe:
                    continue

                start = fi or fe
                end = fe or date.max

                if not start:
                    start = end

                ps.append((start, end, r))

            periods_by_ente[ente] = ps

        # Detectar solapes entre pares de entes
        overlapping_records = []
        overlapping_entes = set()
        overlap_ranges = []

        for i in range(len(entes)):
            for j in range(i + 1, len(entes)):
                a, b = entes[i], entes[j]
                for s1, e1, r1 in periods_by_ente.get(a, []):
                    for s2, e2, r2 in periods_by_ente.get(b, []):
                        if self._overlap(s1, e1, s2, e2):
                            overlapping_records.extend([r1, r2])
                            overlapping_entes.update([a, b])

                            inter_s = max(s1, s2)
                            inter_e = min(e1, e2)
                            overlap_ranges.append((inter_s, inter_e))

        if overlapping_records:
            # Eliminar duplicados
            seen = set()
            uniq_records = []
            for r in overlapping_records:
                ident = (r['ente'], r['hoja'], r['fecha_ingreso'], r['fecha_egreso'])
                if ident not in seen:
                    uniq_records.append(r)
                    seen.add(ident)

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
                'descripcion': 'Relaciones simultáneas en diferentes entes (inconsistencia crítica)'
            })

            self.logger.warning(
                f"RFC {uniq_records[0]['rfc_original']}: "
                f"Solape entre entes: {', '.join(sorted(overlapping_entes))}"
            )

        return hallazgos
