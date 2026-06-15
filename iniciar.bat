@echo off
cd /d "%~dp0"

echo Iniciando controladoria...
echo O Chrome vai abrir nos sistemas. Faca login em cada aba.
echo A extracao comeca sozinha assim que o login for detectado.
echo.

call venv\Scripts\activate
python iniciar.py

echo.
pause
