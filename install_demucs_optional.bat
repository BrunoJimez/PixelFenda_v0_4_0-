@echo off
setlocal
cd /d "%~dp0"
echo PixelFenda v0.4.0 - ambiente opcional Demucs
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher ^(py^) nao encontrado.
  pause
  exit /b 1
)
if not exist .venv_demucs (
  py -3.13 -m venv .venv_demucs 2>nul || py -m venv .venv_demucs
)
call .venv_demucs\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -U demucs
if errorlevel 1 (
  echo.
  echo A instalacao basica do Demucs falhou. Consulte README_v0.4.0.md.
  pause
  exit /b 1
)
echo.
echo Demucs instalado no ambiente opcional .venv_demucs.
echo Para CUDA, instale uma versao PyTorch CUDA compativel com seu driver NVIDIA neste mesmo ambiente.
python -c "import demucs; print('Demucs: OK')"
pause
