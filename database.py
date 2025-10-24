# ===========================================================
# database.py — SCIL / SASP 2025
# Manejador central de base de datos SQLite
# ===========================================================

import sqlite3
import json
import hashlib


class DatabaseManager:
    def __init__(self, db_path="scil.db"):
        self.db_path = db_path
        self._init_db()

    # -------------------------------------------------------
    # Conexión
    # -------------------------------------------------------
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------
    # Inicialización
    # -------------------------------------------------------
    def _init_db(self):
        conn = self._connect()
        cur = conn.cursor()

        # Tabla laboral
        cur.execute("""
            CREATE TABLE IF NOT EXISTS laboral (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash_firma TEXT UNIQUE,
                datos TEXT NOT NULL,
                creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Usuarios
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                usuario TEXT UNIQUE NOT NULL,
                clave TEXT NOT NULL,
                entes TEXT NOT NULL
            )
        """)

        # Catálogo de entes
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clave TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                siglas TEXT,
                clasificacion TEXT,
                ambito TEXT,
                activo INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Catálogo de municipios
        cur.execute("""
            CREATE TABLE IF NOT EXISTS municipios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clave TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                siglas TEXT,
                clasificacion TEXT,
                ambito TEXT DEFAULT 'MUNICIPAL',
                activo INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()
        print("✅ Base de datos inicializada (modo scil.db)")

    # -------------------------------------------------------
    # Utilidades internas
    # -------------------------------------------------------
    def _hash_text(self, text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _sanitize(self, s):
        if not s:
            return ""
        return str(s).strip().upper().replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U")

    # -------------------------------------------------------
    # Usuarios
    # -------------------------------------------------------
    def get_usuario(self, usuario, clave):
        conn = self._connect()
        cur = conn.cursor()
        clave_hash = hashlib.sha256(clave.encode("utf-8")).hexdigest()
        cur.execute("""
            SELECT nombre, usuario, entes
            FROM usuarios
            WHERE usuario=? AND clave=?
        """, (usuario, clave_hash))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "nombre": row["nombre"],
            "usuario": row["usuario"],
            "entes": [x.strip() for x in row["entes"].split(",") if x.strip()]
        }

    # -------------------------------------------------------
    # Catálogos
    # -------------------------------------------------------
    def listar_entes(self, solo_activos=True):
        conn = self._connect()
        cur = conn.cursor()
        q = "SELECT clave, nombre, siglas, clasificacion, ambito FROM entes"
        if solo_activos:
            q += " WHERE activo=1"
        q += " ORDER BY nombre ASC"
        cur.execute(q)
        data = [dict(r) for r in cur.fetchall()]
        conn.close()
        return data

    def listar_municipios(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT clave, nombre, siglas, clasificacion, ambito
            FROM municipios
            WHERE activo=1
            ORDER BY nombre ASC
        """)
        data = [dict(r) for r in cur.fetchall()]
        conn.close()
        return data

    def get_mapa_siglas(self):
        """Devuelve {'SIGLA': 'ENTE_#####'} para búsqueda rápida."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT siglas, clave FROM entes WHERE activo=1")
        mapa = {}
        for sigla, clave in cur.fetchall():
            if sigla:
                mapa[self._sanitize(sigla)] = clave
        conn.close()
        return mapa

    # -------------------------------------------------------
    # Normalización de entes
    # -------------------------------------------------------
    def normalizar_ente(self, valor):
        """Devuelve nombre del ente según su sigla o clave."""
        if not valor:
            return None
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT nombre FROM entes
            WHERE UPPER(siglas)=UPPER(?) OR UPPER(clave)=UPPER(?)
            LIMIT 1
        """, (valor, valor))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    def normalizar_ente_clave(self, valor, mapa_siglas=None):
        """Convierte sigla o nombre a clave ENTE_#####."""
        if not valor:
            return None
        val = self._sanitize(valor)
        if mapa_siglas and val in mapa_siglas:
            return mapa_siglas[val]

        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT clave FROM entes
            WHERE UPPER(siglas)=? OR UPPER(nombre)=? OR UPPER(clave)=?
            LIMIT 1
        """, (val, val, val))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    # -------------------------------------------------------
    # Resultados laborales
    # -------------------------------------------------------
    def comparar_con_historico(self, nuevos):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT hash_firma FROM laboral")
        existentes = {r[0] for r in cur.fetchall()}

        nuevos_validos, repetidos = [], []
        for r in nuevos:
            texto = json.dumps(r, sort_keys=True, ensure_ascii=False)
            h = self._hash_text(texto)
            if h not in existentes:
                r["hash_firma"] = h
                nuevos_validos.append(r)
            else:
                repetidos.append(r)
        conn.close()
        return nuevos_validos, repetidos, len(repetidos)

    def guardar_resultados(self, resultados, tabla, archivo):
        conn = self._connect()
        cur = conn.cursor()
        count = 0
        for r in resultados:
            try:
                cur.execute("""
                    INSERT INTO laboral (hash_firma, datos)
                    VALUES (?, ?)
                """, (r["hash_firma"], json.dumps(r, ensure_ascii=False)))
                count += 1
            except sqlite3.IntegrityError:
                continue
        conn.commit()
        conn.close()
        return count

    def obtener_resultados_paginados(self, tabla, filtro, pagina, limite):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(f"SELECT datos FROM {tabla} ORDER BY id DESC LIMIT ? OFFSET ?", (limite, (pagina - 1) * limite))
        rows = cur.fetchall()
        conn.close()

        resultados = []
        for row in rows:
            try:
                resultados.append(json.loads(row[0]))
            except Exception:
                continue
        return resultados, len(resultados)

    def obtener_resultados_por_rfc(self, rfc):
        """Devuelve los registros asociados a un RFC, sin duplicados."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT datos FROM laboral
            WHERE json_extract(datos, '$.rfc') = ?
            ORDER BY id DESC
        """, (rfc,))
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return None

        resultados = []
        for row in rows:
            try:
                resultados.append(json.loads(row[0]))
            except Exception:
                continue

        if not resultados:
            return None

        # --- Unificación de registros únicos por combinación clave ---
        vistos = set()
        registros_unicos = []
        for r in resultados:
            for reg in r.get("registros", []):
                clave = (
                    reg.get("ente"),
                    reg.get("puesto"),
                    reg.get("monto"),
                    reg.get("fecha_ingreso"),
                    reg.get("fecha_egreso")
                )
                if clave not in vistos:
                    vistos.add(clave)
                    registros_unicos.append(reg)

        info = {
            "rfc": rfc,
            "nombre": resultados[0].get("nombre", ""),
            "entes": list({e for r in resultados for e in r.get("entes", [])}),
            "registros": registros_unicos,
            "estado": resultados[-1].get("estado", ""),
            "solventacion": resultados[-1].get("solventacion", "")
        }
        return info

    def actualizar_solventacion(self, rfc, estado, solventacion):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            UPDATE laboral
            SET datos = json_set(datos, '$.estado', ?, '$.solventacion', ?)
            WHERE json_extract(datos, '$.rfc') = ?
        """, (estado, solventacion, rfc))
        filas = cur.rowcount
        conn.commit()
        conn.close()
        return filas

