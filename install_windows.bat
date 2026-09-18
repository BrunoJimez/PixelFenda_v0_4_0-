@echo off
setlocal
cd /d "%~dp0"
echo ========================================
echo PixelFenda v0.4.0 - Instalacao Windows
echo ========================================
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if errorlevel 1 goto :erro
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :erro

echo.
echo Instalacao concluida.
echo ModernGL tentara usar sua GPU NVIDIA automaticamente.
echo O FFmpeg usara NVENC quando disponivel.
echo Execute run_windows.bat para abrir o programa.
pause
exit /b 0
:erro
echo.
echo Falha durante a instalacao. Verifique Python 3.11+ (recomendado 3.13) e internet.
pause
exit /b 1
