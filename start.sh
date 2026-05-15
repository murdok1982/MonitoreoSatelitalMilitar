#!/bin/bash
# AEGIS-IMINT — Inicio rápido Linux/macOS
set -e

# Activar entorno virtual si existe
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Verificar .env
if [ ! -f .env ]; then
    echo "[WARN] No se encontró .env — ejecuta setup.sh primero."
fi

echo "[INFO] Iniciando AEGIS-IMINT en http://localhost:8501"
streamlit run main.py \
    --server.port 8501 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection true
