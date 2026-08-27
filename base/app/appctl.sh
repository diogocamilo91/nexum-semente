#!/usr/bin/env bash
# Painel de controle do app pessoal. Tudo passa por aqui.
# (Parte do kit NEXUM Semente — nada fixo: descobre a propria pasta sozinho.)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$DIR/app.log"
PAUSED="$DIR/PAUSED"
PORTA=$(grep -E '^CHAT_PORTA=' "$HOME/.config/semente/config.env" 2>/dev/null | cut -d= -f2)
PORTA=${PORTA:-8800}

_vivo(){ pgrep -f "$DIR/[s]ervidor.py" >/dev/null; }

_wait_dead() {
  local n=0
  while _vivo || pgrep -f "$DIR/[r]un.sh" >/dev/null; do
    n=$((n+1))
    if [ "$n" -gt 40 ]; then
      pkill -9 -f "$DIR/[r]un.sh" 2>/dev/null
      pkill -9 -f "$DIR/[s]ervidor.py" 2>/dev/null
      sleep 1; break
    fi
    sleep 0.5
  done
}

# Espera a linha ficar livre: NAO reinicie em cima de uma resposta saindo.
# A contagem vem de uma placa que o proprio app publica — contar processo com
# `ps` da zero fixo e o deploy cai bem em cima do turno.
_espera_livre() {
  local n=0 voando
  while [ "$n" -lt 60 ]; do
    voando=$(curl -s --max-time 3 "http://127.0.0.1:$PORTA/saude" \
             | grep -o '"turnos_em_voo":[0-9]*' | cut -d: -f2)
    [ -z "$voando" ] && return 0
    [ "$voando" = "0" ] && return 0
    echo "  ...esperando $voando resposta(s) terminar(em)"
    n=$((n+1)); sleep 2
  done
}

case "$1" in
  start)
    [ -f "$PAUSED" ] && { echo "app pausado de proposito — use 'resume'"; exit 0; }
    _vivo && { echo "ja esta rodando"; exit 0; }
    setsid nohup bash "$DIR/run.sh" >/dev/null 2>&1 < /dev/null &
    echo "app ligado"
    ;;
  stop)
    pkill -f "$DIR/[r]un.sh" 2>/dev/null
    pkill -f "$DIR/[s]ervidor.py" 2>/dev/null
    _wait_dead
    echo "app parado"
    ;;
  restart) _espera_livre; bash "$0" stop; bash "$0" start ;;
  pause)   touch "$PAUSED"; bash "$0" stop >/dev/null; echo "app pausado — nao religa sozinho" ;;
  resume)  rm -f "$PAUSED"; bash "$0" start ;;
  status)
    if pgrep -af "$DIR/[s]ervidor.py"; then echo ">> VIVO"; else echo ">> PARADO"; fi
    [ -f "$PAUSED" ] && echo "(pausado de proposito — use 'resume')"
    curl -s --max-time 3 "http://127.0.0.1:$PORTA/saude"; echo
    ;;
  log) tail -n "${2:-30}" "$LOG" ;;
  telas) grep -E "^[0-9-]+ [0-9:]+ tela " "$LOG" | tail -30 ;;
  install-watchdog)
    tmp=$(mktemp)
    crontab -l 2>/dev/null | grep -v "$DIR/appctl.sh start" > "$tmp"
    echo "@reboot bash $DIR/appctl.sh start" >> "$tmp"
    echo "*/2 * * * * bash $DIR/appctl.sh start >/dev/null 2>&1" >> "$tmp"
    crontab "$tmp"; rm -f "$tmp"
    echo "vigia instalado (confere a cada 2 min + sobe no boot)"
    ;;
  *) echo "uso: appctl.sh {start|stop|restart|pause|resume|status|log [n]|telas|install-watchdog}" ;;
esac
