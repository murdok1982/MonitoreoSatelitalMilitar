@echo off
REM AEGIS-IMINT — Setup script para Windows
echo === AEGIS-IMINT Setup ===
echo.

REM Crear entorno virtual
echo [INFO] Creando entorno virtual...
python -m venv venv
if errorlevel 1 (
    echo [ERROR] No se encontro Python. Instala Python 3.9+ desde https://python.org
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

REM Instalar dependencias
echo [INFO] Instalando dependencias...
pip install --upgrade pip
pip install -r requirements.txt

REM Crear directorios
echo [INFO] Creando estructura de directorios...
if not exist base_de_datos mkdir base_de_datos
if not exist imagenes mkdir imagenes
if not exist modelos mkdir modelos
if not exist logs mkdir logs

REM Crear .env si no existe
if not exist .env (
    copy .env.example .env
    echo [INFO] Archivo .env creado desde .env.example.
    echo        IMPORTANTE: Edita .env con tus credenciales antes de iniciar.
) else (
    echo [INFO] .env ya existe, no se sobreescribe.
)

echo.
echo === Setup completado ===
echo Proximos pasos:
echo   1. Edita .env con tus credenciales de Sentinel Hub
echo   2. Descarga un modelo YOLO (ver modelos\README.md)
echo   3. Ejecuta: start.bat
pause
