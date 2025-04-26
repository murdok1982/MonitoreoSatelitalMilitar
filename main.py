from config import INSTANCE_ID, CLIENT_ID, CLIENT_SECRET, EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO, YOLO_MODEL_PATH, UPDATE_INTERVAL, SENSIBILIDAD_ALERTA
import streamlit as st
import folium
from streamlit_folium import st_folium
import time
from sentinelhub import SHConfig, SentinelHubRequest, MimeType, CRS, BBox, DataCollection, bbox_to_dimensions
from ultralytics import YOLO
import sqlite3
import smtplib
from email.mime.text import MIMEText
import os
import cv2
import numpy as np


DB_NAME = 'detecciones.db'
# --- Crear/Conectar a la base de datos ---
conn = sqlite3.connect(DB_NAME)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS detecciones (timestamp TEXT, vehiculos_detectados INTEGER, imagen_path TEXT)''')
conn.commit()

# --- Funciones auxiliares ---
def descargar_imagen(bbox_coords):
    bbox = BBox(bbox=bbox_coords, crs=CRS.WGS84)
    request = SentinelHubRequest(
        evalscript="""
        function setup() {
          return {input: ["B04", "B03", "B02"], output: { bands: 3 }};
        }
        function evaluatePixel(sample) {
          return [sample.B04, sample.B03, sample.B02];
        }
        """,
        input_data=[SentinelHubRequest.input_data(
            data_collection=DataCollection.SENTINEL2_L1C,
            time_interval=('2025-04-24', '2025-04-25')
        )],
        responses=[SentinelHubRequest.output_response('default', MimeType.PNG)],
        bbox=bbox,
        size=bbox_to_dimensions(bbox, resolution=10),
        config=config
    )
    image = request.get_data(save_data=False)[0]
    os.makedirs('imagenes', exist_ok=True)
    path = f'imagenes/{int(time.time())}.png'
    cv2.imwrite(path, cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    return path


def detectar_vehiculos(imagen_path):
    results = model.predict(imagen_path)
    cantidad = sum([len(r.boxes) for r in results])
    return cantidad


def guardar_deteccion(vehiculos, imagen_path):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO detecciones (timestamp, vehiculos_detectados, imagen_path) VALUES (datetime('now'), ?, ?)", (vehiculos, imagen_path))
    conn.commit()
    conn.close()


def enviar_alerta(cantidad):
    remitente = 'gustavolobatoclara@gmail.com'
    destinatario = 'elmundo@gmail.com'
    password = 'tu_contraseña'

    mensaje = f'Alerta militar: {cantidad} vehículos detectados.'
    msg = MIMEText(mensaje)
    msg['Subject'] = 'ALERTA MILITAR'
    msg['From'] = remitente
    msg['To'] = destinatario

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(remitente, password)
    server.sendmail(remitente, destinatario, msg.as_string())
    server.quit()


def mostrar_trayectoria():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT timestamp, vehiculos_detectados FROM detecciones ORDER BY timestamp ASC")
    data = c.fetchall()
    conn.close()

    if data:
        st.line_chart({"Vehículos detectados": [d[1] for d in data]})

# --- Interfaz de usuario Streamlit ---
st.set_page_config(page_title="Sistema de Monitoreo Satelital Militar", layout="wide")
st.title("Sistema de Monitoreo Satelital Militar")

st.write("Marca un área de vigilancia en el mapa:")

m = folium.Map(location=[45.0, 15.0], zoom_start=4)
draw = st_folium(m, width=700, height=500)

if draw and draw['last_active_drawing']:
    st.success("Área marcada. Iniciando monitoreo...")

    zona = draw['last_active_drawing']['geometry']['coordinates'][0]
    coords = [min(x[0] for x in zona), min(x[1] for x in zona), max(x[0] for x in zona), max(x[1] for x in zona)]

    # Bucle automático
    while True:
        st.info("Actualizando zona...")
        imagen_path = descargar_imagen(coords)
        cantidad = detectar_vehiculos(imagen_path)
        guardar_deteccion(cantidad, imagen_path)

        st.image(imagen_path, caption=f"Vehículos detectados: {cantidad}")

        if cantidad >= SENSIBILIDAD_ALERTA:
            enviar_alerta(cantidad)
            st.error(f"ALERTA: {cantidad} vehículos detectados!")

        mostrar_trayectoria()

        st.info("Esperando 1 hora para la próxima actualización...")
        time.sleep(UPDATE_INTERVAL)

else:
    st.warning("Marca un área en el mapa para comenzar.")
