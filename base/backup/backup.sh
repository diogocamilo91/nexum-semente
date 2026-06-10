#!/usr/bin/env bash
# Semente — backup automático do ~/nexum pro GitHub (repositório PRIVADO do dono).
# Roda sozinho via cron, de hora em hora. Só faz commit/push se algo mudou.
#
# Proteções embutidas:
#  - Trava de arquivo grande: arquivo > 95 MB faria o GitHub recusar TODO o push
#    (e o backup pararia em silêncio). Em vez disso, ignoramos o grande localmente
#    (.git/info/exclude) e avisamos no Telegram — o resto do backup continua subindo.
#  - Alerta se o push falhar: backup parado nunca fica mudo.
#
# Configuração: nada hardcoded — o destino (origin) é configurado pelo instalador
# (ver LEIA-ME.md); o alerta usa ~/semente-bin/alerta.sh (que lê o config.env).
set -uo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin

REPO="$HOME/nexum"
LOGDIR="$HOME/semente-bin/log"
LOG="$LOGDIR/backup.log"
ALERTA="$HOME/semente-bin/alerta.sh"
MAXMB=95                       # GitHub recusa arquivo > 100 MB; margem de segurança

mkdir -p "$LOGDIR"
cd "$REPO" || { echo "$(date '+%F %T') ERRO: $REPO nao existe" >> "$LOG"; exit 1; }

avisar() {  # alerta no Telegram do dono; nunca derruba o backup se falhar
  [ -x "$ALERTA" ] && "$ALERTA" --titulo "💾 Backup" "$1" >>"$LOG" 2>&1 || true
}

# --- Trava de arquivo grande ---
GRANDES=$(find . -path ./.git -prune -o -type f -size +${MAXMB}M -print 2>/dev/null)
if [ -n "$GRANDES" ]; then
  while IFS= read -r f; do
    rel="${f#./}"
    grep -qxF "$rel" .git/info/exclude 2>/dev/null || echo "$rel" >> .git/info/exclude
    git rm --cached --quiet "$rel" 2>/dev/null   # se já estava rastreado, tira do índice
    echo "$(date '+%F %T') GRANDE ignorado (>${MAXMB}MB): $rel" >> "$LOG"
  done <<< "$GRANDES"
  avisar "⚠️ Backup: arquivo grande (>${MAXMB}MB) foi deixado FORA do backup pra não travar o resto. Arquivo(s): $(echo "$GRANDES" | tr '\n' ' ')"
fi

# --- Nada mudou? Não faz nada (evita commit à toa) ---
if [ -z "$(git status --porcelain)" ]; then
  echo "$(date '+%F %T') sem mudancas" >> "$LOG"
  exit 0
fi

git add -A
git commit -q -m "Backup automático — $(date '+%d/%m/%Y %H:%M')" >> "$LOG" 2>&1
if git push -q origin main >> "$LOG" 2>&1; then
  echo "$(date '+%F %T') backup enviado OK" >> "$LOG"
else
  echo "$(date '+%F %T') ERRO no push (ver acima)" >> "$LOG"
  avisar "🔴 Backup: o envio pro GitHub FALHOU agora. O backup pode estar parado — peça pro seu assistente olhar o log (~/semente-bin/log/backup.log)."
fi
