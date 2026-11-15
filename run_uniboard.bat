@echo off
rem Запуск UniBoard (устанавливает зависимости при первом запуске)
cd /d "%~dp0"
py -3 -m pip install -q -r requirements.txt 2>nul
start "UniBoard" /b pyw -3 "%~dp0uniboard.pyw"
