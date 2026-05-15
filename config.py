"""
AEGIS-IMINT — Configuración central
Carga todos los parámetros desde variables de entorno / archivo .env
NUNCA incluir credenciales directamente en este archivo.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── Sentinel Hub ──────────────────────────────────────────────────────────────
INSTANCE_ID = os.getenv('SENTINEL_INSTANCE_ID', '')
CLIENT_ID = os.getenv('SENTINEL_CLIENT_ID', '')
CLIENT_SECRET = os.getenv('SENTINEL_CLIENT_SECRET', '')
SENTINEL_RESOLUTION = int(os.getenv('SENTINEL_RESOLUTION', '10'))

# ─── Alertas Email ─────────────────────────────────────────────────────────────
EMAIL_FROM = os.getenv('EMAIL_FROM', '')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
EMAIL_TO = os.getenv('EMAIL_TO', '')
EMAIL_SMTP_HOST = os.getenv('EMAIL_SMTP_HOST', 'smtp.gmail.com')
EMAIL_SMTP_PORT = int(os.getenv('EMAIL_SMTP_PORT', '587'))

# ─── Alertas Telegram (alternativa) ────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# ─── Ollama LLM local ──────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llava:7b')

# ─── Modelo de detección YOLOv8 ────────────────────────────────────────────────
YOLO_MODEL_PATH = os.getenv('YOLO_MODEL_PATH', 'modelos/yolov8_military.pt')
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', '0.45'))

# ─── Parámetros de monitoreo ───────────────────────────────────────────────────
UPDATE_INTERVAL = int(os.getenv('UPDATE_INTERVAL', '3600'))
SENSIBILIDAD_ALERTA = int(os.getenv('SENSIBILIDAD_ALERTA', '5'))
MAX_IMAGE_AGE_DAYS = int(os.getenv('MAX_IMAGE_AGE_DAYS', '3'))

# ─── Almacenamiento y seguridad ────────────────────────────────────────────────
DB_PATH = os.getenv('DB_PATH', 'base_de_datos/detecciones.db')
IMAGES_DIR = os.getenv('IMAGES_DIR', 'imagenes')
FERNET_KEY_PATH = os.getenv('FERNET_KEY_PATH', 'base_de_datos/.fernet_key')
