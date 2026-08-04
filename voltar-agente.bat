@echo off
title Voltar o Agente da Controladoria
cd /d "%~dp0"

echo ==================================================
echo    RELIGANDO O AGENTE NESTE COMPUTADOR
echo ==================================================
echo.

if exist "AGENTE-PAUSADO.txt" (
    del "AGENTE-PAUSADO.txt"
    echo    Pronto. O agente voltou a funcionar normalmente.
) else (
    echo    O agente ja estava funcionando normalmente.
)
echo.

powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*agente.py*' }) { exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo    A janela do agente nao esta aberta - abrindo agora...
    start "" "%~dp0agente-watchdog.bat"
    echo    Pronto, a janela do agente vai aparecer.
) else (
    echo    A janela do agente ja esta aberta.
)
echo.
pause
