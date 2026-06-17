#!/usr/bin/env bash
# Semente — snippet do fechamento: seção 🎓 Aprendizado.
# Vai pra ~/.config/semente/fechamento.d/40-aprendizado.sh (com +x).
#
# Coleta o que os canais do dono lançaram nas últimas 30h e pede pro Claude
# (headless) redigir uma curadoria curta. Se o Claude falhar/demorar, cai no
# plano B: lista simples dos títulos (a seção nunca fica muda por causa do redator).
# Contrato do fechamento: <120s no total; imprimir nada = seção omitida hoje.
# (orçamento interno: 40s coletor + 70s redator = 110s no pior caso — folga de 10s
#  pro plano B sair ANTES do SNIPPET_TIMEOUT=120 do fechamento matar o snippet)
set -u

CONFIG="${SEMENTE_CONFIG:-$HOME/.config/semente/config.env}"
# shellcheck disable=SC1090
[ -f "$CONFIG" ] && { set -a; . "$CONFIG"; set +a; }
CLAUDE="${CLAUDE_BIN:-$(command -v claude || echo "$HOME/.local/bin/claude")}"
EMPTYMCP="$HOME/.config/semente/empty-mcp.json"
[ -f "$EMPTYMCP" ] || echo '{"mcpServers":{}}' > "$EMPTYMCP"

MATERIAL=$(timeout 40 python3 "$HOME/semente-bin/aprendizado.py" --horas 30 --sem-shorts 2>/dev/null)

# nada novo (ou coletor mudo) => seção omitida hoje
case "$MATERIAL" in
  ""|*"0 vídeo(s) novo(s)"*|*"sem canais configurados"*) exit 0 ;;
esac

# plano B pronto desde já: a lista crua, encurtada
PLANO_B="🎓 Aprendizado — novos nos seus canais
$(printf '%s\n' "$MATERIAL" | grep -E '^\s+•' | sed 's/^ *//' | head -10)"

read -r -d '' PROMPT <<EOF
Você é o assistente pessoal de ${NOME_DONO:-uma pessoa} montando a seção "Aprendizado" do resumo da noite. Abaixo, os vídeos que os canais que o dono SEGUE lançaram hoje. Escreva a seção em português do Brasil:
- 1ª linha EXATAMENTE: 🎓 Aprendizado
- depois, até 6 itens "• [Canal] título — 1 frase do que parece ser (pelo título)". Não invente conteúdo que o título não sustenta; se o título não diz nada, só liste.
- inclua o link de cada item numa linha abaixo dele.
- escolha os mais interessantes se houver mais de 6; shorts por último.
- nada além da seção (sem comentários seus).

MATERIAL:
$MATERIAL
EOF

SAIDA=$(timeout 70 "$CLAUDE" -p "$PROMPT" --model claude-haiku-4-5 --output-format json --permission-mode bypassPermissions \
          --mcp-config "$EMPTYMCP" --strict-mcp-config 2>/dev/null | python3 -c '
import sys, json
try: d=json.load(sys.stdin)
except Exception: sys.exit(0)
print((d.get("result","") or "").strip())
')

case "$SAIDA" in
  "🎓 Aprendizado"*) printf '%s\n' "$SAIDA" ;;   # redator respondeu direito
  *)                 printf '%s\n' "$PLANO_B" ;; # resposta-fantasma/erro => lista crua
esac
