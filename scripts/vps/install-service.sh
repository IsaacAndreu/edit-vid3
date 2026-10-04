#!/usr/bin/env bash
# Servicio del sistema: el servidor hace vídeos todo el rato (python main.py --vigilar), arranca solo al encender la
# VPS y se reinicia si algo lo tumba. Uso: bash scripts/vps/install-service.sh [minutos entre miradas, 5]
#   Ver qué hace:   journalctl -u edit-vid3 -f        Parar: sudo systemctl stop edit-vid3
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
EVERY="${1:-5}"
sudo tee /etc/systemd/system/edit-vid3.service >/dev/null <<UNIT
[Unit]
Description=edit-vid3: vídeos de materiales/ en cuanto aparecen
After=network-online.target docker.service
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$ROOT
Environment=PATH=$HOME/.deno/bin:$ROOT/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart=$ROOT/.venv/bin/python main.py --vigilar $EVERY
Restart=always
RestartSec=60
Nice=5

[Install]
WantedBy=multi-user.target
UNIT
# the Telegram bot: /estado, /gasto, /videos… and the hourly report (needs TELEGRAM_* in .env)
sudo tee /etc/systemd/system/edit-vid3-bot.service >/dev/null <<UNIT
[Unit]
Description=edit-vid3: bot de Telegram
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$ROOT
Environment=PATH=$ROOT/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart=$ROOT/.venv/bin/python main.py --bot
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT
# the nightly cron of install-cron.sh is not needed with the service
( crontab -l 2>/dev/null | grep -v "main.py --all" ) | crontab - || true
sudo systemctl daemon-reload
sudo systemctl enable --now edit-vid3
if grep -q '^TELEGRAM_BOT_TOKEN=' .env 2>/dev/null && grep -q '^TELEGRAM_CHAT_ID=' .env 2>/dev/null; then
  sudo systemctl enable --now edit-vid3-bot && sudo systemctl restart edit-vid3-bot
else
  echo "Bot de Telegram sin activar: conecta Telegram (estudio → Ajustes) y luego: sudo systemctl enable --now edit-vid3-bot"
fi
sleep 2
systemctl --no-pager status edit-vid3 | head -5
echo "Listo: mete guiones en materiales/<canal>/<vídeo>/ y se harán solos. Registro: journalctl -u edit-vid3 -f"
