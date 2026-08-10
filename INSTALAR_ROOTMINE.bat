@echo off
chcp 65001 >nul
title Instalación NeuralMant - RootMine v4.0
cd /d "%~dp0"
echo =============================================
echo   NEURALMANT - ROOTMINE v4.0 ^| INSTALACION
echo =============================================
where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo ERROR: Python no esta disponible en PATH.
  echo Instala Python 3.11 o superior y marca Add Python to PATH.
  pause
  exit /b 1
)
if not exist .venv (
  echo Creando entorno virtual .venv...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if not exist .streamlit\secrets.toml copy .streamlit\secrets.toml.example .streamlit\secrets.toml >nul
echo.
echo Instalacion terminada correctamente.
echo.
echo IMPORTANTE:
echo 1. Abre .streamlit\secrets.toml
 echo 2. Configura una sola GEMINI_API_KEY para toda la aplicacion.
echo 3. El correo externo esta desactivado; RootMine usa notificaciones internas.
echo.
pause
