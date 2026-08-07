@echo off
chcp 65001 >nul
title Instalación NeuralMant - RootMine
cd /d "%~dp0"
echo =============================================
echo   NEURALMANT - ROOTMINE | INSTALACION
 echo =============================================
if not exist .venv (
  echo Creando entorno virtual...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .streamlit\secrets.toml copy .streamlit\secrets.toml.example .streamlit\secrets.toml >nul
echo.
echo Instalacion terminada.
echo Abre .streamlit\secrets.toml y agrega tu clave de Gemini u OpenAI.
pause
