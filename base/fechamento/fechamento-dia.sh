#!/usr/bin/env bash
# Semente — FECHAMENTO DO DIA (o "relatório de vida" do assistente).
# Roda 1x/dia à noite (cron 21h) e manda no Telegram do dono UM resumo do dia:
# a saúde da VPS + a seção de cada módulo instalado (agenda, e-mails...).
#
# ARQUITETURA DE PLUGINS: este script NÃO conhece os módulos. Cada módulo
# instalado dropa um snippet executável em ~/.config/semente/fechamento.d/
# (ex.: 10-agenda.sh, 20-emails.sh). Na hora do fechamento, cada snippet roda
# e o que ele imprimir vira uma seção. Contrato do snippet:
#   - executável (chmod +x), roda em <120s, imprime texto pronto pro Telegram;
#   - 1ª linha = título da seção (ex.: "📅 Amanhã na agenda");
#   - imprimir NADA = seção omitida hoje (sem erro);
#   - NUNCA aguardar input, NUNCA mandar mensagem por conta própria (quem manda
#     é o fechamento), NUNCA escrever fora dos próprios arquivos/logs.
# A ordem é alfabética — por isso o prefixo numérico (10-, 20-, ...).
#
# Quando roda: cron 21h. Na mão: bash ~/semente-bin/fechamento-dia.sh
# Testar sem mandar: SEMENTE_DRYRUN=1 bash ~/semente-bin/fechamento-dia.sh
# Pausar: criar ~/fechamento-dia.PAUSED (apagar pra religar).
set -u

CONFIG="$HOME/.config/semente/config.env"
SNIPPETS="$HOME/.config/semente/fechamento.d"
ALERTA="$HOME/semente-bin/alerta.sh"
SAUDE="$HOME/semente-bin/saude_vps.py"
LOG="$HOME/semente-bin/log/fechamento.log"
PAUSED="$HOME/fechamento-dia.PAUSED"
SNIPPET_TIMEOUT=120

mkdir -p "$(dirname "$LOG")" "$SNIPPETS"
ts()  { date '+%F %T'; }
log() { echo "$(ts) $*" >> "$LOG"; }

[ -f "$PAUSED" ] && { log "pausado (existe $PAUSED) — saindo"; exit 0; }
# shellcheck disable=SC1090
[ -f "$CONFIG" ] && { set -a; . "$CONFIG"; set +a; }

# dia da semana em português, sem depender de locale instalado
case "$(date +%u)" in
  1) DIA_SEM="segunda-feira";; 2) DIA_SEM="terça-feira";; 3) DIA_SEM="quarta-feira";;
  4) DIA_SEM="quinta-feira";; 5) DIA_SEM="sexta-feira";; 6) DIA_SEM="sábado";; 7) DIA_SEM="domingo";;
esac

MSG="🌙 Fechamento do dia — $(date '+%d/%m/%Y'), $DIA_SEM"

# --- seções dos módulos (plugins) ---
ALGUM_SNIPPET=0
for s in "$SNIPPETS"/*.sh; do
  [ -e "$s" ] || break
  [ -x "$s" ] || { log "snippet sem +x, pulado: $s"; continue; }
  ALGUM_SNIPPET=1
  NOME=$(basename "$s")
  if SAIDA=$(timeout "$SNIPPET_TIMEOUT" bash "$s" 2>>"$LOG"); then
    if [ -n "$SAIDA" ]; then
      MSG="$MSG"$'\n\n'"$SAIDA"
      log "seção ok: $NOME"
    else
      log "seção vazia (omitida): $NOME"
    fi
  else
    MSG="$MSG"$'\n\n'"⚠️ A seção '$NOME' falhou hoje (ver log)."
    log "seção FALHOU: $NOME"
  fi
done
[ "$ALGUM_SNIPPET" -eq 0 ] && log "nenhum snippet em $SNIPPETS (só VPS no fechamento)"

# --- saúde da VPS (sempre presente; é a base) ---
if [ -f "$SAUDE" ]; then
  VPS=$(timeout 60 python3 "$SAUDE" 2>>"$LOG") || VPS="🖥️ VPS: não consegui medir hoje (ver log)."
else
  VPS="🖥️ VPS: monitor ainda não instalado."
fi
MSG="$MSG"$'\n\n'"$VPS"

# --- enviar ---
if [ "${SEMENTE_DRYRUN:-0}" = "1" ]; then
  printf '%s\n' "----[dryrun] mandaria no Telegram:----" "$MSG"
  exit 0
fi

if "$ALERTA" "$MSG" >>"$LOG" 2>&1; then
  log "fechamento enviado"
else
  log "ERRO ao enviar o fechamento (alerta.sh falhou)"
  exit 1
fi
exit 0
