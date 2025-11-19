"""
Procesador de análisis de cruces de horarios
Detecta solapamientos de horarios entre entes educativos
"""

import pandas as pd
from collections import defaultdict
from datetime import time
from .base import BaseProcessor


class SchedulesProcessor(BaseProcessor):
    """
    Analiza cruces y solapamientos de horarios docentes

    Reglas de auditoría:
    - HORARIO_INCOHERENTE (severidad 5): Hora salida < hora entrada
    - HORARIO_FALTANTE (severidad 3): Registros con datos incompletos
    - SOLAPE_HORARIO_ENTRE_ENTES (severidad 5): Horarios simultáneos en diferentes entes
    - SOLAPE_HORARIO_MISMO_ENTE (severidad 4): Horarios solapados en el mismo ente
    - RELACION_ACTIVA_SIN_EGRESO (severidad 2): Docente sin fecha de egreso
    """

    def __init__(self):
        super().__init__(logger_name='SchedulesProcessor')

    # ========================================================
    # LIMPIEZA DE HORAS
    # ========================================================

    def limpiar_hora(self, valor):
        """
        Limpia y normaliza valores de hora

        Args:
            valor: Valor de hora (datetime, string, etc.)

        Returns:
            str: Hora en formato 'HH:MM' o None
        """
        if pd.isna(valor):
            return None

        s = str(valor).strip()
        if not s:
            return None

        try:
            # Si es datetime
            if isinstance(valor, pd.Timestamp):
                return valor.strftime('%H:%M')

            # Si tiene formato HH:MM
            if ':' in s:
                partes = s.split(':')[:2]
                h, m = int(partes[0]), int(partes[1])
                return f"{h:02d}:{m:02d}"

            # Si es formato HHMM (ej: 730 -> 07:30)
            if len(s) == 3 or len(s) == 4:
                if len(s) == 3:
                    s = '0' + s
                return f"{s[:2]}:{s[2:]}"

        except Exception as e:
            self.logger.warning(f"Error limpiando hora '{valor}': {e}")

        return None

    def _to_time(self, hora_str):
        """
        Convierte string 'HH:MM' a objeto time

        Args:
            hora_str: String en formato 'HH:MM'

        Returns:
            time: Objeto time o None
        """
        if not hora_str:
            return None

        try:
            h, m = map(int, hora_str.split(':'))
            return time(h, m)
        except Exception as e:
            self.logger.warning(f"Error convirtiendo '{hora_str}' a time: {e}")
            return None

    # ========================================================
    # DETECCIÓN DE COLUMNAS
    # ========================================================

    def detectar_columnas(self, df, ente):
        """
        Detecta columnas relevantes para análisis de horarios

        Args:
            df: DataFrame con datos del ente
            ente: Nombre del ente

        Returns:
            tuple: (rfc_col, nombre_col, f_ing, f_egr, dia, h_ent, h_sal, plantel)
        """
        cols = df.columns.astype(str)
        cache_key = f"{ente}_{hash(str(cols.tolist()))}"

        if cache_key in self.column_cache:
            return self.column_cache[cache_key]

        # Detectar cada columna
        rfc_col = self.detectar_columna(cols, ['RFC'])
        nombre_col = self.detectar_columna(cols, ['NOMBRE'])
        f_ing_col = self.detectar_columna(cols, ['INGRESO'])
        f_egr_col = self.detectar_columna(cols, ['EGRESO', 'BAJA', 'SALIDA'])
        dia_col = self.detectar_columna(cols, ['DIA'])
        h_ent_col = self.detectar_columna(cols, ['ENTRADA'])
        h_sal_col = self.detectar_columna(cols, ['SALIDA'])
        plantel_col = self.detectar_columna(cols, ['PLANTEL', 'ESCUELA'])

        resultado = (rfc_col, nombre_col, f_ing_col, f_egr_col,
                    dia_col, h_ent_col, h_sal_col, plantel_col)

        self.column_cache[cache_key] = resultado

        self.logger.info(f"Columnas detectadas en {ente}: RFC={rfc_col}, "
                        f"Día={dia_col}, Entrada={h_ent_col}, Salida={h_sal_col}")

        return resultado

    # ========================================================
    # PROCESAMIENTO PRINCIPAL
    # ========================================================

    def procesar_archivo(self, filepath):
        """
        Procesa archivo Excel y detecta cruces de horarios

        Args:
            filepath: Ruta al archivo Excel

        Returns:
            list: Lista de hallazgos de cruces de horarios
        """
        self.logger.info(f"Iniciando procesamiento de horarios: {filepath}")

        xl = pd.ExcelFile(filepath)
        maestros = defaultdict(list)
        entes_detectados = set()

        # Procesar cada hoja del Excel
        for hoja in xl.sheet_names:
            ente = self.extraer_ente_de_nombre_hoja(hoja)
            entes_detectados.add(ente)

            df = xl.parse(hoja)
            cols = self.detectar_columnas(df, ente)
            rfc_col, nombre_col, f_ing, f_egr, dia, h_ent, h_sal, plantel = cols

            if not rfc_col:
                self.logger.warning(f"Hoja '{hoja}' omitida: no se encontró columna RFC")
                continue

            # Procesar cada fila
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

        self.logger.info(f"Maestros únicos: {len(maestros)} | Entes: {len(entes_detectados)}")

        # Analizar cada maestro
        resultados = []
        for rfc, registros in maestros.items():
            entes_rfc = {r['ente'] for r in registros}

            # Validaciones
            resultados.extend(self._validar_incoherencias(rfc, registros))
            resultados.extend(self._solape_mismo_ente(rfc, registros))

            if len(entes_rfc) > 1:
                resultados.extend(self._solape_entre_entes(rfc, registros))

            # Relaciones activas
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
                    'descripcion': 'Relación docente activa sin fecha de egreso'
                })

        # Ordenar por severidad
        resultados.sort(key=lambda x: x['severidad'], reverse=True)

        self.logger.info(f"Procesamiento completado: {len(resultados)} hallazgos detectados")

        return resultados

    # ========================================================
    # REGLAS DE AUDITORÍA
    # ========================================================

    def _validar_incoherencias(self, rfc, registros):
        """Detecta horarios incoherentes o incompletos"""
        hallazgos = []

        for r in registros:
            h_in = self._to_time(r.get('hora_entrada'))
            h_out = self._to_time(r.get('hora_salida'))

            # Datos incompletos
            if not r.get('dia_semana') or not h_in or not h_out:
                hallazgos.append({
                    'rfc': rfc,
                    'registros': [r],
                    'total_entes': 1,
                    'entes': [r['ente']],
                    'fecha_comun': 'DATOS_INCOMPLETOS',
                    'tipo_patron': 'HORARIO_FALTANTE',
                    'severidad': 3,
                    'descripcion': 'Registro con día u horas incompletas'
                })
                continue

            # Salida antes de entrada
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

                self.logger.warning(
                    f"RFC {rfc}: Horario incoherente en {r['ente']} "
                    f"({r['hora_entrada']} -> {r['hora_salida']})"
                )

        return hallazgos

    def _solape_mismo_ente(self, rfc, registros):
        """Detecta solapes de horario dentro del mismo ente"""
        hallazgos = []
        por_ente_dia = defaultdict(list)

        # Agrupar por ente y día
        for r in registros:
            if r.get('hora_entrada') and r.get('hora_salida') and r.get('dia_semana'):
                por_ente_dia[(r['ente'], r['dia_semana'])].append(r)

        # Buscar solapes
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
                    'descripcion': f'Solapamiento de horarios en {key[0]} el {key[1]}'
                })

                self.logger.warning(f"RFC {rfc}: Solape de horario en {key[0]} el {key[1]}")

        return hallazgos

    def _solape_entre_entes(self, rfc, registros):
        """Detecta solapes de horario entre diferentes entes"""
        hallazgos = []
        por_dia = defaultdict(list)

        # Agrupar por día
        for r in registros:
            if r.get('hora_entrada') and r.get('hora_salida') and r.get('dia_semana'):
                por_dia[r['dia_semana']].append(r)

        # Buscar solapes entre entes
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

                self.logger.warning(
                    f"RFC {rfc}: Solape de horario entre entes el {dia} "
                    f"({', '.join(sorted(entes))})"
                )

        return hallazgos

    def _buscar_solapes(self, registros):
        """Busca solapes de horario en una lista de registros"""
        result = []
        times = []

        # Convertir a objetos time
        for r in registros:
            start = self._to_time(r.get('hora_entrada'))
            end = self._to_time(r.get('hora_salida'))

            if not start or not end:
                continue

            times.append((start, end, r))

        # Comparar todos los pares
        for i in range(len(times)):
            s1, e1, r1 = times[i]
            for j in range(i + 1, len(times)):
                s2, e2, r2 = times[j]

                # Solape inclusivo
                if (s1 <= e2) and (s2 <= e1):
                    result.extend([r1, r2])

        # Eliminar duplicados manteniendo orden
        uniq = []
        seen = set()
        for r in result:
            key = (r['ente'], r['dia_semana'], r['hora_entrada'], r['hora_salida'])
            if key not in seen:
                uniq.append(r)
                seen.add(key)

        return uniq
