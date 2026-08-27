#!/usr/bin/env bash
# App pessoal — supervisor: liga o app e reinicia sozinho se ele cair.
# (Parte do kit NEXUM Semente — nada fixo: descobre a propria pasta sozinho.)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$DIR/venv/bin/python"
cd "$DIR" || exit 1
echo "$(date '+%F %T') supervisor iniciado" >> "$DIR/app.log"
while true; do
    "$PY" -u "$DIR/servidor.py" >> "$DIR/app.log" 2>&1
    echo "$(date '+%F %T') app saiu (cod $?), reiniciando em 3s" >> "$DIR/app.log"
    sleep 3
done
