import pandas as pd
from collections import defaultdict
import re

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
    
    def procesar_archivo(self, filepath):
        """Procesar archivo Excel y encontrar duplicados entre entes"""
        try:
            # Leer todas las hojas del Excel
            xl_file = pd.ExcelFile(filepath)
            
            entes_rfc = defaultdict(list)
            
            for sheet_name in xl_file.sheet_names:
                print(f"Procesando hoja: {sheet_name}")
                
                # Leer datos de la hoja
                df = xl_file.parse(sheet_name)
                
                # Determinar columnas basado en el nombre de la hoja
                if 'FERIA' in sheet_name.upper():
                    rfc_col = 'RFC_FERIA'
                    nombre_col = 'NOMBRE'
                    puesto_col = 'PUESTO'
                elif 'SEPE' in sheet_name.upper():
                    rfc_col = 'RFC_SEPE'
                    nombre_col = 'NOMBRE'
                    puesto_col = 'PUESTO'
                else:
                    # Buscar columnas automáticamente
                    rfc_col = next((col for col in df.columns if 'RFC' in col.upper()), df.columns[0])
                    nombre_col = next((col for col in df.columns if 'NOMBRE' in col.upper()), df.columns[1])
                    puesto_col = next((col for col in df.columns if 'PUESTO' in col.upper()), df.columns[2])
                
                # Procesar cada fila
                for idx, row in df.iterrows():
                    rfc = self.limpiar_rfc(row.get(rfc_col))
                    if rfc:
                        entes_rfc[rfc].append({
                            'ente': sheet_name,
                            'nombre': row.get(nombre_col, ''),
                            'puesto': row.get(puesto_col, ''),
                            'rfc_original': row.get(rfc_col, '')
                        })
            
            # Encontrar RFCs que aparecen en múltiples entes
            duplicados = {}
            for rfc, registros in entes_rfc.items():
                if len(registros) > 1:
                    entes_unicos = list(set(reg['ente'] for reg in registros))
                    if len(entes_unicos) > 1:
                        duplicados[rfc] = {
                            'rfc': rfc,
                            'registros': registros,
                            'total_entes': len(entes_unicos),
                            'entes': entes_unicos
                        }
            
            # Convertir a lista para el frontend
            resultados = list(duplicados.values())
            
            # Ordenar por número de entes (mayor primero)
            resultados.sort(key=lambda x: x['total_entes'], reverse=True)
            
            return resultados
            
        except Exception as e:
            print(f"Error procesando archivo: {str(e)}")
            raise e
    
    def analizar_horarios(self, registros):
        """Para la siguiente etapa - análisis de horarios"""
        # Aquí implementarás la lógica para detectar conflictos de horario
        pass
