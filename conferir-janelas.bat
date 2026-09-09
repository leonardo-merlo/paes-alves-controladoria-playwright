@echo off
title Diagnostico - Janelas do Agente
cd /d "%~dp0"

echo ==================================================
echo    CONFERINDO AS JANELAS DO AGENTE
echo ==================================================
echo.
echo Isto so confere e avisa o Leonardo. Nao muda nada no
echo seu computador.
echo.

venv\Scripts\python.exe diagnostico_inicializacao.py

echo.
pause
