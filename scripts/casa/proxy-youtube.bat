@echo off
rem Proxy de YouTube para el servidor (docs/VPS.md, 3e). Doble clic; deja la ventana abierta.
cd /d "%~dp0..\.."
if exist .venv\Scripts\python.exe (.venv\Scripts\python.exe scripts\casa\proxy_youtube.py) else (python scripts\casa\proxy_youtube.py)
pause
