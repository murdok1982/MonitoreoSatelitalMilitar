#!/bin/bash
# AEGIS-IMINT — Setup script para Linux/macOS
set -e

echo "=== AEGIS-IMINT Setup ==="
echo ""

# Verificar Python 3.9+
PYTHON=$(command -v python3 || command -v python)
PY_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[INFO] Python detectado: $PY_VERSION"

# Crear entorno virtual
echo "[INFO] Creando entorno virtual..."
$PYTHON -m venv venv
source venv/bin/activate

# Instalar dependencias
echo "[INFO] Instalando dependencias..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

# Crear directorios necesarios
echo "[INFO] Creando estructura de directorios..."
mkdir -p base_de_datos imagenes modelos logs

# Crear .env si no existe
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[INFO] Archivo .env creado desde .env.example."
    echo "       IMPORTANTE: Edita .env con tus credenciales antes de iniciar."
else
    echo "[INFO] .env ya existe, no se sobreescribe."
fi

echo ""
echo "=== Setup completado ==="
echo "Próximos pasos:"
echo "  1. Edita .env con tus credenciales de Sentinel Hub"
echo "  2. Descarga un modelo YOLO (ver modelos/README.md)"
echo "  3. (Opcional) Instala Ollama: https://ollama.ai/"
echo "  4. Ejecuta: source venv/bin/activate && streamlit run main.py"
echo "     o simplemente: bash start.sh"
