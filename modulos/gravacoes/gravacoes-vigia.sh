#!/usr/bin/env bash
# Semente — vigia da pasta de gravações. Cron de 5 em 5 min.
#
# O dono solta um áudio em ~/gravacoes/entrada/ (por SFTP, Termius, ou o
# assistente baixa de um anexo). Este vigia pega cada arquivo novo, chama o
# gravacao_processar.py (transcrição Gemini + ficha) e avisa no Telegram.
#
# Way of life: NUNCA apaga o áudio. Deu certo => move pra ~/gravacoes/processadas/.
# Deu errado => move pra ~/gravacoes/com-problema/ e avisa (uma vez só).
# Pausar: criar ~/gravacoes-vigia.PAUSED (apagar pra religar).
set -u

ENTRADA="$HOME/gravacoes/entrada"
OK="$HOME/gravacoes/processadas"
RUIM="$HOME/gravacoes/com-problema"
ALERTA="$HOME/semente-bin/alerta.sh"
PROC="$HOME/semente-bin/gravacao_processar.py"
LOG="$HOME/semente-bin/log/gravacoes.log"
PAUSED="$HOME/gravacoes-vigia.PAUSED"
LOCK="$HOME/.config/semente/gravacoes.lock"

mkdir -p "$ENTRADA" "$OK" "$RUIM" "$(dirname "$LOG")" "$(dirname "$LOCK")"
ts() { date '+%F %T'; }
log() { echo "$(ts) $*" >> "$LOG"; }

[ -f "$PAUSED" ] && exit 0

# trava: nunca dois vigias ao mesmo tempo (áudio longo passa de 5 min)
exec 9>"$LOCK"
flock -n 9 || exit 0

shopt -s nullglob
for f in "$ENTRADA"/*; do
  [ -f "$f" ] || continue
  base=$(basename "$f")
  case "$base" in .*) continue ;; esac   # ignora ocultos/parciais

  # arquivo ainda crescendo (upload em curso)? espera a próxima rodada
  t1=$(stat -c %s "$f"); sleep 5; t2=$(stat -c %s "$f")
  [ "$t1" != "$t2" ] && { log "ainda subindo, deixo pra depois: $base"; continue; }

  log "processando: $base"
  if MD=$(timeout 3000 python3 "$PROC" "$f" 2>>"$LOG"); then
    mv -n "$f" "$OK/$base"
    log "ok: $base -> $MD"
    "$ALERTA" --titulo "🎙️ Gravação pronta" \
      "Transcrevi e avaliei \"$base\". Ficou em: ${MD/#$HOME/\~}
Me pergunta qualquer coisa sobre ela que eu leio pra você." >>"$LOG" 2>&1
  else
    mv -n "$f" "$RUIM/$base"
    log "FALHOU: $base (áudio movido pra com-problema/)"
    "$ALERTA" --titulo "🎙️ Gravação com problema" \
      "Não consegui transcrever \"$base\". O áudio está guardado em ~/gravacoes/com-problema/ (não apaguei nada). Me chama que eu investigo o porquê." >>"$LOG" 2>&1
  fi
done
exit 0
