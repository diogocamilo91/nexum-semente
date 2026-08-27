#!/usr/bin/env bash
# Chat web — supervisor: liga o chat e reinicia sozinho se ele cair.
# (Parte do kit NEXUM Semente — nada fixo: descobre a propria pasta sozinho.)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$DIR/venv/bin/python"
cd "$DIR" || exit 1
echo "$(date '+%F %T') supervisor iniciado" >> "$DIR/chat.log"
while true; do
    "$PY" -u "$DIR/chat.py" >> "$DIR/chat.log" 2>&1
    echo "$(date '+%F %T') chat saiu (cod $?), reiniciando em 3s" >> "$DIR/chat.log"
    sleep 3
done
