#!/usr/bin/env bash
# Painel do espelho do WhatsApp. Tudo passa por aqui.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$DIR/logs/saida.log"
PAUSED="$DIR/PAUSED"

_vivo(){ pgrep -f "$DIR/[c]oletor.js" >/dev/null; }

case "$1" in
  start)
    [ -f "$PAUSED" ] && { echo "espelho pausado de proposito — use 'resume'"; exit 0; }
    _vivo && { echo "ja esta rodando"; exit 0; }
    mkdir -p "$DIR/logs"
    setsid nohup bash "$DIR/run.sh" >/dev/null 2>&1 < /dev/null &
    sleep 1
    pgrep -f "$DIR/[c]oletor.js" > "$DIR/run.pid" 2>/dev/null
    echo "espelho ligado"
    ;;
  stop)
    pkill -f "$DIR/[r]un.sh" 2>/dev/null
    pkill -f "$DIR/[c]oletor.js" 2>/dev/null
    sleep 1
    rm -f "$DIR/run.pid"
    echo "espelho parado"
    ;;
  restart) bash "$0" stop; bash "$0" start ;;
  pause)   touch "$PAUSED"; bash "$0" stop >/dev/null; echo "espelho pausado — nao religa sozinho" ;;
  resume)  rm -f "$PAUSED"; bash "$0" start ;;
  status)
    if _vivo; then
      echo ">> VIVO"
      pgrep -f "$DIR/[c]oletor.js" > "$DIR/run.pid"
    else
      echo ">> PARADO"; rm -f "$DIR/run.pid"
    fi
    [ -f "$PAUSED" ] && echo "(pausado de proposito — use 'resume')"
    if [ -f "$DIR/qr.png" ]; then
      echo "!! tem um QR esperando ser lido no celular: $DIR/qr.png"
    fi
    n=$(wc -l < "$DIR/dados/mensagens.jsonl" 2>/dev/null || echo 0)
    echo "mensagens no espelho: $n"
    ;;
  log) tail -n "${2:-30}" "$LOG" ;;
  parear)
    # recomeca o pareamento do zero: a credencial velha e MOVIDA, nunca apagada
    bash "$0" stop >/dev/null
    if [ -d "$DIR/auth" ]; then
      alvo="$DIR/auth.anterior-$(date +%d%m%Y-%H%M)"
      mv "$DIR/auth" "$alvo"
      echo "credencial anterior guardada em $(basename "$alvo")"
    fi
    mkdir -p "$DIR/auth"; chmod 700 "$DIR/auth"
    bash "$0" start
    echo "aguarde ~15s e abra o arquivo qr.png"
    ;;
  install-watchdog)
    tmp=$(mktemp)
    crontab -l 2>/dev/null | grep -v "$DIR/wactl.sh start" > "$tmp"
    echo "@reboot bash $DIR/wactl.sh start" >> "$tmp"
    echo "*/2 * * * * bash $DIR/wactl.sh start >/dev/null 2>&1" >> "$tmp"
    crontab "$tmp"; rm -f "$tmp"
    echo "vigia instalado (confere a cada 2 min + sobe no boot)"
    ;;
  *) echo "uso: wactl.sh {start|stop|restart|pause|resume|status|log [n]|parear|install-watchdog}" ;;
esac
