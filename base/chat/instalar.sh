#!/usr/bin/env bash
# ============================================================================
# INSTALADOR DO CHAT WEB  (kit NEXUM Semente)
#
# Faz TUDO: venv, config, servidor web com HTTPS, servico ligado e vigia.
# Nao pergunta nada — a unica escolha (a senha) sai daqui pronta e e mostrada
# no fim, uma vez.
#
#   bash instalar.sh
#
# Requisitos: o modulo do cerebro e o do Telegram ja instalados (a transcricao
# de audio reusa o Whisper de la), e as portas 80/443 abertas (o blindar.sh ja
# abre). Rode como o usuario dono, NAO como root — ele pede sudo quando precisa.
# ============================================================================
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINO="$HOME/semente-chat"
CONFIG="$HOME/.config/semente/config.env"

ok(){ echo "  ✅ $*"; }
erro(){ echo "  ❌ $*" >&2; exit 1; }
passo(){ echo; echo "▶ $*"; }

[ "$(id -u)" -eq 0 ] && erro "rode como o usuario dono (sem sudo na frente)"

# ---------------------------------------------------------------- 1. fundacao
passo "1/7 conferindo a fundacao"
command -v python3 >/dev/null || erro "python3 nao encontrado"
CLAUDE_BIN="$(command -v claude || echo "$HOME/.local/bin/claude")"
[ -x "$CLAUDE_BIN" ] || erro "o Claude Code nao esta instalado/logado nesta maquina"
ok "claude: $($CLAUDE_BIN --version 2>/dev/null | head -1)"
# o teste que vale: o stream-json e a fundacao do chat inteiro
if ! "$CLAUDE_BIN" -p "responda apenas: ok" --output-format stream-json --verbose \
      --permission-mode bypassPermissions 2>/dev/null | head -3 | grep -q '"type"'; then
  erro "o claude nao devolveu stream-json. Resolva isso ANTES — e a fundacao inteira."
fi
ok "stream-json respondendo"
mkdir -p "$(dirname "$CONFIG")"; touch "$CONFIG"; chmod 600 "$CONFIG"

# ---------------------------------------------------------------- 2. copia
passo "2/7 instalando em $DESTINO"
mkdir -p "$DESTINO"
cp "$KIT/chat.py" "$KIT/tela.html" "$KIT/run.sh" "$KIT/chatctl.sh" \
   "$KIT/requirements.txt" "$DESTINO/"
chmod +x "$DESTINO/run.sh" "$DESTINO/chatctl.sh"
ok "arquivos no lugar"

# ---------------------------------------------------------------- 3. venv
passo "3/7 preparando o ambiente do python"
if [ ! -x "$DESTINO/venv/bin/python" ]; then
  python3 -m venv "$DESTINO/venv" 2>/dev/null || {
    echo "  instalando python3-venv..."; sudo apt-get install -y -qq python3-venv >/dev/null
    python3 -m venv "$DESTINO/venv"; }
fi
"$DESTINO/venv/bin/pip" install -q --upgrade pip >/dev/null
"$DESTINO/venv/bin/pip" install -q -r "$DESTINO/requirements.txt"
ok "flask instalado"

# ---------------------------------------------------------------- 4. config
passo "4/7 escrevendo a configuracao"
# SEMPRE acrescenta chave; nunca sobrescreve o arquivo (ele guarda o kit inteiro).
addcfg(){ grep -q "^$1=" "$CONFIG" || echo "$1=$2" >> "$CONFIG"; }
SENHA_NOVA=""
if ! grep -q "^CHAT_SENHA=" "$CONFIG"; then
  SENHA_NOVA="$(tr -dc 'a-z2-9' < /dev/urandom | head -c 5)-$(tr -dc 'a-z2-9' < /dev/urandom | head -c 5)"
  echo "CHAT_SENHA=$SENHA_NOVA" >> "$CONFIG"
fi
addcfg CHAT_SEGREDO "$(tr -dc 'a-f0-9' < /dev/urandom | head -c 48)"
addcfg CHAT_PORTA 8800
addcfg CHAT_MAX_TURNOS 2
chmod 600 "$CONFIG"
PORTA="$(grep -E '^CHAT_PORTA=' "$CONFIG" | cut -d= -f2)"
ok "config em $CONFIG (chmod 600)"

# ---------------------------------------------------------------- 5. endereco (HTTPS)
passo "5/7 pondo o chat num endereco com cadeado"
IP="$(curl -s --max-time 8 https://api.ipify.org || true)"
[ -n "$IP" ] || IP="$(hostname -I | awk '{print $1}')"
[ -n "$IP" ] || erro "nao consegui descobrir o IP desta maquina"
ENDERECO="chat.${IP}.sslip.io"      # dominio-por-IP: HTTPS de graca, sem comprar dominio

if ! command -v caddy >/dev/null; then
  echo "  instalando o Caddy (servidor web que cuida do HTTPS sozinho)..."
  sudo apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl >/dev/null
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -qq >/dev/null
  sudo apt-get install -y -qq caddy >/dev/null
fi
ok "caddy: $(caddy version | head -1)"

BLOCO="/etc/caddy/Caddyfile"
if ! sudo grep -q "$ENDERECO" "$BLOCO" 2>/dev/null; then
  sudo cp "$BLOCO" "$BLOCO.antes-do-chat" 2>/dev/null || true
  sudo tee -a "$BLOCO" >/dev/null <<CADDY

# ---- chat do assistente (kit Semente) ----
$ENDERECO {
    # o streaming (SSE) NAO pode passar por compressao nem por buffer:
    # senao a resposta chega toda de uma vez, no fim.
    @stream path /api/conversas/*/stream
    handle @stream {
        reverse_proxy 127.0.0.1:$PORTA {
            flush_interval -1
        }
    }
    handle {
        encode zstd gzip
        reverse_proxy 127.0.0.1:$PORTA
    }
}
CADDY
fi
sudo systemctl reload caddy 2>/dev/null || sudo systemctl restart caddy
ok "endereco: https://$ENDERECO"

# ---------------------------------------------------------------- 6. ligar
passo "6/7 ligando"
bash "$DESTINO/chatctl.sh" start >/dev/null
bash "$DESTINO/chatctl.sh" install-watchdog >/dev/null
sleep 3
ok "$(bash "$DESTINO/chatctl.sh" status | tail -1)"

# ---------------------------------------------------------------- 7. provar
passo "7/7 conferindo pelo caminho por onde a pessoa entra"
CODIGO="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "https://$ENDERECO/" || echo 000)"
[ "$CODIGO" = "200" ] || {
  echo "  ⚠️  o endereco respondeu $CODIGO (o certificado pode levar ~1 min na 1a vez)."
  echo "     confira: curl -I https://$ENDERECO/   ·   $DESTINO/chatctl.sh log"
  exit 1; }
ok "https://$ENDERECO respondeu 200 (a tela de entrar)"

echo
echo "════════════════════════════════════════════════════════"
echo "  CHAT NO AR:  https://$ENDERECO"
[ -n "$SENHA_NOVA" ] && echo "  SENHA:       $SENHA_NOVA   (anote — so aparece aqui)"
[ -z "$SENHA_NOVA" ] && echo "  SENHA:       a que ja estava em $CONFIG (CHAT_SENHA)"
echo "════════════════════════════════════════════════════════"
echo "  No celular: abra o endereco, entre, e use 'Adicionar a"
echo "  tela de inicio' — vira um app."
echo "  Controle:   $DESTINO/chatctl.sh {status|log|restart}"
