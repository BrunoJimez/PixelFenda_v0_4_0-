@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Ambiente nao encontrado. Execute install_windows.bat primeiro.
  pause
  exit /b 1
)
.venv\Scripts\python.exe pixelfenda.py
if errorlevel 1 pause
