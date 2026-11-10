#!/usr/bin/env bash
# edit-vid3 en una VPS Ubuntu 24.04 (4-8 vCPU, 8-16 GB). Uso, como usuario normal con sudo:
#   git clone -b claude/pensive-bell-5pi66r https://github.com/IsaacAndreu/edit-vid3.git && cd edit-vid3
#   bash scripts/vps/setup-ubuntu.sh
# Instala: Python (venv), ffmpeg, Node 22, Deno, las librerías de Chrome para Remotion, Docker y el
# PO Token Provider (bgutil: servidor en Docker + plugin de yt-dlp), y la seguridad básica (ufw, fail2ban, parches).
# Se puede repetir sin romper nada.
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT="$(pwd)"

echo "== Paquetes del sistema"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git curl unzip ffmpeg ca-certificates \
  libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
  libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2t64 libpango-1.0-0 libcairo2 fonts-liberation

echo "== Swap de 8 GB (un pico de Chromium/PyTorch no mata el proceso)"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 8G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  grep -q /swapfile /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

echo "== Node 22 (Remotion)"
if ! command -v node >/dev/null || [ "$(node -v | cut -c2- | cut -d. -f1)" -lt 20 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

echo "== Deno (retos JavaScript de YouTube para yt-dlp)"
if ! command -v deno >/dev/null; then
  curl -fsSL https://deno.land/install.sh | sh -s -- -y
  echo 'export PATH="$HOME/.deno/bin:$PATH"' >> ~/.bashrc
  export PATH="$HOME/.deno/bin:$PATH"
fi

echo "== Python (venv en .venv) — torch para CPU: la VPS no tiene gráfica"
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip wheel
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
pip install -U "yt-dlp[default]" yt-dlp-ejs bgutil-ytdlp-pot-provider psutil

echo "== Paquetes de Node"
npm install

echo "== Docker + servidor del PO Token Provider (bgutil) en 127.0.0.1:4416"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER" || true
fi
sudo docker rm -f bgutil-provider >/dev/null 2>&1 || true
sudo docker run --name bgutil-provider -d --init --restart unless-stopped -p 127.0.0.1:4416:4416 \
  brainicism/bgutil-ytdlp-pot-provider
sleep 3
curl -fsS http://127.0.0.1:4416/ping && echo "  PO Token Provider responde ✓" || echo "  AVISO: el PO Token Provider no responde todavía"

echo "== Seguridad: cortafuegos (solo SSH y web), fail2ban (bloquea a quien prueba contraseñas) y parches automáticos"
sudo apt-get install -y ufw fail2ban unattended-upgrades
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo systemctl enable --now fail2ban
echo 'APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";' | sudo tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null
# Docker publica 4416 solo en 127.0.0.1: el PO Token Provider no se ve desde fuera aunque Docker se salte ufw

echo "== Configuración de esta máquina (config.local.yaml, fuera de git)"
if [ ! -f config.local.yaml ]; then
  cp scripts/vps/config.local.example.yaml config.local.yaml
  echo "  creado config.local.yaml (sin cuenta, PO Token, mweb)"
fi

echo
echo "Listo. Falta copiar a mano (nunca por git):"
echo "  - .env con tus claves               →  $ROOT/.env"
echo "  - (opcional) cookies de reserva     →  ~/.config/edit-vid3/cookies/*.txt"
echo "Prueba:   . .venv/bin/activate && python main.py --probar-youtube"
echo "Después, que haga vídeos todo el rato:   bash scripts/vps/install-service.sh"
echo "Y el estudio web con HTTPS (WEB_PASSWORD en .env):   bash scripts/vps/install-web.sh"
