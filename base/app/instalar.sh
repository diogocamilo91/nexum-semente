#!/usr/bin/env bash
# ============================================================================
# INSTALADOR DO APP PESSOAL  (kit NEXUM Semente)
#
# Faz TUDO: ambiente, config, servidor web com HTTPS, servico ligado e vigia.
# Nao pergunta nada — a unica escolha (a senha) sai daqui pronta e e mostrada
# no fim, uma vez.
#
#   bash instalar.sh
#
# Opcoes (quase ninguem precisa):
#   --sem-endereco   nao mexe no Caddy (pra quem ja tem um servidor web/dominio)
#   --sem-vigia      nao instala o despertador que religa o app sozinho
#   APP_DIR=...      instala em outra pasta (o padrao e ~/semente-app)
#
# Requisitos: o modulo do cerebro e o do Telegram ja instalados (a transcricao
# de audio reusa o Whisper de la), e as portas 80/443 abertas (o blindar.sh ja
# abre). Rode como o usuario dono, NAO como root — ele pede sudo quando precisa.
# ============================================================================
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINO="${APP_DIR:-$HOME/semente-app}"
COM_ENDERECO=1; COM_VIGIA=1
for a in "$@"; do
  case "$a" in
    --sem-endereco) COM_ENDERECO=0 ;;
    --sem-vigia)    COM_VIGIA=0 ;;
    *) echo "opcao desconhecida: $a" >&2; exit 2 ;;
  esac
done
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
# preserva os dados (conversas e anexos) se ja houver uma instalacao aqui
cp -r "$KIT"/casca.py "$KIT"/servidor.py "$KIT"/run.sh "$KIT"/appctl.sh \
      "$KIT"/requirements.txt "$KIT"/CONTRATO.md "$DESTINO"/
rm -rf "$DESTINO/telas.novas" "$DESTINO/nucleo.novo"
cp -r "$KIT"/telas "$DESTINO"/telas.novas
cp -r "$KIT"/nucleo "$DESTINO"/nucleo.novo
rm -rf "$DESTINO/estatico"
cp -r "$KIT"/estatico "$DESTINO"/estatico
rm -rf "$DESTINO/telas" "$DESTINO/nucleo"
mv "$DESTINO/telas.novas" "$DESTINO/telas"
mv "$DESTINO/nucleo.novo" "$DESTINO/nucleo"
chmod +x "$DESTINO/run.sh" "$DESTINO/appctl.sh"
mkdir -p "$DESTINO/dados/anexos"
ok "arquivos no lugar (as conversas antigas, se havia, continuam em dados/)"

# ---------------------------------------------------------------- 3. ambiente
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
# Sorteia N caracteres do alfabeto dado. O `head` fecha o cano na cara do `tr`,
# que morre de SIGPIPE — com `pipefail` isso derruba o instalador inteiro. E so
# derrubava na PRIMEIRA instalacao (quando ainda nao existe senha), que e
# justamente a da pessoa nova. Por isso o pipefail sai so aqui dentro.
sorteia(){
  local antes; antes=$(set +o | grep pipefail)
  set +o pipefail
  LC_ALL=C tr -dc "$1" < /dev/urandom 2>/dev/null | head -c "$2"
  eval "$antes"
}
SENHA_NOVA=""
if ! grep -q "^CHAT_SENHA=" "$CONFIG"; then
  SENHA_NOVA="$(sorteia 'a-z2-9' 5)-$(sorteia 'a-z2-9' 5)"
  echo "CHAT_SENHA=$SENHA_NOVA" >> "$CONFIG"
fi
addcfg CHAT_SEGREDO "$(sorteia 'a-f0-9' 48)"
addcfg CHAT_PORTA 8800
addcfg CHAT_MAX_TURNOS 2
chmod 600 "$CONFIG"
PORTA="$(grep -E '^CHAT_PORTA=' "$CONFIG" | cut -d= -f2)"
ok "config em $CONFIG (chmod 600)"

# ---------------------------------------------------------------- 5. endereco
passo "5/7 pondo o app num endereco com cadeado"
if [ "$COM_ENDERECO" = "0" ]; then
  ENDERECO="127.0.0.1:$PORTA"
  ok "pulado a pedido (--sem-endereco) — aponte o seu servidor web pra 127.0.0.1:$PORTA"
else
IP="$(curl -s --max-time 8 https://api.ipify.org || true)"
[ -n "$IP" ] || IP="$(hostname -I | awk '{print $1}')"
[ -n "$IP" ] || erro "nao consegui descobrir o IP desta maquina"
ENDERECO="app.${IP}.sslip.io"      # dominio-por-IP: HTTPS de graca, sem comprar dominio

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

CADDYFILE="/etc/caddy/Caddyfile"
if ! sudo grep -q "$ENDERECO" "$CADDYFILE" 2>/dev/null; then
  sudo cp "$CADDYFILE" "$CADDYFILE.antes-do-app" 2>/dev/null || true
  sudo tee -a "$CADDYFILE" >/dev/null <<CADDY

# ---- app pessoal do assistente (kit Semente) ----
$ENDERECO {
    # o streaming da resposta (SSE) NAO pode passar por compressao nem por buffer:
    # senao a resposta chega toda de uma vez, no fim.
    @stream path /api/chat/conversas/*/stream
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
fi

# ---------------------------------------------------------------- 6. ligar
passo "6/7 ligando"
bash "$DESTINO/appctl.sh" start >/dev/null
if [ "$COM_VIGIA" = "1" ]; then
  bash "$DESTINO/appctl.sh" install-watchdog >/dev/null
else
  ok "vigia pulado a pedido (--sem-vigia): o app NAO religa sozinho nem sobe no boot"
fi
sleep 4
ok "$(bash "$DESTINO/appctl.sh" status | head -1)"

# ---------------------------------------------------------------- 7. provar
passo "7/7 conferindo pelo caminho por onde a pessoa entra"
if [ "$COM_ENDERECO" = "0" ]; then
  ALVO="http://127.0.0.1:$PORTA/"
else
  ALVO="https://$ENDERECO/"
fi
CODIGO="$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 "$ALVO" || echo 000)"
[ "$CODIGO" = "200" ] || {
  echo "  ⚠️  o endereco respondeu $CODIGO (o certificado pode levar ~1 min na 1a vez)."
  echo "     confira: curl -I https://$ENDERECO/   ·   $DESTINO/appctl.sh log"
  exit 1; }
ok "$ALVO respondeu 200 (a tela de entrar)"
echo "  telas que subiram:"
bash "$DESTINO/appctl.sh" telas | sed 's/^/    /'

echo
echo "════════════════════════════════════════════════════════"
echo "  APP NO AR:   $ALVO"
[ -n "$SENHA_NOVA" ] && echo "  SENHA:       $SENHA_NOVA   (anote — so aparece aqui)"
[ -z "$SENHA_NOVA" ] && echo "  SENHA:       a que ja estava em $CONFIG (CHAT_SENHA)"
echo "════════════════════════════════════════════════════════"
echo "  No celular: abra o endereco, entre, e use 'Adicionar a"
echo "  tela de inicio' — vira um app de verdade."
echo "  Controle:   $DESTINO/appctl.sh {status|log|telas|restart}"
echo
echo "  Modulo instalado depois (e-mail, agenda, Drive...) aparece"
echo "  sozinho na gaveta: e so rodar este instalador de novo."
