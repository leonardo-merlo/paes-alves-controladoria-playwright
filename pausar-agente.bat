@echo off
title Pausar o Agente da Controladoria
cd /d "%~dp0"

echo ==================================================
echo    PAUSANDO O AGENTE NESTE COMPUTADOR
echo ==================================================
echo.

echo Pausado em %date% %time% > "AGENTE-PAUSADO.txt"

if not exist "AGENTE-PAUSADO.txt" (
    echo [ERRO] Nao consegui criar o arquivo de pausa.
    echo Avise o Leonardo.
    echo.
    pause
    exit /b 1
)

echo    Pronto. O agente NAO vai mais rodar extracoes neste computador.
echo.
echo    A janela do agente pode continuar aberta, e o computador pode
echo    ser reiniciado - ele continua pausado do mesmo jeito.
echo.
echo    Para voltar ao normal: clique em  voltar-agente.bat
echo.
pause
