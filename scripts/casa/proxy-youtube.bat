@echo off
rem Proxy de YouTube para el servidor (docs/VPS.md, 3e). Doble clic; deja la ventana abierta.
rem Si se cierra o Tailscale aun no esta conectado (al encender), vuelve a arrancar solo a los 15 s.
title Proxy de YouTube
set "HERE=%~dp0"
:loop
if exist "%HERE%..\..\.venv\Scripts\python.exe" (
  "%HERE%..\..\.venv\Scripts\python.exe" "%HERE%proxy_youtube.py"
) else (
  python "%HERE%proxy_youtube.py"
)
echo.
echo El proxy se ha parado. Vuelvo a arrancarlo en 15 s (cierra esta ventana para pararlo del todo).
timeout /t 15 /nobreak >nul
goto loop
