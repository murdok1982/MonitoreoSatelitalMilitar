@echo off
REM start_api.bat — Launch the AEGIS-IMINT FastAPI REST server (Windows)

call venv\Scripts\activate.bat 2>nul || echo [WARN] No venv found, using system Python

set PORT=%API_PORT%
if "%PORT%"=="" set PORT=8502

echo ==========================================
echo   AEGIS-IMINT REST API
echo   Port    : %PORT%
echo   Docs    : http://localhost:%PORT%/api/docs
echo   ReDoc   : http://localhost:%PORT%/api/redoc
echo ==========================================

python -m api.run
