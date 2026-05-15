import sqlite3
import os
from datetime import datetime
from config import DB_PATH


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS detecciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        vehiculos_detectados INTEGER NOT NULL,
        clases_detectadas TEXT,
        imagen_path TEXT,
        lat_min REAL, lon_min REAL, lat_max REAL, lon_max REAL,
        amenaza_nivel TEXT,
        informe_llm TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS zonas_vigilancia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        coords TEXT NOT NULL,
        activa INTEGER DEFAULT 1,
        creada TEXT NOT NULL
    )''')
    conn.commit()
    conn.close()


def guardar_deteccion(vehiculos: int, imagen_path: str, coords: list,
                      clases: str = '', amenaza: str = '', informe: str = ''):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    lat_min = coords[1] if len(coords) >= 4 else 0
    lon_min = coords[0] if len(coords) >= 4 else 0
    lat_max = coords[3] if len(coords) >= 4 else 0
    lon_max = coords[2] if len(coords) >= 4 else 0
    c.execute("""INSERT INTO detecciones
        (timestamp, vehiculos_detectados, clases_detectadas, imagen_path, lat_min, lon_min, lat_max, lon_max, amenaza_nivel, informe_llm)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (datetime.utcnow().isoformat(), vehiculos, clases, imagen_path,
               lat_min, lon_min, lat_max, lon_max, amenaza, informe))
    conn.commit()
    conn.close()


def obtener_historial(limit: int = 100) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT timestamp, vehiculos_detectados, amenaza_nivel, imagen_path, informe_llm "
        "FROM detecciones ORDER BY timestamp DESC LIMIT ?",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return rows


def obtener_tendencia() -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT timestamp, vehiculos_detectados FROM detecciones ORDER BY timestamp ASC")
    rows = c.fetchall()
    conn.close()
    return rows


def guardar_zona(nombre: str, coords: list):
    import json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO zonas_vigilancia (nombre, coords, creada) VALUES (?, ?, ?)",
        (nombre, json.dumps(coords), datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def obtener_zonas() -> list:
    import json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, nombre, coords, activa FROM zonas_vigilancia WHERE activa=1")
    rows = c.fetchall()
    conn.close()
    return [(r[0], r[1], json.loads(r[2]), r[3]) for r in rows]
