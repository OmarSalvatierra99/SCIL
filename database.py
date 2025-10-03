import sqlite3
import json
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_path='scil.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Inicializar base de datos SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS resultados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfc TEXT NOT NULL,
                datos TEXT NOT NULL,
                fecha_analisis TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS archivos_procesados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_archivo TEXT NOT NULL,
                fecha_procesamiento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_duplicados INTEGER
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def guardar_resultados(self, resultados):
        """Guardar resultados en la base de datos"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Limpiar resultados anteriores
        cursor.execute('DELETE FROM resultados')
        
        for resultado in resultados:
            cursor.execute(
                'INSERT INTO resultados (rfc, datos) VALUES (?, ?)',
                (resultado['rfc'], json.dumps(resultado, ensure_ascii=False))
            )
        
        conn.commit()
        conn.close()
    
    def obtener_resultados(self):
        """Obtener resultados de la base de datos"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT datos FROM resultados ORDER BY fecha_analisis DESC')
        rows = cursor.fetchall()
        
        resultados = []
        for row in rows:
            resultados.append(json.loads(row[0]))
        
        conn.close()
        return resultados
