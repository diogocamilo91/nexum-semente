#!/usr/bin/env bash
# Espelho do WhatsApp — supervisor: liga o coletor e religa se ele cair.
# (Parte do kit NEXUM Semente — descobre a propria pasta sozinho.)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1
mkdir -p logs
echo "$(date '+%F %T') supervisor iniciado" >> logs/saida.log
while true; do
    node "$DIR/coletor.js" >> logs/saida.log 2>&1
    echo "$(date '+%F %T') coletor saiu (cod $?), religando em 5s" >> logs/saida.log
    sleep 5
done
