@echo off
TITLE Cisco SG300-28 Monitor
color 0B

echo =======================================================
echo    Iniciando Servidor Monitor Cisco SG300-28
echo =======================================================
echo.

REM Verifica si Python esta instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] No se encontro Python instalado en el sistema.
    echo Por favor instala Python 3.8+ desde python.org y agregalo al PATH.
    pause
    exit /b
)

REM Instala requerimientos si no existen
echo [INFO] Verificando dependencias...
pip install -r requirements.txt >nul 2>&1

REM Ejecuta el servidor Flask
echo.
echo [INFO] Servidor web iniciado en http://localhost:5000
echo [INFO] Presiona CTRL+C en esta ventana para detener.
echo.

python app.py
pause
