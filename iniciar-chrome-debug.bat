@echo off
title Chrome — Modo Extração

:: Verifica se Chrome já está rodando com a porta de debug
netstat -an | findstr "9222" >nul 2>&1
if %errorlevel% == 0 (
    echo Chrome com debug ja esta rodando na porta 9222.
    timeout /t 2 /nobreak >nul
    exit /b 0
)

:: Inicia o Chrome com porta de debug ativa
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

echo Chrome iniciado no modo extracao.
echo Faca login nos sistemas judiciais antes de clicar em "Iniciar Extracao".
timeout /t 3 /nobreak >nul
