#!/usr/bin/env bash
# Bot do Telegram — supervisor: liga o bot e reinicia sozinho se ele cair.
# (Parte do kit NEXUM Semente — nada fixo: descobre a propria pasta sozinho.)
BOTDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$BOTDIR/venv/bin/python"
cd "$BOTDIR" || exit 1
echo "$(date '+%F %T') supervisor iniciado" >> "$BOTDIR/bot.log"
while true; do
    "$PY" -u "$BOTDIR/bot.py" >> "$BOTDIR/bot.log" 2>&1
    echo "$(date '+%F %T') bot saiu (cod $?), reiniciando em 3s" >> "$BOTDIR/bot.log"
    sleep 3
done
