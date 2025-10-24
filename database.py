# ===========================================================
# database.py — SCIL QNA 2025 / Gestor de Base de Datos Auditor
# Compatible con procesamiento en memoria (tabla laboral)
# ===========================================================

import sqlite3
import json
import hashlib
import threading


class DatabaseManager:
    def __init__(self, db_path='scil.db'):
        self.db_path = db_path
        self._local = threading.local()
        self._initialized = False
        self.init_db()

    # -------------------------------------------------------
    # Conexión y configuración
    # -------------------------------------------------------
    def get_connection(self):
        if not hasattr(self._local, 'conn'):
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA foreign_keys=ON;")
            except Exception:
                pass
            self._local.conn = conn
        return self._local.conn

    def init_db(self):
        conn = self.get_connection()
        cur = conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS laboral (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo_analisis TEXT NOT NULL,
                rfc TEXT NOT NULL,
                datos TEXT NOT NULL,
                hash_firma TEXT UNIQUE,
                fecha_analisis TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS archivos_procesados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_archivo TEXT NOT NULL,
                tipo_analisis TEXT,
                total_registros INTEGER,
                fecha_procesamiento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                usuario TEXT UNIQUE NOT NULL,
                clave TEXT NOT NULL,           
                entes TEXT NOT NULL            
            );

            CREATE INDEX IF NOT EXISTS idx_tipo_lab ON laboral(tipo_analisis);
            CREATE INDEX IF NOT EXISTS idx_rfc_lab ON laboral(rfc);
            CREATE INDEX IF NOT EXISTS idx_hash_lab ON laboral(hash_firma);
        """)
        conn.commit()
        self._initialized = True
        print("✅ Base de datos inicializada (modo temporal: scil.db)")

    # -------------------------------------------------------
    # Utilidades internas
    # -------------------------------------------------------
    @staticmethod
    def _safe_json_loads(x):
        if x is None:
            return None
        if isinstance(x, (dict, list)):
            return x
        if isinstance(x, (bytes, bytearray)):
            try:
                x = x.decode('utf-8', errors='ignore')
            except Exception:
                return None
        if isinstance(x, str):
            x = x.strip()
            if not x:
                return None
            try:
                return json.loads(x)
            except Exception:
                return None
        return None

    # -------------------------------------------------------
    # Gestión de usuarios
    # -------------------------------------------------------
    def get_usuario(self, usuario, clave):
        if not usuario or not clave:
            return None
        conn = self.get_connection()
        cur = conn.cursor()
        clave_hash = hashlib.sha256(clave.encode('utf-8')).hexdigest()
        cur.execute("SELECT * FROM usuarios WHERE usuario=? AND clave=?", (usuario, clave_hash))
        row = cur.fetchone()
        if not row:
            return None

        data = dict(row)
        entes = [e.strip().upper() for e in (data.get("entes") or "").split(",") if e.strip()]
        if len(entes) > 40 or "*" in entes:
            entes = []
        data["entes"] = entes
        return data

    # -------------------------------------------------------
    # Comparación y guardado de resultados
    # -------------------------------------------------------
    def comparar_con_historico(self, nuevos_resultados, tipo_analisis='laboral'):
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT hash_firma FROM laboral WHERE tipo_analisis=?", (tipo_analisis,))
        antiguos = {r['hash_firma'] for r in cur.fetchall()}

        nuevos_unicos, repetidos, nuevos_hash = [], [], set()
        for res in nuevos_resultados:
            firma = hashlib.sha256(
                f"{res.get('rfc','')}_{res.get('tipo_patron','')}_{res.get('descripcion','')}_{tipo_analisis}".encode('utf-8')
            ).hexdigest()
            res['hash_firma'] = firma
            if firma in antiguos:
                repetidos.append(res)
            else:
                nuevos_unicos.append(res)
            nuevos_hash.add(firma)

        print(f"🔍 Comparación QNA: {len(nuevos_unicos)} nuevos, {len(repetidos)} repetidos.")
        return nuevos_unicos, repetidos, []

    def guardar_resultados(self, resultados, tipo_analisis='laboral', nombre_archivo=None):
        if not resultados:
            return 0
        conn = self.get_connection()
        cur = conn.cursor()
        nuevos = 0
        cur.execute('BEGIN TRANSACTION')
        try:
            for res in resultados:
                firma = res.get('hash_firma') or hashlib.sha256(
                    f"{res.get('rfc','')}_{res.get('tipo_patron','')}_{res.get('descripcion','')}_{tipo_analisis}".encode('utf-8')
                ).hexdigest()
                cur.execute("SELECT 1 FROM laboral WHERE hash_firma=?", (firma,))
                if cur.fetchone():
                    continue
                cur.execute("""
                    INSERT INTO laboral (tipo_analisis, rfc, datos, hash_firma)
                    VALUES (?, ?, ?, ?)
                """, (tipo_analisis, res.get('rfc',''), json.dumps(res, ensure_ascii=False), firma))
                nuevos += 1

            if nombre_archivo:
                cur.execute("""
                    INSERT INTO archivos_procesados (nombre_archivo, tipo_analisis, total_registros)
                    VALUES (?, ?, ?)
                """, (nombre_archivo, tipo_analisis, len(resultados)))

            conn.commit()
            print(f"💾 {nuevos} resultados guardados.")
        except Exception as e:
            conn.rollback()
            print(f"❌ Error guardando resultados: {e}")
            raise
        return nuevos

     # -------------------------------------------------------
    # Lectura con paginación (general)
    # -------------------------------------------------------
    def obtener_resultados_paginados(self, tipo_analisis=None, busqueda=None, pagina=1, limite=50):
        conn = self.get_connection()
        cur = conn.cursor()

        base = "FROM laboral WHERE 1=1"
        params = []
        if tipo_analisis:
            base += " AND tipo_analisis=?"
            params.append(tipo_analisis)
        if busqueda:
            base += " AND datos LIKE ?"
            params.append(f"%{busqueda}%")

        cur.execute(f"SELECT COUNT(1) {base}", tuple(params))
        total = cur.fetchone()[0]

        offset = (pagina - 1) * limite
        cur.execute(
            f"SELECT rfc, datos {base} ORDER BY fecha_analisis DESC LIMIT ? OFFSET ?",
            tuple(params + [limite, offset])
        )
        filas = cur.fetchall()

        resultados = []
        for f in filas:
            d = self._safe_json_loads(f['datos'])
            if not isinstance(d, dict):
                continue

            resultado = {
                "rfc": f["rfc"],
                "nombre": d.get("nombre", ""),
                "entes": d.get("entes", []),
                "estado": d.get("estado", ""),  # si no existe, queda vacío
                "registros": d.get("registros", []),
                "tipo_patron": d.get("tipo_patron", ""),
                "descripcion": d.get("descripcion", "")
            }

            resultados.append(resultado)

        return resultados, total


    # -------------------------------------------------------
    # Vistas detalladas — por RFC y por Ente
    # -------------------------------------------------------
    def obtener_resultados_por_rfc(self, rfc: str):
        """Devuelve información detallada de un trabajador por RFC."""
        if not rfc:
            return None
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT datos FROM laboral
            WHERE UPPER(rfc)=?
        """, (rfc.upper(),))
        filas = cur.fetchall()
        if not filas:
            return None

        nombre = ""
        entes = set()
        registros = []
        for row in filas:
            d = self._safe_json_loads(row["datos"])
            if not isinstance(d, dict):
                continue
            if d.get("nombre"):
                nombre = d.get("nombre")
            for e in (d.get("entes") or []):
                entes.add(e)
            for reg in (d.get("registros") or []):
                if isinstance(reg, dict):
                    registros.append(reg)

        return {"nombre": nombre, "entes": sorted(entes), "registros": registros}

    def obtener_resultados_por_ente(self, ente: str):
        """Devuelve todos los trabajadores asociados a un ente."""
        if not ente:
            return {}
        needle = ente.upper().strip()

        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT rfc, datos FROM laboral")
        filas = cur.fetchall()
        if not filas:
            return {}

        resultados_agrupados = {}
        for row in filas:
            rfc = (row["rfc"] or "SIN_RFC").upper()
            d = self._safe_json_loads(row["datos"])
            if not isinstance(d, dict):
                continue

            entes = d.get("entes") or []
            if not any(needle in (e or "").upper() for e in entes):
                continue

            nombre = d.get("nombre", "")
            if rfc not in resultados_agrupados:
                resultados_agrupados[rfc] = {"nombre": nombre, "registros": []}

            for reg in (d.get("registros") or []):
                if not isinstance(reg, dict):
                    continue
                ente_reg = (reg.get("ente") or "").upper()
                if needle in ente_reg:
                    resultados_agrupados[rfc]["registros"].append(reg)

        return resultados_agrupados

