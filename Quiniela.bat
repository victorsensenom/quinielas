@echo off
rem Programa de la quiniela: doble clic para abrirlo.
rem La primera vez instala lo que necesita (numpy) y descarga datos de liga; tarda un poco.
cd /d "%~dp0"
set PY=
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1 && set PY=py -3
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1 && set PY=python
if not defined PY (
  echo.
  echo  No encuentro Python 3.12 o superior.
  echo  Instalalo gratis desde https://www.python.org/downloads/
  echo  marcando la casilla "Add python.exe to PATH", y vuelve a abrir este archivo.
  echo.
  pause
  exit /b 1
)
%PY% -c "import numpy" >nul 2>&1
if errorlevel 1 (
  echo Instalando numpy, solo la primera vez...
  %PY% -m pip install --user -r requirements.txt
  if errorlevel 1 (
    echo.
    echo  No se pudo instalar numpy. Comprueba la conexion a internet y vuelve a intentarlo.
    pause
    exit /b 1
  )
)
%PY% quiniela_app.py
if errorlevel 1 pause