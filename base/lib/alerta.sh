#!/usr/bin/env bash
# Semente — alerta.sh: o mensageiro único dos robôs.
# Manda mensagem no Telegram do dono via API do bot (curl puro, sem dependência).
# TODOS os robôs do kit (backup, monitor, fechamento...) avisam por aqui — assim
# a configuração mora num lugar só (~/.config/semente/config.env) e trocar de
# canal no futuro é mexer num arquivo só.
#
# Uso:
#   alerta.sh "mensagem"
#   alerta.sh --titulo "💾 Backup" "mensagem"
#   echo "mensagem" | alerta.sh --titulo "🖥️ VPS" -      (lê da entrada padrão)
#
# Lê de ~/.config/semente/config.env:
#   TELEGRAM_BOT_TOKEN       (obrigatório) token do bot, do BotFather
#   TELEGRAM_OWNER_ID        (obrigatório) chat id do dono
#   TELEGRAM_ALERTA_CHAT_ID  (opcional) outro chat pra receber alertas de robô
#
# Sai com código 0 se TODAS as partes foram entregues; 1 se algo falhou
# (config faltando, sem internet, API recusou). Quem chama decide o que fazer.
set -u

CONFIG="${SEMENTE_CONFIG:-$HOME/.config/semente/config.env}"

if [ ! -f "$CONFIG" ]; then
  echo "alerta.sh: config não existe: $CONFIG" >&2
  exit 1
fi
# shellcheck disable=SC1090
set -a; . "$CONFIG"; set +a

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_OWNER_ID:-}" ]; then
  echo "alerta.sh: TELEGRAM_BOT_TOKEN/TELEGRAM_OWNER_ID faltando em $CONFIG" >&2
  exit 1
fi

CHAT="${TELEGRAM_ALERTA_CHAT_ID:-$TELEGRAM_OWNER_ID}"

TITULO=""
if [ "${1:-}" = "--titulo" ]; then
  TITULO="${2:-}"
  shift 2
fi

MSG="${1:-}"
if [ "$MSG" = "-" ] || [ -z "$MSG" ]; then
  MSG=$(cat)   # entrada padrão
fi
[ -n "$TITULO" ] && MSG="${TITULO}"$'\n'"${MSG}"

if [ -z "$MSG" ]; then
  echo "alerta.sh: mensagem vazia, nada a enviar" >&2
  exit 1
fi

enviar() {  # $1 = texto (<=4096 chars). Sem parse_mode de propósito: nunca quebra por formatação.
  curl -sS --max-time 20 \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${CHAT}" \
    --data-urlencode "disable_web_page_preview=true" \
    --data-urlencode "text=$1" 2>&1 | grep -q '"ok":true'
}

# Telegram aceita até 4096 chars por mensagem; quebramos em pedaços de até 3900,
# de preferência numa quebra de linha, pra não cortar frase no meio.
RC=0
while [ ${#MSG} -gt 3900 ]; do
  PARTE="${MSG:0:3900}"
  CORTE="${PARTE%$'\n'*}"
  [ -n "$CORTE" ] || CORTE="$PARTE"
  enviar "$CORTE" || RC=1
  MSG="${MSG:${#CORTE}}"
  MSG="${MSG#$'\n'}"
done
[ -n "$MSG" ] && { enviar "$MSG" || RC=1; }

exit $RC
