@echo off
title Atualizar Sistema da Controladoria
cd /d "%~dp0"

echo ==================================================
echo    ATUALIZANDO O SISTEMA DA CONTROLADORIA
echo ==================================================
echo.

where git >nul 2>&1
if errorlevel 1 (
    echo [ERRO] O Git nao esta instalado nesta maquina.
    echo Avise o Leonardo - nao da para atualizar sem ele.
    echo.
    pause
    exit /b 1
)

if not exist ".git" (
    echo [ERRO] Esta pasta nao esta ligada ao GitHub.
    echo Avise o Leonardo.
    echo.
    pause
    exit /b 1
)

echo [1 de 3] Baixando a versao mais recente...
git fetch origin
if errorlevel 1 (
    echo.
    echo [ERRO] Nao consegui acessar o GitHub.
    echo Verifique se a internet esta funcionando e tente de novo.
    echo.
    pause
    exit /b 1
)

git reset --hard origin/master
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao aplicar a atualizacao. Avise o Leonardo.
    echo.
    pause
    exit /b 1
)
echo          Pronto.
echo.

echo [2 de 3] Conferindo os componentes...
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    python -m pip install -q -r requirements.txt
    echo          Pronto.
) else (
    echo          [AVISO] Ambiente Python nao encontrado nesta pasta.
    echo          Avise o Leonardo.
)
echo.

echo [3 de 3] Reiniciando o agente...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*agente.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo          Aguardando o agente voltar...
timeout /t 15 /nobreak >nul

powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*agente.py*' }) { exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo          O agente nao voltou sozinho - iniciando o vigia...
    start "" "%~dp0agente-watchdog.bat"
    echo          Vigia iniciado. A janela do agente vai abrir.
) else (
    echo          Agente reiniciado.
)
echo.

echo ==================================================
echo    ATUALIZADO COM SUCESSO
echo ==================================================
echo.
echo Pode fechar esta janela.
echo.
pause
