#!/usr/bin/env bash
# Semente — monitor da VPS (cron 30/30min).
# Roda o coletor (que SALVA o histórico em ~/semente-bin/log/vps-historico.csv) e,
# SÓ se houver EMERGÊNCIA (serviço caído ou disco quase cheio), manda na hora no
# Telegram do dono. A régua é UM relatório por dia: tudo o mais (memória, carga,
# disco em 85%, backup atrasado) vai só no fechamento das 21h. Isto é o socorro.
#
# Pra mexer no que é emergência: função emergencias() em saude_vps.py.
# Silêncio TOTAL (nem emergência): criar ~/monitor-vps.PAUSED (apagar pra religar).
set -u

SCRIPT="$HOME/semente-bin/saude_vps.py"
ALERTA="$HOME/semente-bin/alerta.sh"
LOG="$HOME/semente-bin/log/monitor-vps.log"
PAUSED="$HOME/monitor-vps.PAUSED"
STAMP="/tmp/semente-vps-ultimo-alerta"   # anti-spam: não repetir o mesmo alerta a cada 30min

mkdir -p "$(dirname "$LOG")"
[ -f "$PAUSED" ] && exit 0

EMERGENCIA=$(python3 "$SCRIPT" --emergencia 2>>"$LOG")

if [ -n "$EMERGENCIA" ]; then
  # só manda se for diferente do último alerta enviado
  ANTERIOR=$(cat "$STAMP" 2>/dev/null || true)
  if [ "$EMERGENCIA" != "$ANTERIOR" ]; then
    if "$ALERTA" --titulo "🖥️ VPS — emergência" "$EMERGENCIA" >>"$LOG" 2>&1; then
      echo "$EMERGENCIA" > "$STAMP"
      echo "$(date '+%F %T') alerta enviado" >> "$LOG"
    fi
  fi
else
  rm -f "$STAMP"   # voltou ao normal: zera, pra avisar de novo se reaparecer
fi
exit 0
