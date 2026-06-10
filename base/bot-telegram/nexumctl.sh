#!/usr/bin/env bash
# Painel de controle do bot do Telegram. Tudo passa por aqui (start/stop/status/log).
# (Parte do kit NEXUM Semente — nada fixo: descobre a propria pasta sozinho.)
BOTDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$BOTDIR/bot.log"
PAUSED="$BOTDIR/PAUSED"   # se este arquivo existir, o bot fica desligado de proposito (o vigia respeita)

# espera o bot morrer de verdade antes de seguir (evita o restart "ja esta rodando")
_wait_dead() {
  local n=0
  while pgrep -f "$BOTDIR/[r]un.sh" >/dev/null || pgrep -f "$BOTDIR/[b]ot.py" >/dev/null; do
    n=$((n+1))
    if [ "$n" -gt 20 ]; then            # ~10s e ainda vivo: forca
      pkill -9 -f "$BOTDIR/[r]un.sh" 2>/dev/null
      pkill -9 -f "$BOTDIR/[b]ot.py" 2>/dev/null
      sleep 1
      break
    fi
    sleep 0.5
  done
}

case "$1" in
  start)
    if [ -f "$PAUSED" ]; then echo "bot esta pausado de proposito — use 'resume' pra religar"; exit 0; fi
    if pgrep -f "$BOTDIR/[b]ot.py" >/dev/null; then echo "ja esta rodando"; exit 0; fi
    setsid nohup bash "$BOTDIR/run.sh" >/dev/null 2>&1 < /dev/null &
    echo "bot ligado"
    ;;
  stop)
    pkill -f "$BOTDIR/[r]un.sh" 2>/dev/null
    pkill -f "$BOTDIR/[b]ot.py" 2>/dev/null
    _wait_dead
    echo "bot parado"
    ;;
  restart)
    bash "$0" stop
    bash "$0" start
    ;;
  pause)
    # desliga de proposito: cria a trava e para. O vigia NAO vai religar.
    touch "$PAUSED"
    bash "$0" stop >/dev/null
    echo "bot pausado — nao vai religar sozinho ate voce mandar 'resume'"
    ;;
  resume)
    rm -f "$PAUSED"
    bash "$0" start
    ;;
  status)
    if pgrep -af "$BOTDIR/[b]ot.py"; then echo ">> VIVO"; else echo ">> PARADO"; fi
    [ -f "$PAUSED" ] && echo "(pausado de proposito — use 'resume')"
    ;;
  log)
    tail -n "${2:-30}" "$LOG"
    ;;
  install-cron)
    # liga o bot sozinho quando a VPS reiniciar (sem duplicar a linha)
    tmp=$(mktemp)
    crontab -l 2>/dev/null | grep -v "$BOTDIR/nexumctl.sh start" > "$tmp"
    echo "@reboot bash $BOTDIR/nexumctl.sh start" >> "$tmp"
    crontab "$tmp"
    rm -f "$tmp"
    echo "cron @reboot instalado"
    ;;
  install-watchdog)
    # vigia: religa sozinho em ate 2 min se cair (o start respeita a pausa) + sobe no boot
    tmp=$(mktemp)
    crontab -l 2>/dev/null | grep -v "$BOTDIR/nexumctl.sh start" > "$tmp"
    echo "@reboot bash $BOTDIR/nexumctl.sh start" >> "$tmp"
    echo "*/2 * * * * bash $BOTDIR/nexumctl.sh start >/dev/null 2>&1" >> "$tmp"
    crontab "$tmp"
    rm -f "$tmp"
    echo "vigia instalado (confere a cada 2 min + sobe no boot)"
    ;;
  *)
    echo "uso: nexumctl.sh {start|stop|restart|pause|resume|status|log [n]|install-cron|install-watchdog}"
    ;;
esac
