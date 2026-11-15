@echo off
rem Launch UniBoard (installs dependencies on first run)
cd /d "%~dp0"
py -3 -m pip install -q -r requirements.txt 2>nul
start "UniBoard" /b pyw -3 "%~dp0uniboard.pyw"
