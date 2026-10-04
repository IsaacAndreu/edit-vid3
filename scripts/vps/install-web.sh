#!/usr/bin/env bash
# Estudio web en la VPS, con HTTPS: https://<tu-ip>.sslip.io (o tu dominio) → python main.py --web (127.0.0.1:8080).
# Uso: bash scripts/vps/install-web.sh [dominio]      (sin dominio: <ip-pública>.sslip.io, sin comprar nada)
# Antes: WEB_PASSWORD=una-contraseña-larga en .env (sin ella el estudio no abre fuera de la VPS).
#   Ver qué hace:  journalctl -u edit-vid3-web -f       Parar: sudo systemctl stop edit-vid3-web
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
if ! grep -qE '^WEB_PASSWORD=.{10,}' .env 2>/dev/null; then
  echo "Falta WEB_PASSWORD en .env (10 caracteres o más). Añádela:  echo 'WEB_PASSWORD=…' >> .env"
  exit 1
fi
IP="$(curl -fsS4 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"
DOMAIN="${1:-${IP//./-}.sslip.io}"

echo "== Servicio del estudio (127.0.0.1:8080, solo accesible a través de Caddy)"
sudo tee /etc/systemd/system/edit-vid3-web.service >/dev/null <<UNIT
[Unit]
Description=edit-vid3: estudio web
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$ROOT
Environment=PATH=$HOME/.deno/bin:$ROOT/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart=$ROOT/.venv/bin/python main.py --web 8080 --host 127.0.0.1
Restart=always
RestartSec=10
KillMode=process          # a video started from the studio keeps going when the studio restarts

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now edit-vid3-web

echo "== Caddy (HTTPS automático con Let's Encrypt)"
if ! command -v caddy >/dev/null; then
  sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -y && sudo apt-get install -y caddy
fi
sudo tee /etc/caddy/Caddyfile >/dev/null <<CADDY
$DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:8080 {
		header_up X-Forwarded-Proto {scheme}
	}
	header {
		Strict-Transport-Security "max-age=31536000"
		X-Frame-Options DENY
		Referrer-Policy no-referrer
	}
}
CADDY
sudo systemctl reload caddy || sudo systemctl restart caddy
if command -v ufw >/dev/null && sudo ufw status | grep -q active; then sudo ufw allow 80/tcp && sudo ufw allow 443/tcp; fi
# the Telegram messages link to the studio («Revisar clips»)
grep -q '^STUDIO_URL=' .env || echo "STUDIO_URL=https://$DOMAIN" >> .env
sudo systemctl restart edit-vid3 2>/dev/null || true      # the watcher reads .env at start
echo
echo "Listo: https://$DOMAIN   (la primera vez tarda ~30 s en sacar el certificado)"
