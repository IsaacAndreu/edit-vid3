#!/usr/bin/env bash
# La cola de vídeos cada día a una hora (por defecto 03:00, hora del servidor). Uso: bash scripts/vps/install-cron.sh [HH:MM]
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
AT="${1:-03:00}"
H="${AT%%:*}"; M="${AT##*:}"
LINE="$M $H * * * cd $ROOT && git pull -q && . .venv/bin/activate && PATH=\$HOME/.deno/bin:\$PATH python main.py --all > out/cola.log 2>&1"
( crontab -l 2>/dev/null | grep -v "edit-vid3\|main.py --all" ; echo "$LINE # edit-vid3" ) | crontab -
echo "Cola programada a las $AT:"
crontab -l | grep "main.py --all"
