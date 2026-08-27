#!/usr/bin/env bash
# Painel de controle do chat web. Tudo passa por aqui (start/stop/status/log).
# (Parte do kit NEXUM Semente — nada fixo: descobre a propria pasta sozinho.)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$DIR/chat.log"
PAUSED="$DIR/PAUSED"

_wait_dead() {
  local n=0
  while pgrep -f "$DIR/[c]hat.py" >/dev/null || pgrep -f "$DIR/[r]un.sh" >/dev/null; do
    n=$((n+1))
    if [ "$n" -gt 40 ]; then    # ~20s: o dreno interno e ~120s, mas parar na mao e parar
      pkill -9 -f "$DIR/[r]un.sh" 2>/dev/null
      pkill -9 -f "$DIR/[c]hat.py" 2>/dev/null
      sleep 1; break
    fi
    sleep 0.5
  done
}

# Espera a linha ficar livre: nao reinicie em cima de um turno que esta respondendo.
_espera_livre() {
  local porta n=0
  porta=$(grep -E '^CHAT_PORTA=' "$HOME/.config/semente/config.env" 2>/dev/null | cut -d= -f2)
  porta=${porta:-8800}
  while [ "$n" -lt 60 ]; do     # ate 2 min
    voando=$(curl -s --max-time 3 "http://127.0.0.1:$porta/saude" | grep -o '"turnos_em_voo":[0-9]*' | cut -d: -f2)
    [ -z "$voando" ] && return 0
    [ "$voando" = "0" ] && return 0
    echo "  ...esperando $voando turno(s) terminar(em)"
    n=$((n+1)); sleep 2
  done
}

case "$1" in
  start)
    if [ -f "$PAUSED" ]; then echo "chat esta pausado de proposito — use 'resume'"; exit 0; fi
    if pgrep -f "$DIR/[c]hat.py" >/dev/null; then echo "ja esta rodando"; exit 0; fi
    setsid nohup bash "$DIR/run.sh" >/dev/null 2>&1 < /dev/null &
    echo "chat ligado"
    ;;
  stop)
    pkill -f "$DIR/[r]un.sh" 2>/dev/null
    pkill -f "$DIR/[c]hat.py" 2>/dev/null
    _wait_dead
    echo "chat parado"
    ;;
  restart)
    _espera_livre
    bash "$0" stop; bash "$0" start
    ;;
  pause)  touch "$PAUSED"; bash "$0" stop >/dev/null; echo "chat pausado — nao religa sozinho" ;;
  resume) rm -f "$PAUSED"; bash "$0" start ;;
  status)
    if pgrep -af "$DIR/[c]hat.py"; then echo ">> VIVO"; else echo ">> PARADO"; fi
    [ -f "$PAUSED" ] && echo "(pausado de proposito — use 'resume')"
    ;;
  log) tail -n "${2:-30}" "$LOG" ;;
  install-watchdog)
    tmp=$(mktemp)
    crontab -l 2>/dev/null | grep -v "$DIR/chatctl.sh start" > "$tmp"
    echo "@reboot bash $DIR/chatctl.sh start" >> "$tmp"
    echo "*/2 * * * * bash $DIR/chatctl.sh start >/dev/null 2>&1" >> "$tmp"
    crontab "$tmp"; rm -f "$tmp"
    echo "vigia instalado (confere a cada 2 min + sobe no boot)"
    ;;
  *) echo "uso: chatctl.sh {start|stop|restart|pause|resume|status|log [n]|install-watchdog}" ;;
esac
