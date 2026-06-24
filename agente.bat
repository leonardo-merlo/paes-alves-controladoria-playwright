@echo off
title Controladoria - Agente Local
cd /d "%~dp0"

call venv\Scripts\activate

:loop
echo.
echo [%date% %time%] Iniciando agente da controladoria...
python -u agente.py
echo.
echo [%date% %time%] O agente encerrou. Reiniciando em 5s... (feche esta janela para parar)
timeout /t 5 /nobreak >nul
goto loop
