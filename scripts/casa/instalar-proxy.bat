@echo off
rem Deja este equipo listo como proxy de YouTube 24/7 (docs/VPS.md, 3e). Boton derecho -> Ejecutar como administrador.
rem 1) arranca el proxy al iniciar sesion, minimizado; 2) enchufado no se suspende ni hiberna, ni al cerrar la tapa;
rem 3) el firewall deja entrar al puerto 8899 SOLO desde Tailscale (100.64.0.0/10), en cualquier red (wifi, movil...).
net session >nul 2>&1
if errorlevel 1 (
  echo Abre este archivo con boton derecho -^> "Ejecutar como administrador".
  pause
  exit /b 1
)
where python >nul 2>&1
if errorlevel 1 if not exist "%~dp0..\..\.venv\Scripts\python.exe" (
  echo Falta Python: instalalo desde python.org marcando "Add python.exe to PATH" y vuelve a abrir esto.
  pause
  exit /b 1
)
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
> "%STARTUP%\proxy-youtube.bat" echo @start "Proxy de YouTube" /min "%~dp0proxy-youtube.bat"
echo [1/3] Arrancara solo al iniciar sesion: %STARTUP%\proxy-youtube.bat
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setactive SCHEME_CURRENT
echo [2/3] Enchufado: no se suspende, no hiberna y cerrar la tapa no hace nada.
netsh advfirewall firewall delete rule name="Proxy YouTube (Tailscale)" >nul 2>&1
netsh advfirewall firewall add rule name="Proxy YouTube (Tailscale)" dir=in action=allow protocol=TCP localport=8899 remoteip=100.64.0.0/10 profile=any >nul
echo [3/3] Firewall: puerto 8899 abierto solo para tus equipos de Tailscale.
echo.
echo Listo. Ahora arranco el proxy: apunta la linea http://100.x.y.z:8899 que sale y pasasela al servidor.
start "Proxy de YouTube" "%~dp0proxy-youtube.bat"
pause
