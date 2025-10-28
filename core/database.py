# ===========================================================
# core/database.py — SCIL 2025
# Manejador central de base de datos SQLite
# ===========================================================

import sqlite3
import json
import hashlib
from pathlib import Path


class DatabaseManager:
    def __init__(self, db_path="scil.db"):
        self.db_path = db_path
        print(f"📂 Base de datos en uso: {Path(self.db_path).resolve()}")
        self._init_db()

    # -------------------------------------------------------
    # Conexión
    # -------------------------------------------------------
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------
    # Inicialización de tablas
    # -------------------------------------------------------
    def _init_db(self):
        conn = self._connect()
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

            CREATE TABLE IF NOT EXISTS solventaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfc TEXT NOT NULL,
                ente TEXT NOT NULL,
                estado TEXT NOT NULL,
                comentario TEXT,
                actualizado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(rfc, ente)
            );

            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                usuario TEXT UNIQUE NOT NULL,
                clave TEXT NOT NULL,
                entes TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clave TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                siglas TEXT,
                clasificacion TEXT,
                ambito TEXT,
                activo INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS municipios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clave TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                siglas TEXT,
                clasificacion TEXT,
                ambito TEXT DEFAULT 'MUNICIPAL',
                activo INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        conn.close()
        print(f"✅ Tablas listas en {self.db_path}")

    # -------------------------------------------------------
    # Poblar datos base
    # -------------------------------------------------------
    def poblar_datos_iniciales(self):
        conn = self._connect()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM usuarios")
        if cur.fetchone()[0] == 0:
            base = [
                ("C.P. Odilia Cuamatzi Bautista", "odilia",
                 hashlib.sha256("odilia2025".encode()).hexdigest(), "TODOS"),
                ("C.P. Luis Felipe Camilo Fuentes", "felipe",
                 hashlib.sha256("felipe2025".encode()).hexdigest(), "TODOS"),
            ]
            cur.executemany(
                "INSERT INTO usuarios (nombre, usuario, clave, entes) VALUES (?, ?, ?, ?)", base)
            print("👥 Usuarios base insertados")

        cur.execute("SELECT COUNT(*) FROM entes")
        if cur.fetchone()[0] == 0:
            entes = [
                ("ENTE_00001", "Secretaría de Gobierno", "SEGOB", "Estatal", "Estatal"),
                ("ENTE_00002", "Secretaría de Finanzas", "SEFIN", "Estatal", "Estatal"),
                ("ENTE_00003", "Secretaría de Educación Pública", "SEPE", "Estatal", "Estatal"),
            ]
            cur.executemany(
                "INSERT INTO entes (clave, nombre, siglas, clasificacion, ambito) VALUES (?,?,?,?,?)", entes)
            print("🏛️ Entes base insertados")

        conn.commit()
        conn.close()

    # -------------------------------------------------------
    # Catálogos
    # -------------------------------------------------------
    def listar_entes(self, solo_activos=True):
        conn = self._connect()
        cur = conn.cursor()
        q = "SELECT clave, nombre, siglas, clasificacion, ambito FROM entes"
        if solo_activos:
            q += " WHERE activo=1"
        q += " ORDER BY nombre"
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
            ORDER BY nombre
        """)
        data = [dict(r) for r in cur.fetchall()]
        conn.close()
        return data

    # -------------------------------------------------------
    # Mapas rápidos de entes
    # -------------------------------------------------------
    def get_mapa_siglas(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT siglas, clave FROM entes WHERE activo=1")
        mapa = {}
        for sigla, clave in cur.fetchall():
            if sigla:
                mapa[self._sanitize(sigla)] = clave
        conn.close()
        return mapa

    def get_mapa_claves_inverso(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT clave, siglas, nombre FROM entes WHERE activo=1")
        mapa = {}
        for clave, sigla, nombre in cur.fetchall():
            if sigla:
                mapa[self._sanitize(clave)] = self._sanitize(sigla)
            elif nombre:
                mapa[self._sanitize(clave)] = self._sanitize(nombre)
        conn.close()
        return mapa

    # -------------------------------------------------------
    # Utilidades
    # -------------------------------------------------------
    def _hash_text(self, text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _sanitize(self, s):
        if not s:
            return ""
        s = str(s).strip().upper()
        for a, b in zip("ÁÉÍÓÚ", "AEIOU"):
            s = s.replace(a, b)
        return s

    # -------------------------------------------------------
    # Normalización
    # -------------------------------------------------------
    def normalizar_ente(self, valor):
        if not valor:
            return None
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT nombre FROM entes
            WHERE UPPER(siglas)=UPPER(?) OR UPPER(clave)=UPPER(?) OR UPPER(nombre)=UPPER(?)
            LIMIT 1
        """, (valor, valor, valor))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    def normalizar_ente_clave(self, valor):
        if not valor:
            return None
        val = self._sanitize(valor)
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
        existentes = {r[0] for r in cur.fetchall() if r[0]}
        conn.close()

        nuevos_validos, repetidos = [], []
        for r in nuevos:
            texto = json.dumps(r, sort_keys=True, ensure_ascii=False)
            h = self._hash_text(texto)
            if h not in existentes:
                r["hash_firma"] = h
                nuevos_validos.append(r)
            else:
                repetidos.append(r)
        return nuevos_validos, repetidos, len(repetidos)

    def guardar_resultados(self, resultados):
        if not resultados:
            return 0
        conn = self._connect()
        cur = conn.cursor()
        count = 0
        for r in resultados:
            try:
                cur.execute("""
                    INSERT INTO laboral (tipo_analisis, rfc, datos, hash_firma)
                    VALUES (?, ?, ?, ?)
                """, (
                    r.get("tipo_patron", "GENERAL"),
                    r.get("rfc", ""),
                    json.dumps(r, ensure_ascii=False),
                    r["hash_firma"]
                ))
                count += 1
            except sqlite3.IntegrityError:
                continue
        conn.commit()
        conn.close()
        return count

    def obtener_resultados_paginados(self, tabla="laboral", filtro=None, pagina=1, limite=10000):
        conn = self._connect()
        cur = conn.cursor()
        offset = (pagina - 1) * limite
        if filtro:
            cur.execute(
                f"SELECT datos FROM {tabla} WHERE datos LIKE ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (f"%{filtro}%", limite, offset))
        else:
            cur.execute(
                f"SELECT datos FROM {tabla} ORDER BY id DESC LIMIT ? OFFSET ?",
                (limite, offset))
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
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT datos FROM laboral
            WHERE UPPER(json_extract(datos, '$.rfc')) = UPPER(?)
            ORDER BY id DESC
        """, (rfc,))
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return None

        registros = []
        for row in rows:
            try:
                registros.append(json.loads(row[0]))
            except Exception:
                continue
        if not registros:
            return None

        vistos, registros_unicos = set(), []
        for r in registros:
            for reg in r.get("registros", []):
                clave = (reg.get("ente"), reg.get("puesto"),
                         reg.get("monto"), reg.get("fecha_ingreso"), reg.get("fecha_egreso"))
                if clave not in vistos:
                    vistos.add(clave)
                    registros_unicos.append(reg)

        return {
            "rfc": rfc,
            "nombre": registros[0].get("nombre", ""),
            "entes": list({e for r in registros for e in r.get("entes", [])}),
            "registros": registros_unicos,
            "estado": registros[-1].get("estado", "Sin valoración"),
            "solventacion": registros[-1].get("solventacion", "")
        }

    # -------------------------------------------------------
    # Solventaciones
    # -------------------------------------------------------
    def get_solventaciones_por_rfc(self, rfc):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT ente, estado, comentario FROM solventaciones WHERE rfc=?
        """, (rfc,))
        data = {}
        for row in cur.fetchall():
            data[row["ente"]] = {
                "estado": row["estado"],
                "comentario": row["comentario"]
            }
        conn.close()
        return data

    def actualizar_solventacion(self, rfc, estado, comentario, ente="GENERAL"):
        if not ente:
            ente = "GENERAL"
        if not estado:
            estado = "Sin valoración"

        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO solventaciones (rfc, ente, estado, comentario)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(rfc, ente) DO UPDATE SET
                estado=excluded.estado,
                comentario=excluded.comentario,
                actualizado=CURRENT_TIMESTAMP
        """, (rfc, ente, estado, comentario))
        filas = cur.rowcount
        conn.commit()
        conn.close()
        return filas

    # -------------------------------------------------------
    # Estado por RFC y Ente
    # -------------------------------------------------------
    def get_estado_rfc_ente(self, rfc, ente_clave):
        if not rfc or not ente_clave:
            return None
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT estado FROM solventaciones
            WHERE rfc = ? AND ente = ?
            ORDER BY actualizado DESC
            LIMIT 1
        """, (rfc, ente_clave))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    # -------------------------------------------------------
    # Autenticación de usuarios
    # -------------------------------------------------------
    def get_usuario(self, usuario, clave):
        if not usuario or not clave:
            return None
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT nombre, usuario, clave, entes
            FROM usuarios
            WHERE LOWER(usuario)=LOWER(?)
            LIMIT 1
        """, (usuario,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None

        clave_hash = hashlib.sha256(clave.encode()).hexdigest()
        if clave_hash != row["clave"]:
            return None

        entes = [e.strip().upper() for e in (row["entes"] or "").split(",") if e.strip()]
        return {
            "nombre": row["nombre"],
            "usuario": row["usuario"],
            "entes": entes
        }


# -----------------------------------------------------------
# Ejecución directa
# -----------------------------------------------------------
if __name__ == "__main__":
    db = DatabaseManager("scil.db")
    db.poblar_datos_iniciales()

