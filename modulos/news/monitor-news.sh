#!/usr/bin/env bash
# Semente — monitor de NOTÍCIA GIGANTE (cross-portal). Cron de 5 em 5 min.
#
# A régua: notícia grande sai em VÁRIOS portais ao mesmo tempo, não em um só.
#   1) news.py --check cruza os portais. Sinal BARATO: só dispara um
#      "CANDIDATO_GIGANTE" quando a mesma notícia aparece forte em >=N portais PT.
#   2) Só AÍ acordamos o Claude (headless) pra dar o veredito: é REALMENTE
#      uma notícia gigante/estouro, ou só tema em alta? Quase nunca há candidato,
#      então o LLM quase nunca roda — barato em chamada, alto em precisão.
#   3) Veredito SIM => alerta no Telegram (via alerta.sh). NÃO => fica quieto.
#
# O coletor já faz dedup do dia (não re-emite o mesmo evento), então não spama.
# Pausar: criar ~/monitor-news.PAUSED (apagar pra religar).
# Config: tudo de ~/.config/semente/config.env (nada fixo aqui).
set -u

CONFIG="${SEMENTE_CONFIG:-$HOME/.config/semente/config.env}"
# shellcheck disable=SC1090
[ -f "$CONFIG" ] && { set -a; . "$CONFIG"; set +a; }

CLAUDE="${CLAUDE_BIN:-$(command -v claude || echo "$HOME/.local/bin/claude")}"
SCRIPT="$HOME/semente-bin/news.py"
ALERTA="$HOME/semente-bin/alerta.sh"
LOG="$HOME/semente-bin/log/monitor-news.log"
PAUSED="$HOME/monitor-news.PAUSED"
EMPTYMCP="$HOME/.config/semente/empty-mcp.json"
DONO="${NOME_DONO:-o dono}"

mkdir -p "$(dirname "$LOG")"
[ -f "$EMPTYMCP" ] || echo '{"mcpServers":{}}' > "$EMPTYMCP"

ts() { date '+%F %T'; }
log() { echo "$(ts) $*" >> "$LOG"; }
[ -f "$PAUSED" ] && exit 0

CAND=$(python3 "$SCRIPT" --check 2>>"$LOG")
case "$CAND" in
  CANDIDATO_GIGANTE*) : ;;          # tem candidato — segue pro juiz
  *) exit 0 ;;                      # nada convergindo forte — sai calado
esac

log "candidato a gigante detectado:"
printf '%s\n' "$CAND" >> "$LOG"

# ---- O JUIZ (LLM) ------------------------------------------------------------
read -r -d '' PROMPT <<EOF
Você é o assistente pessoal de ${DONO} julgando se uma notícia é GIGANTE. Ninguém está respondendo: o que você devolver vai pra um robô, não pra uma pessoa.

CONTEXTO: vários portais brasileiros (G1, CNN, Folha, Poder360, Jovem Pan, BBC Brasil) estão, ao mesmo tempo, destacando uma mesma notícia. Convergência assim costuma indicar algo grande — MAS nem sempre: às vezes é só um tema em alta (ex.: Copa do Mundo chegando, pauta política rotineira do Congresso), que NÃO é o que interessa.

A RÉGUA — só conta como GIGANTE a notícia que ESTOUROU AGORA e para todo mundo ao mesmo tempo, do tipo que faz a pessoa parar o que está fazendo:
- Exemplos GIGANTES: morte de uma figura enorme (presidente, ex-presidente, celebridade máxima); ataque/guerra começando (um país bombardeia outro); atentado, catástrofe grave (terremoto com muitos mortos, tragédia nacional); golpe, prisão de figura altíssima; algo histórico e inesperado.
- NÃO é gigante: tema recorrente ou esperado (Copa do Mundo, eleição em andamento, novela, clima, economia do dia), nota política rotineira, esporte comum, matéria de comportamento, "veja/saiba/entenda".
- NÃO é gigante: ação de governo/órgão regulador — suspender/recolher/proibir vacina, remédio, produto, alimento; abrir investigação; "X reações/mortes EM INVESTIGAÇÃO" ou "sob apuração"; alerta sanitário. Mesmo com mortes citadas, enquanto é apuração/medida preventiva NÃO é gigante — é matéria importante de painel, não interrupção.
- A peneira final: só é GIGANTE um FATO CONSUMADO, súbito e chocante, já confirmado (morreu, explodiu, caiu, foi preso, começou a guerra) — não um processo, uma medida, uma suspeita ou uma investigação em curso.

Na dúvida, é NÃO. É melhor deixar passar do que incomodar ${DONO} com notícia que não é gigante.

MANCHETES QUE CONVERGIRAM AGORA:
${CAND#CANDIDATO_GIGANTE}

RESPONDA EXATAMENTE EM 2 LINHAS:
- Linha 1: só "SIM" ou "NAO".
- Linha 2: se SIM, UMA frase curta dizendo qual é a notícia (pro dono, direto). Se NAO, uma palavra ("rotina").
EOF

OUT=$(timeout 180 "$CLAUDE" -p "$PROMPT" --output-format json --permission-mode bypassPermissions \
        --mcp-config "$EMPTYMCP" --strict-mcp-config 2>>"$LOG")
RC=$?
if [ "$RC" -ne 0 ]; then log "juiz falhou (rc=$RC) — não aviso"; exit 0; fi

VEREDITO=$(printf '%s' "$OUT" | python3 -c '
import sys, json
try: d=json.load(sys.stdin)
except Exception: print(""); sys.exit(0)
print((d.get("result","") or "").strip())
')
log "veredito: ${VEREDITO//$'\n'/ | }"

LINHA1=$(printf '%s' "$VEREDITO" | head -1 | tr "[:lower:]" "[:upper:]" | tr -cd "A-Z")
case "$LINHA1" in
  SIM*) : ;;
  *) log "juiz disse que NÃO é gigante — fico quieto"; exit 0 ;;
esac

RESUMO=$(printf '%s' "$VEREDITO" | sed -n '2,$p' | tr '\n' ' ' | sed 's/  */ /g')
[ -z "$RESUMO" ] && RESUMO="(veja nos portais)"

MSG="Está em vários portais ao mesmo tempo:

$RESUMO

(não precisa entrar em portal nenhum; me chama \"News\" que eu te dou o resumo do que está rolando.)"

"$ALERTA" --titulo "🚨 Notícia GRANDE agora" "$MSG" >>"$LOG" 2>&1 \
  && log "ALERTA GIGANTE enviado: $RESUMO" || log "falha ao enviar alerta"
exit 0
