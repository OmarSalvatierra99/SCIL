import pandas as pd
from collections import defaultdict
import re
from datetime import datetime

class DataProcessor:
    def __init__(self):
        self.entes = {}

    def limpiar_rfc(self, rfc):
        """Limpiar y estandarizar RFC"""
        if pd.isna(rfc):
            return None
        rfc_limpio = str(rfc).strip().upper()
        # Remover espacios y caracteres especiales
        rfc_limpio = re.sub(r'[^A-Z0-9]', '', rfc_limpio)
        return rfc_limpio if len(rfc_limpio) >= 10 else None

    def limpiar_fecha(self, fecha):
        """Limpiar y estandarizar fecha"""
        if pd.isna(fecha):
            return None
        
        # Si es ya un objeto datetime
        if isinstance(fecha, datetime):
            return fecha.strftime('%Y-%m-%d')
        
        # Si es string
        fecha_str = str(fecha).strip()
        if not fecha_str or fecha_str.lower() in ['nan', 'nat', '']:
            return None
            
        # Intentar parsear diferentes formatos de fecha
        try:
            # Para formato de fecha Excel (número serial)
            if isinstance(fecha, (int, float)):
                return pd.to_datetime(fecha, unit='D', origin='1899-12-30').strftime('%Y-%m-%d')
            
            # Para strings de fecha
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d']:
                try:
                    fecha_dt = datetime.strptime(fecha_str, fmt)
                    return fecha_dt.strftime('%Y-%m-%d')
                except ValueError:
                    continue
                    
            # Si no se pudo parsear, devolver el string original
            return fecha_str
        except:
            return fecha_str

    def extraer_ente_de_nombre_hoja(self, sheet_name):
        """Extraer el nombre del ente del nombre de la hoja"""
        # Formato: [ENTE]_[PERIODO]
        partes = sheet_name.split('_')
        if len(partes) >= 2:
            return partes[0]  # Retorna la primera parte como ente
        return sheet_name  # Si no puede dividir, usa el nombre completo

    def encontrar_columna_rfc(self, df, ente):
        """Encontrar automáticamente la columna RFC basada en el ente"""
        # Buscar columnas que empiecen con RFC
        columnas_rfc = [col for col in df.columns if str(col).startswith('RFC')]
        
        if not columnas_rfc:
            return None
        
        # Priorizar RFC_[ENTE]
        columna_especifica = f"RFC_{ente}"
        if columna_especifica in df.columns:
            return columna_especifica
        
        # Si no existe, usar la primera columna RFC que encuentre
        return columnas_rfc[0]

    def procesar_archivo(self, filepath):
        """Procesar archivo Excel y encontrar duplicados entre entes"""
        try:
            # Leer todas las hojas del Excel
            xl_file = pd.ExcelFile(filepath)

            entes_rfc = defaultdict(list)
            entes_detectados = set()

            for sheet_name in xl_file.sheet_names:
                print(f"Procesando hoja: {sheet_name}")

                # Extraer ente del nombre de la hoja
                ente = self.extraer_ente_de_nombre_hoja(sheet_name)
                entes_detectados.add(ente)

                # Leer datos de la hoja
                df = xl_file.parse(sheet_name)

                # Encontrar columnas automáticamente
                rfc_col = self.encontrar_columna_rfc(df, ente)
                if not rfc_col:
                    print(f"  ⚠️ No se encontró columna RFC en {sheet_name}, saltando...")
                    continue

                # Buscar otras columnas
                nombre_col = next((col for col in df.columns if 'NOMBRE' in str(col).upper()), None)
                puesto_col = next((col for col in df.columns if 'PUESTO' in str(col).upper()), None)
                fecha_col = next((col for col in df.columns if 'FECHA' in str(col).upper() and 'INGRESO' in str(col).upper()), None)

                print(f"  📊 Columnas detectadas - RFC: {rfc_col}, Nombre: {nombre_col}, Puesto: {puesto_col}, Fecha: {fecha_col}")

                # Procesar cada fila
                registros_procesados = 0
                for idx, row in df.iterrows():
                    rfc = self.limpiar_rfc(row.get(rfc_col))
                    if rfc:
                        fecha_ingreso = self.limpiar_fecha(row.get(fecha_col)) if fecha_col and fecha_col in row else None
                        
                        entes_rfc[rfc].append({
                            'ente': ente,
                            'hoja': sheet_name,
                            'nombre': row.get(nombre_col, '') if nombre_col else '',
                            'puesto': row.get(puesto_col, '') if puesto_col else '',
                            'fecha_ingreso': fecha_ingreso,
                            'rfc_original': row.get(rfc_col, ''),
                            'fecha_columna': fecha_col if fecha_col else 'No encontrada'
                        })
                        registros_procesados += 1

                print(f"  ✅ {registros_procesados} registros procesados en {sheet_name}")

            print(f"\n🎯 Entes detectados: {', '.join(entes_detectados)}")

            # Encontrar RFCs que aparecen en múltiples entes
            duplicados = {}
            for rfc, registros in entes_rfc.items():
                if len(registros) > 1:
                    entes_unicos = list(set(reg['ente'] for reg in registros))
                    if len(entes_unicos) > 1:
                        # Analizar conflictos de fechas
                        conflictos_fecha = self.analizar_conflictos_fecha(registros)
                        
                        duplicados[rfc] = {
                            'rfc': rfc,
                            'registros': registros,
                            'total_entes': len(entes_unicos),
                            'entes': entes_unicos,
                            'conflictos_fecha': conflictos_fecha,
                            'tiene_conflicto_fecha': len(conflictos_fecha) > 0,
                            'entes_detectados': list(entes_detectados)
                        }

            # Convertir a lista para el frontend
            resultados = list(duplicados.values())

            # Ordenar por número de entes (mayor primero) y luego por conflicto de fecha
            resultados.sort(key=lambda x: (x['total_entes'], x['tiene_conflicto_fecha']), reverse=True)

            print(f"📈 Análisis completado: {len(resultados)} duplicados encontrados")
            return resultados

        except Exception as e:
            print(f"❌ Error procesando archivo: {str(e)}")
            raise e

    def analizar_conflictos_fecha(self, registros):
        """Analizar conflictos en fechas de ingreso entre diferentes entes"""
        conflictos = []
        
        # Agrupar registros por ente
        registros_por_ente = {}
        for registro in registros:
            ente = registro['ente']
            if ente not in registros_por_ente:
                registros_por_ente[ente] = []
            registros_por_ente[ente].append(registro)
        
        # Verificar si hay fechas inconsistentes para el mismo RFC en diferentes entes
        entes_con_fecha = [ente for ente, regs in registros_por_ente.items() 
                          if any(reg['fecha_ingreso'] for reg in regs)]
        
        if len(entes_con_fecha) > 1:
            # Recolectar todas las fechas únicas
            fechas_unicas = set()
            for ente, regs in registros_por_ente.items():
                for reg in regs:
                    if reg['fecha_ingreso']:
                        fechas_unicas.add(reg['fecha_ingreso'])
            
            # Si hay más de una fecha única, hay conflicto
            if len(fechas_unicas) > 1:
                for ente, regs in registros_por_ente.items():
                    for reg in regs:
                        if reg['fecha_ingreso']:
                            conflictos.append({
                                'ente': ente,
                                'hoja': reg['hoja'],
                                'nombre': reg['nombre'],
                                'fecha_ingreso': reg['fecha_ingreso'],
                                'puesto': reg['puesto'],
                                'columna_fecha': reg['fecha_columna']
                            })
        
        return conflictos

    def analizar_horarios(self, registros):
        """Para la siguiente etapa - análisis de horarios"""
        pass
