@echo off
chcp 65001 >nul
title NeuralMant - RootMine
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo El entorno virtual no existe.
  echo Ejecuta primero INSTALAR_ROOTMINE.bat
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m streamlit run app.py
