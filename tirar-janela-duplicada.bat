@echo off
title Controladoria - Tirar a janela duplicada
cd /d "%~dp0"

echo ==================================================
echo    TIRAR A JANELA DUPLICADA DO AGENTE
echo ==================================================
echo.
echo O agente esta configurado para abrir DUAS vezes quando
echo voce liga o computador. Por isso aparecem duas janelas
echo pretas. Isto desativa uma delas.
echo.
echo Nada e apagado: o atalho fica guardado nesta pasta, em
echo inicializacao-desativada, e da para voltar atras.
echo.
pause

venv\Scripts\python.exe desativar_inicializacao_duplicada.py

echo.
pause
