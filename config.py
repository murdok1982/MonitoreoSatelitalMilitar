# config.py

# Sentinel Hub API keys
INSTANCE_ID = 'TU_INSTANCE_ID'
CLIENT_ID = 'TU_CLIENT_ID'
CLIENT_SECRET = 'TU_CLIENT_SECRET'

# Email settings for alert
EMAIL_FROM = 'gustavolobatoclara@gmail.com'
EMAIL_PASSWORD = 'contraseña'
EMAIL_TO = 'destinatario@gmail.com'

# Model path
YOLO_MODEL_PATH = 'modelos/yolov8_military.pt'

# Tasa de actualización y sensibilidad
UPDATE_INTERVAL = 3600  # 1 hora
SENSIBILIDAD_ALERTA = 10  # mínimo vehículos para alerta
