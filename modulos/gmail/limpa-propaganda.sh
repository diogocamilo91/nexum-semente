#!/usr/bin/env bash
# Semente — robô limpa-propaganda (cron de hora em hora).
# Marca como LIDA a aba Promoções do Gmail. NUNCA apaga, NUNCA arquiva.
# Silencioso de propósito: só escreve no log; se quebrar 3x seguidas, avisa o
# dono UMA vez pelo alerta.sh (anti-spam por arquivo-marcador).
set -u

BIN="$HOME/semente-bin"
LOG="$BIN/log/limpa-propaganda.log"
FALHAS="$BIN/log/.limpa-propaganda.falhas"
mkdir -p "$BIN/log"

CONFIG="${SEMENTE_CONFIG:-$HOME/.config/semente/config.env}"
# shellcheck disable=SC1090
[ -f "$CONFIG" ] && { set -a; . "$CONFIG"; set +a; }

# desligado no config? sai quieto (deixa o cron instalado, mas inerte)
if [ "${GMAIL_LIMPA_PROPAGANDA:-sim}" = "nao" ]; then
  exit 0
fi

{
  echo "--- $(date '+%F %T')"
  if python3 "$BIN/gmail.py" limpa-propaganda --max 200; then
    rm -f "$FALHAS"
  else
    N=$(( $(cat "$FALHAS" 2>/dev/null || echo 0) + 1 ))
    echo "$N" > "$FALHAS"
    if [ "$N" -eq 3 ] && [ -x "$BIN/alerta.sh" ]; then
      "$BIN/alerta.sh" --titulo "📧 Gmail" \
        "O robô limpa-propaganda falhou 3 vezes seguidas. Provável: autorização do Google expirou. Me peça pra refazer o auth do Gmail quando puder. (Nenhum e-mail foi afetado.)"
    fi
  fi
} >> "$LOG" 2>&1
