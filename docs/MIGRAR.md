# Pasar a un servidor nuevo

Para cambiar de VPS (o a un servidor dedicado más grande) sin perder nada. Unas 2 horas, la mayor parte esperando
instalaciones y copias. Los comandos van en **el servidor viejo** o en **el nuevo**, según se indique.

## 0. Antes de empezar (servidor viejo)

1. En el estudio → ⚙️ Ajustes → **Pausar** la cola, y espera a que terminen los vídeos que se están haciendo
   (🖥 Estado del servidor → Cola: ninguno «haciendo»).
2. Copia de seguridad ahora:

   ```bash
   cd /opt/video-app/edit-vid3 && .venv/bin/python main.py --copia
   ```

   Lleva lo que no se puede rehacer: `config.local.yaml` y `.env` (tus claves), los guiones y voces de
   `materiales/`, los datos del estudio (`out/_*.json`: ajustes, voces, calendario, ideas, experimentos…), las listas
   de la biblioteca y el registro de la API. Descárgala también desde 🖥 Estado del servidor → **Descargar** y
   guárdala en un sitio privado (lleva tus claves).

## 1. Instalar (servidor nuevo)

Ubuntu 24.04. Igual que la primera vez (docs/VPS.md, punto 2):

```bash
mkdir -p /opt/video-app && cd /opt/video-app
git clone -b claude/pensive-bell-5pi66r https://github.com/IsaacAndreu/edit-vid3.git
cd edit-vid3
bash scripts/vps/setup-ubuntu.sh          # Python, ffmpeg, Node, Deno, Chrome para Remotion, Docker, PO Token
```

## 2. Copiar los datos (del viejo al nuevo, directamente)

En **el servidor viejo** (cambia `IP_NUEVA`):

```bash
cd /opt/video-app/edit-vid3
scp "$(ls -t /root/copias-edit-vid3/edit-vid3-*.tar.gz | head -1)" root@IP_NUEVA:/root/copia.tar.gz
# las cuentas de reserva (si las usas), nunca por git:
scp -r /root/.config/edit-vid3 root@IP_NUEVA:/root/.config/
```

Opcional, para no volver a descargar ni analizar (puede ser mucho; `du -sh cache out` dice cuánto):

```bash
rsync -a --info=progress2 cache/embeddings cache/library root@IP_NUEVA:/opt/video-app/edit-vid3/cache/
rsync -a --info=progress2 --include='*/' --include='video-final.mp4' --include='shorts/***' --exclude='*' \
      out/ root@IP_NUEVA:/opt/video-app/edit-vid3/out/       # los vídeos terminados que aún no has subido
```

En **el servidor nuevo**:

```bash
cd /opt/video-app/edit-vid3
tar xzf /root/copia.tar.gz                 # deja config.local.yaml, .env, materiales/, out/_*.json… en su sitio
```

## 3. Conexión de casa y proxy

- **Tailscale** (las descargas salen por el PC de casa): `curl -fsSL https://tailscale.com/install.sh | sh &&
  tailscale up`, entra con tu cuenta y comprueba que ves el PC de casa: `tailscale status`.
- **Proxy de metadatos** (DataImpulse): ya viene en `config.local.yaml`; no hay que tocar nada.

## 4. Ajustar a la máquina grande

En `config.local.yaml` (ejemplo para 64 GB de RAM y 16 núcleos):

```yaml
queue:
  parallel_videos: 5
  slots: {red: 3, cpu: 2}       # 3 buscando/descargando y 2 analizando/rellenando/renderizando a la vez
```

Empieza con `parallel_videos: 3` y `slots: {red: 2, cpu: 2}`, mira la RAM en 🖥 Estado del servidor durante un día
y sube después. La cuota de la API de YouTube sigue limitando cuántos vídeos salen al día.

## 5. Servicios y estudio

```bash
bash scripts/vps/install-service.sh        # la cola (edit-vid3)
bash scripts/vps/install-web.sh            # el estudio con HTTPS: https://<ip-nueva-con-guiones>.sslip.io
```

La dirección del estudio cambia con la IP (sslip.io). La contraseña es la misma (`WEB_PASSWORD` de `.env`).

## 6. Comprobar

```bash
.venv/bin/python main.py --comprobar-proteccion      # conexiones, cuota, claves (solo nombres)
.venv/bin/python -m pytest -q                         # todo pasa
```

En el estudio: 🖥 Estado del servidor (máquina, cuota, proxy, conexión de casa «libre»), y quita la pausa de la cola.
Mira que el primer vídeo termine bien y que llegue el aviso de Telegram.

## 7. Apagar el viejo

Cuando el nuevo haya hecho un par de vídeos bien, **en el viejo**:

```bash
systemctl disable --now edit-vid3 edit-vid3-web
```

Que no queden los dos a la vez: gastarían la misma cuota de la API y las mismas claves. Guarda el viejo una semana por
si falta algo y luego cancélalo.
