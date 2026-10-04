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

## 3b2. Bot de Telegram

Con Telegram conectado (estudio → Ajustes → Avisos al móvil), `install-service.sh` deja también el servicio
`edit-vid3-bot` (si lo conectas después: `sudo systemctl enable --now edit-vid3-bot`). Escríbele al bot:

- `/estado` — qué vídeo está haciendo y en qué etapa, la cola, el gasto de hoy y el disco libre.
- `/gasto` — gasto de hoy, de la última hora y de 7 días, por vídeo y por servicio.
- `/videos`, `/errores`, `/video <nombre>`, `/youtube` (cómo respondió YouTube en 24 h).
- `/pausa`, `/seguir`, `/limite <dólares>`, `/reintentar <nombre>`.

Cada hora manda un parte (qué hace, terminados y errores de esa hora, gasto, peticiones a YouTube); `bot.quiet_hours`
en config.local.yaml para silenciar la noche. Además avisa al momento si el vigilante deja de dar señales, si se llega
al límite de gasto o si el disco se llena; cada vídeo que falla manda su propio mensaje. Solo contesta a tu chat.
Registro: `journalctl -u edit-vid3-bot -f`.

**Miniaturas:** `miniaturas: {enabled: false}` (por defecto): no se generan; el aviso al móvil lleva un fotograma del
vídeo. `true` para volver a las 3 miniaturas automáticas.

## 3c. Seguridad del servidor

`setup-ubuntu.sh` ya deja: cortafuegos `ufw` (solo SSH, 80 y 443), `fail2ban` (bloquea IPs que prueban contraseñas
de SSH) y parches de seguridad automáticos. Además, recomendado:

1. Entra con **clave SSH** en vez de contraseña: en tu PC `ssh-keygen -t ed25519` y `ssh-copy-id usuario@ip`
   (en Windows: `type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh usuario@ip "cat >> ~/.ssh/authorized_keys"`).
2. Cuando entres sin contraseña, desactívalas: en `/etc/ssh/sshd_config` pon `PasswordAuthentication no` y
   `PermitRootLogin no`, y `sudo systemctl restart ssh` (deja otra sesión abierta mientras pruebas).
3. `.env` solo para tu usuario: `chmod 600 .env`.

## 3d. Si YouTube pide cuenta al servidor

`--probar-youtube` dice «YouTube pide cuenta a ESTA IP» cuando la IP del servidor (de centro de datos) recibe el
control «Sign in to confirm you're not a bot» con todos los clientes, con y sin PO Token. Desde aquí solo se puede
descargar con cookies de una **cuenta secundaria** (nunca la de tu canal: yt-dlp con cuenta puede acabar en bloqueo de
esa cuenta).

1. Crea 1-3 cuentas de Google nuevas solo para esto.
2. Por cada una, en tu PC: ventana **privada** → entra en YouTube con esa cuenta → abre
   `https://www.youtube.com/robots.txt` → exporta las cookies con la extensión «Get cookies.txt LOCALLY» →
   **cierra la ventana privada sin cerrar sesión** (cerrar sesión invalida las cookies).
3. Súbelas (PowerShell): `scp cuenta1.txt root@<ip>:/opt/video-app/edit-vid3/cookies/` (la carpeta `cookies/` del
   proyecto no va a git).
4. En `config.local.yaml`: `cookies: rotate` (todas las peticiones con cuenta, por turnos; en esta IP todas la
   necesitan) y repite `python main.py --probar-youtube`.

Con `cookies: fallback` (el de por defecto) también funciona: cada petición que recibe el control «no eres un bot» se
repite con una cuenta, pero gasta una petición sin cuenta antes de cada una.

## 3e. YouTube por la conexión de casa (sin cuentas)

Si YouTube bloquea la IP del servidor, la alternativa a las cookies: el servidor descarga de YouTube **a través de tu
PC de casa**, donde YouTube no pide cuenta. Todo lo demás (IA, Whisper, CLIP, render) sigue en el servidor. El PC
solo pasa bytes: casi no usa CPU y puedes seguir usándolo. Va por **Tailscale** (red privada gratuita entre tus
equipos): el proxy no queda abierto a internet y solo deja pasar direcciones de YouTube.

1. **Tailscale en los dos:** en el PC, instálalo desde tailscale.com/download e inicia sesión. En el servidor:
   `curl -fsSL https://tailscale.com/install.sh | sh && tailscale up` (abre el enlace que sale y entra con la misma
   cuenta).
2. **En el PC** (tras `git pull`): doble clic en `scripts\casa\proxy-youtube.bat`. Si Windows pregunta, permite el
   acceso en redes privadas. La ventana dice la línea para el servidor (`http://100.x.y.z:8899`). Déjala abierta.
3. **En el servidor**, en `config.local.yaml`, dentro de `sourcing: youtube:` añade `proxy: http://100.x.y.z:8899`
   y prueba: `python main.py --probar-youtube` (sale «por la conexión de casa (proxy)»).
4. Que arranque solo: `Win+R` → `shell:startup` → crea ahí un acceso directo a `proxy-youtube.bat`, y que el PC no
   se suspenda (LOCAL.md, «Que el PC no se duerma»).

Con proxy no se usa PO Token (YouTube ve la IP de casa, que no lo necesita). Gasta de tu conexión ~1-2 GB por vídeo
(baja de YouTube y sube al servidor). Si el PC está apagado, la cola no arranca y te avisa por Telegram.

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

**Vídeos ya subidos a YouTube** (`cleanup.published_days: 7`, `min_free_gb: 30`): un vídeo marcado como subido
pierde a los 7 días su vídeo final, las previas, los Shorts y sus clips de trabajo (~2-4 GB), y conserva títulos,
miniaturas, diagnóstico, registro y las imágenes de «Errores». Se marca solo si el título aparece en tu canal (tu canal
en el estudio → Ajustes; se mira cada pocas horas) o a mano en el estudio → el vídeo → «Ya está subido a YouTube». Si
quedan menos de 30 GB libres se borran antes (los subidos más antiguos primero) y, si aun así falta, te avisa por
Telegram. Nunca se borra un vídeo que no esté marcado como subido, y un vídeo limpiado no se vuelve a hacer.

## 5. Avisos

- Un PO Token **no garantiza** que YouTube no bloquee; solo hace las peticiones como YouTube espera de ese cliente.
- Usar una cuenta con yt-dlp puede acabar en bloqueo temporal o permanente de esa cuenta: por eso aquí es solo de
  reserva.
- Las condiciones de YouTube restringen descargar y reutilizar contenido sin permiso; el riesgo de reclamaciones de
  usar clips de terceros es el mismo en casa o en un servidor (ver el aviso por canal en el informe de QA).
