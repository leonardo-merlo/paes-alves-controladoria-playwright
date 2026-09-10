@echo off
title Controladoria — Agente Local

cd /d "%~dp0"

:: O Chrome NAO e mais aberto aqui. Removido em 10/09/2026.
::
:: Este script subia o Chrome no boot. Consequencia: quando o operador clicava
:: em "Abrir sistemas", o Chrome ja estava de pe e o codigo caia sempre no
:: caminho quente (iniciar.py, passo 1.4a), que abre cada aba por um PUT
:: /json/new com 5s de prazo e que falha EM SILENCIO. Na maquina do Leonardo,
:: em 09/09, nao havia watchdog: a porta 9222 estava fechada, o "Abrir
:: sistemas" caiu no caminho frio (1.4b, o proprio Chrome lancado com as URLs
:: na linha de comando) e o eProc TJMG extraiu os 35 processos — coisa que nao
:: acontecia desde 19/08. E a unica diferenca estrutural encontrada entre as
:: duas maquinas.
::
:: Nao faz falta: abrir_sistemas() sobe o Chrome sozinho quando ele nao esta
:: respondendo, e o faz pelo caminho mais confiavel dos dois.
::
:: Havia ainda um agravante com duas janelas do agente: a guarda era um
:: netstat seguido de start, sem exclusao nenhuma. Dois watchdogs subindo
:: juntos no boot consultavam a porta no mesmo segundo, os dois a viam fechada
:: e os dois lancavam Chrome — dois Chrome no mesmo perfil disputando a 9222,
:: que e o incidente ja registrado de 14/08 (as duas instancias escutam em
:: pilhas diferentes, 127.0.0.1 e ::1, e qual delas o agente encontra vira
:: sorteio).

:loop
echo [%date% %time%] Iniciando agente...
call venv\Scripts\activate.bat
python agente.py
echo [%date% %time%] Agente encerrou (codigo: %errorlevel%). Reiniciando em 10 segundos...
timeout /t 10 /nobreak >nul
goto loop
