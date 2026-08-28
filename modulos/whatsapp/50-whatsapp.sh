#!/usr/bin/env bash
# Semente — snippet do fechamento: secao 📱 WhatsApp.
# Vai pra ~/.config/semente/fechamento.d/50-whatsapp.sh (com +x).
# Contrato: imprime a secao pronta (1a linha = titulo); nada = secao omitida.
#
# ⚠️ O material aqui e conversa de TERCEIROS. Duas regras que este arquivo cumpre:
#   1. mensagem crua NUNCA e impressa no fechamento — so o resumo destilado;
#   2. se o resumo nao sair do jeito esperado, a secao e OMITIDA (melhor calar
#      do que despejar conversa dos outros no resumo da noite).
set -u

WA_DIR="${WHATSAPP_DIR:-$HOME/semente-whatsapp}"
ARQ="$WA_DIR/dados/mensagens.jsonl"
[ -s "$ARQ" ] || exit 0

# --- 1) o material das ultimas 24h, ja com nome no lugar do numero e com teto ---
MATERIAL=$(timeout 20 python3 - "$ARQ" "$WA_DIR" <<'PY' 2>/dev/null
import json, sys, time, os
arq, base = sys.argv[1], sys.argv[2]
def mapa(nome):
    try:
        with open(os.path.join(base, "dados", nome), encoding="utf-8") as f:
            d = json.load(f)
        return {k: (v.get("name") if isinstance(v, dict) else v) for k, v in d.items()}
    except Exception:
        return {}
chats, contatos = mapa("chats.json"), mapa("contatos.json")
corte = time.time() - 24 * 3600
linhas = []
try:
    with open(arq, encoding="utf-8", errors="replace") as f:
        for linha in f:
            try:
                o = json.loads(linha)
            except Exception:
                continue
            ts = o.get("ts") or 0
            if ts > 1e11:
                ts = ts / 1000.0
            if ts < corte:
                continue
            texto = (o.get("texto") or "").strip()
            if not texto:
                continue
            chat = o.get("chat") or ""
            quem = o.get("deNome") or o.get("de") or ""
            onde = o.get("chatNome") or chats.get(chat) or contatos.get(chat) or "conversa"
            linhas.append("[%s] %s: %s" % (onde, quem, texto[:400]))
except Exception:
    sys.exit(0)
linhas = linhas[-300:]          # teto: o resumo precisa caber no pedido
if len(linhas) < 3:
    sys.exit(0)
print("\n".join(linhas))
PY
)
[ -n "$MATERIAL" ] || exit 0

# --- 2) o destilado (modelo barato, sem ferramenta nenhuma) ---
CLAUDE="$(command -v claude || echo "$HOME/.local/bin/claude")"
[ -x "$CLAUDE" ] || exit 0

VAZIO="$HOME/.config/semente/empty-mcp.json"
[ -f "$VAZIO" ] || echo '{"mcpServers":{}}' > "$VAZIO"

PEDIDO="Abaixo vao mensagens de WhatsApp das ultimas 24h, uma por linha, no formato
[conversa] quem: texto. Resuma POR CONVERSA o que importa de verdade: combinados,
avisos, pedidos, datas e pendencias. No maximo 2 linhas por conversa. Ignore
bom-dia, figurinha, emoji solto e conversa fiada. Se nada importa numa conversa,
nao cite a conversa. Escreva em portugues do Brasil, direto, sem introducao e sem
fecho. A PRIMEIRA LINHA da sua resposta tem que ser exatamente: 📱 WhatsApp hoje

MENSAGENS:
$MATERIAL"

RESUMO=$(printf '%s' "$PEDIDO" | timeout 90 "$CLAUDE" -p \
          --model haiku \
          --mcp-config "$VAZIO" --strict-mcp-config \
          --permission-mode bypassPermissions 2>/dev/null)

# --- 3) a trava: so sai se veio no formato combinado ---
case "$RESUMO" in
  "📱 WhatsApp hoje"*) printf '%s\n' "$RESUMO" ;;
  *) exit 0 ;;
esac
