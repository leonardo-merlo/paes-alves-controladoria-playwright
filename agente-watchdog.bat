@echo off
title Controladoria — Agente Local

cd /d "%~dp0"

:: Inicia o Chrome com porta de debug e perfil dedicado (se ainda não estiver rodando)
netstat -an | findstr ":9222 " >nul 2>&1
if %errorlevel% neq 0 (
    echo Iniciando Chrome no modo extracao...
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
        --remote-debugging-port=9222 ^
        --user-data-dir="C:\ChromeControladoria"
    timeout /t 4 /nobreak >nul
)

:loop
echo [%date% %time%] Iniciando agente...
call venv\Scripts\activate.bat
python agente.py
echo [%date% %time%] Agente encerrou (codigo: %errorlevel%). Reiniciando em 10 segundos...
timeout /t 10 /nobreak >nul
goto loop
