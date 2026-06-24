@echo off
title Controladoria - Instalacao (rodar uma vez)
cd /d "%~dp0"

echo ============================================
echo   Instalacao do Agente da Controladoria
echo   (rode este arquivo UMA vez, na primeira)
echo ============================================
echo.

REM --- Checar Python ---
python --version >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Python nao foi encontrado.
  echo Instale o Python de https://www.python.org/downloads/
  echo e marque "Add Python to PATH" na instalacao.
  echo.
  pause
  exit /b 1
)

echo [1/3] Criando ambiente virtual (venv)...
python -m venv venv
if errorlevel 1 ( echo [ERRO] Falha ao criar o venv. & pause & exit /b 1 )

echo [2/3] Instalando dependencias...
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 ( echo [ERRO] Falha ao instalar as dependencias. & pause & exit /b 1 )

echo [3/3] Instalando navegador do Playwright...
playwright install chromium

echo.
echo ============================================
echo   Pronto! So falta criar o arquivo .env
echo   (veja INSTALACAO.md, passo 6).
echo   Depois e so abrir o agente.bat.
echo ============================================
echo.
pause
