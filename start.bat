@echo off
REM AEGIS-IMINT — Inicio rapido Windows
echo [INFO] Iniciando AEGIS-IMINT en http://localhost:8501

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

if not exist .env (
    echo [WARN] No se encontro .env - ejecuta setup.bat primero.
)

streamlit run main.py --server.port 8501
