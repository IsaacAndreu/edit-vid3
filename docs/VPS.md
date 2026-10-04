# Prueba en una VPS (un mes)

Objetivo: saber con datos si una VPS descarga de YouTube lo bastante bien para 2-5 vídeos al día. El resto del
programa (Whisper, CLIP, Remotion, ffmpeg) no depende de YouTube; la descarga está aislada en
`pipeline/sourcing/youtube.py`, así que si YouTube cambia solo hay que tocar esa pieza.

## 1. Máquina

- Ubuntu 24.04, mensual y sin permanencia, que permita **subir de tamaño sin reinstalar**.
- Empieza con **4 vCPU / 8 GB** si vas a hacer 2-3 vídeos al día sin prisa; sube a **8 vCPU / 16 GB** si un vídeo
  tarda demasiado (lo verás en `out/<vídeo>/diagnostico.md`, «Tiempo por etapa»). Sin gráfica: Whisper, CLIP y el
  render van por CPU.
- 100 GB de disco como mínimo (vídeos descargados y caché).

## 2. Instalar

```bash
git clone -b claude/pensive-bell-5pi66r https://github.com/IsaacAndreu/edit-vid3.git
cd edit-vid3
bash scripts/vps/setup-ubuntu.sh
```

Instala Python (en `.venv`), ffmpeg, Node, Deno, las librerías de Chrome para Remotion, Docker y el **PO Token
Provider** (`bgutil-ytdlp-pot-provider`: el plugin de yt-dlp + su servidor en Docker en `127.0.0.1:4416`), y crea
`config.local.yaml` (solo de esta máquina, fuera de git):

```yaml
sourcing:
  youtube:
    cookies: fallback      # sin cuenta; una de reserva SOLO si un vídeo la pide (edad, miembros, privado)
    po_token: on           # PO Token + cliente mweb (guía de yt-dlp); avisa si falta
```

Copia a mano, **nunca por git**: `.env` (tus claves) y, si quieres cuentas de reserva, sus cookies en
`~/.config/edit-vid3/cookies/*.txt`. `cookies: never` las ignora del todo.

## 3. Probar, de menos a más

```bash
. .venv/bin/activate
python main.py --probar-youtube          # 1 minuto: ¿descarga?
python main.py --slug <un vídeo>         # un vídeo completo
bash scripts/vps/install-service.sh      # y desde aquí, todo el rato
```

`install-service.sh` deja `python main.py --vigilar` como servicio del sistema: en cuanto hay un vídeo pendiente en
`materiales/` (de cualquier canal) lo hace; si no hay nada, vuelve a mirar cada 5 minutos. Arranca solo al encender
la VPS y se reinicia si algo lo tumba. Un vídeo que falla **no se repite en bucle** (gastaría API): espera a que
cambies sus archivos o a que pasen 6 horas (`watch.retry_hours`). Entre vídeo y vídeo hace `git pull` y, si hay código
nuevo, se reinicia con él. Ver lo que hace: `journalctl -u edit-vid3 -f`; parar: `sudo systemctl stop edit-vid3`.
(`install-cron.sh` sigue ahí si prefieres una hora fija.)

Al empezar cada fase que usa YouTube verás `YouTube: sin cuenta…` y `PO Token Provider activo · clientes default, …,
mweb`. Si no sale lo segundo: `docker ps` (¿está `bgutil-provider`?) y `curl http://127.0.0.1:4416/ping`.

## 3b. Estudio web con contraseña (sin comandos)

```bash
echo 'WEB_PASSWORD=una-contraseña-larga-de-verdad' >> .env
bash scripts/vps/install-web.sh            # o: bash scripts/vps/install-web.sh mi-dominio.com
```

Queda en `https://<tu-ip-con-guiones>.sslip.io` (HTTPS gratis con Let's Encrypt, sin comprar dominio): subir guion y
voz, ver en qué etapa va cada vídeo, descargarlo, revisar errores, competencia y tu canal. El estudio escucha solo en
`127.0.0.1:8080` y Caddy pone el HTTPS delante; fuera de la VPS siempre pide la contraseña (sesión de 30 días; tras
10 intentos fallidos en 10 minutos se bloquea un rato). Registro: `journalctl -u edit-vid3-web -f`.

**Gasto**: en el estudio → Ajustes, «Límite de gasto de API al día» (o `budget.daily_usd`). Al llegar, el servidor no
empieza más vídeos hasta el día siguiente (no cuenta como error).

## 3c. Seguridad del servidor

`setup-ubuntu.sh` ya deja: cortafuegos `ufw` (solo SSH, 80 y 443), `fail2ban` (bloquea IPs que prueban contraseñas
de SSH) y parches de seguridad automáticos. Además, recomendado:

1. Entra con **clave SSH** en vez de contraseña: en tu PC `ssh-keygen -t ed25519` y `ssh-copy-id usuario@ip`
   (en Windows: `type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh usuario@ip "cat >> ~/.ssh/authorized_keys"`).
2. Cuando entres sin contraseña, desactívalas: en `/etc/ssh/sshd_config` pon `PasswordAuthentication no` y
   `PermitRootLogin no`, y `sudo systemctl restart ssh` (deja otra sesión abierta mientras pruebas).
3. `.env` solo para tu usuario: `chmod 600 .env`.

## 4. Métricas (lo que decide)

Cada petición a YouTube queda en `work/<vídeo>/youtube_downloads.jsonl` (qué se pidió, si fue bien, el error —403,
«no eres un bot», 429, necesita cuenta—, intentos, con o sin cuenta, clientes, PO Token, segundos, MB y MB/s). Cada
`diagnostico.md` trae el resumen («YouTube: cómo respondió») y un aviso si más del 5 % son 403 o bloqueos. Para la
semana entera:

```bash
python main.py --youtube-stats 7         # → out/_youtube_stats.md, total y por vídeo
```

Tras una o dos semanas: si los fallidos se quedan en un pequeño porcentaje y sin bloqueos, la VPS sirve. Si aparecen
muchos 403 / «no eres un bot», la IP o la configuración no aguantan este volumen: antes de pagar nada más, prueba
`cookies: fallback` frente a `never`, y comprueba el PO Token. No hace falta rotar cuentas ni proxies para empezar.

## 4b. Disco y recursos

- Cada `diagnostico.md` trae, por etapa, el tiempo, la **RAM máxima** y la **CPU máxima / media** de la máquina: así
  ves si Remotion (render), Whisper (align) o CLIP (analysis) se comen los 16 GB. Si la RAM roza el total, baja
  `render.concurrency` en `config.local.yaml`; si la CPU media es baja, súbelo.
- `cleanup: {after_video: true, cache_days: 14}` (ya en el `config.local.yaml` de la VPS): al terminar un vídeo se
  borran sus temporales pesados (~3 GB: render, clips, proxies del editor) y se quedan el vídeo, los planes, los logs y
  el diagnóstico; las descargas de `cache/` sin usar en 14 días también se borran antes de cada cola. Para rehacer un
  vídeo ya limpiado, vuelve a descargar lo que necesite.

## 5. Avisos

- Un PO Token **no garantiza** que YouTube no bloquee; solo hace las peticiones como YouTube espera de ese cliente.
- Usar una cuenta con yt-dlp puede acabar en bloqueo temporal o permanente de esa cuenta: por eso aquí es solo de
  reserva.
- Las condiciones de YouTube restringen descargar y reutilizar contenido sin permiso; el riesgo de reclamaciones de
  usar clips de terceros es el mismo en casa o en un servidor (ver el aviso por canal en el informe de QA).
