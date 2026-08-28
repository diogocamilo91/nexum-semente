#!/usr/bin/env bash
# ============================================================================
# INSTALADOR DO ESPELHO DO WHATSAPP  (kit NEXUM Semente)   ⚠️ EXPERIMENTAL
#
#   bash instalar.sh
#
# ANTES DE RODAR ISTO: faça a conversa honesta do ENTREVISTA.md com o dono e
# tenha o SIM dele. Este módulo lê conversas de OUTRAS PESSOAS e tem risco
# (pequeno, mas real) pro número dele. Recusa não se discute duas vezes.
#
# O que ele faz: instala a biblioteca na versão ATUAL (não congelada — ela muda
# todo mês acompanhando o WhatsApp), monta o coletor SÓ-LEITURA, PROVA o formato
# do que ele grava sem precisar parear, liga e deixa o QR pronto pra leitura.
# O pareamento é do DONO, no celular dele — este script não pareia nada.
#
# Opcoes:  --sem-vigia   nao instala o despertador que religa sozinho
#          WA_DIR=...    instala em outra pasta (padrao ~/semente-whatsapp)
# ============================================================================
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINO="${WA_DIR:-$HOME/semente-whatsapp}"
CONFIG="$HOME/.config/semente/config.env"
COM_VIGIA=1
for a in "$@"; do
  case "$a" in
    --sem-vigia) COM_VIGIA=0 ;;
    *) echo "opcao desconhecida: $a" >&2; exit 2 ;;
  esac
done

ok(){ echo "  ✅ $*"; }
erro(){ echo "  ❌ $*" >&2; exit 1; }
passo(){ echo; echo "▶ $*"; }
manual(){
  echo
  echo "  ⚠️  Este caminho automático não deu certo: $*"
  echo "     NÃO insista aqui. A biblioteca do WhatsApp muda com frequência e o"
  echo "     kit prevê isso: abra $KIT/desenho.md e construa o coletor na mão,"
  echo "     com a versão de hoje. A planta está completa (travas, esqueleto e"
  echo "     checklist de aceitação)."
  exit 1
}

[ "$(id -u)" -eq 0 ] && erro "rode como o usuario dono (sem sudo na frente)"

# ---------------------------------------------------------------- 1. node
passo "1/7 conferindo o Node"
if ! command -v node >/dev/null; then
  echo "  instalando o Node 20..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - >/dev/null 2>&1 \
    || erro "nao consegui preparar a fonte do Node"
  sudo apt-get install -y -qq nodejs >/dev/null || erro "nao consegui instalar o Node"
fi
NODE_MAIOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAIOR" -ge 20 ] || erro "o Node aqui e a versao $NODE_MAIOR; a biblioteca do WhatsApp precisa da 20 ou maior"
ok "node $(node --version)"

# ---------------------------------------------------------------- 2. copia
passo "2/7 instalando em $DESTINO"
mkdir -p "$DESTINO"/{dados,logs,auth}
chmod 700 "$DESTINO/auth"
cp "$KIT/coletor.js" "$KIT/package.json" "$KIT/run.sh" "$KIT/wactl.sh" "$DESTINO"/
chmod +x "$DESTINO/run.sh" "$DESTINO/wactl.sh"
ok "arquivos no lugar (o que ja estava em dados/ continua la)"

# ---------------------------------------------------------------- 3. trava
passo "3/7 conferindo a trava de SO-LEITURA"
# a lista mora aqui, e nao no coletor, senao o proprio comentario dispararia o alarme
if grep -nE 'sendMessage|readMessages|sendPresence|chatModify|updateProfile|sendReceipt|groupParticipantsUpdate' "$DESTINO/coletor.js"; then
  erro "o coletor tem chamada de ESCRITA — nao instale assim"
fi
ok "nenhuma chamada de envio, de marcar-lido, de presenca ou de alteracao"

# ---------------------------------------------------------------- 4. biblioteca
passo "4/7 baixando a biblioteca na versao de hoje"
cd "$DESTINO"
npm install --omit=dev --no-audit --no-fund >/dev/null 2>&1 \
  || manual "a instalacao das dependencias falhou"
VERSAO_BAILEYS="$(node -p "require('$DESTINO/node_modules/baileys/package.json').version" 2>/dev/null || echo '?')"
[ "$VERSAO_BAILEYS" = "?" ] && manual "a biblioteca nao ficou instalada"
ok "biblioteca do WhatsApp: $VERSAO_BAILEYS"
node -e "const b=require('$DESTINO/node_modules/baileys');
  const f=(b.default||b.makeWASocket);
  if(typeof f!=='function') { console.error('a biblioteca mudou de forma'); process.exit(1) }
  for (const nome of ['useMultiFileAuthState','fetchLatestBaileysVersion','DisconnectReason'])
    if(!(nome in b)) { console.error('faltou '+nome); process.exit(1) }
  console.log('ok');" >/dev/null 2>&1 \
  || manual "a versao $VERSAO_BAILEYS mudou as pecas que o coletor usa"
ok "as pecas que o coletor usa continuam existindo nesta versao"

# ---------------------------------------------------------------- 5. prova
passo "5/7 provando o que o coletor GRAVA (sem precisar do celular)"
node "$DESTINO/coletor.js" --autoteste || manual "o caminho de gravacao nao passou na prova"
ok "o registro sai no formato que a tela do app le, e midia entra so como marca"

# ---------------------------------------------------------------- 6. ligar
passo "6/7 ligando e pedindo o QR"
mkdir -p "$(dirname "$CONFIG")"; touch "$CONFIG"; chmod 600 "$CONFIG"
grep -q "^WHATSAPP_ATIVO=" "$CONFIG" || echo "WHATSAPP_ATIVO=sim" >> "$CONFIG"
grep -q "^WHATSAPP_DIR=" "$CONFIG" || echo "WHATSAPP_DIR=$DESTINO" >> "$CONFIG"
chmod 600 "$CONFIG"
bash "$DESTINO/wactl.sh" start >/dev/null
if [ "$COM_VIGIA" = "1" ]; then
  bash "$DESTINO/wactl.sh" install-watchdog >/dev/null
  ok "vigia instalado (religa em ate 2 min e sobe no boot)"
else
  ok "vigia pulado a pedido (--sem-vigia)"
fi

JA_PAREADO=0
[ -s "$DESTINO/auth/creds.json" ] && JA_PAREADO=1
if [ "$JA_PAREADO" = "1" ]; then
  ok "ja havia uma sessao pareada — o espelho voltou sozinho"
else
  echo -n "  esperando o QR aparecer"
  for i in $(seq 1 30); do
    [ -f "$DESTINO/qr.png" ] && break
    echo -n "."; sleep 2
  done
  echo
  [ -f "$DESTINO/qr.png" ] || manual "o QR nao apareceu em 60s (veja $DESTINO/logs/saida.log)"
  ok "QR pronto: $DESTINO/qr.png"
fi

# ---------------------------------------------------------------- 7. fechamento
passo "7/7 encaixando no resumo da noite"
SNIP="$HOME/.config/semente/fechamento.d/50-whatsapp.sh"
mkdir -p "$(dirname "$SNIP")"
if [ ! -f "$SNIP" ]; then
  cp "$KIT/50-whatsapp.sh" "$SNIP"
  chmod +x "$SNIP"
  ok "secao do WhatsApp no fechamento das 21h"
else
  ok "a secao do fechamento ja existia — nao mexi"
fi

echo
echo "════════════════════════════════════════════════════════"
echo "  ESPELHO INSTALADO  ·  biblioteca $VERSAO_BAILEYS"
echo "  Pasta:    $DESTINO   (fora da pasta de conhecimento = fora do backup)"
echo "  Controle: $DESTINO/wactl.sh {status|log|parear}"
echo "════════════════════════════════════════════════════════"
if [ "$JA_PAREADO" = "0" ]; then
  echo "  FALTA O DONO PAREAR — e so ele pode fazer isso:"
  echo "   1. abra o arquivo $DESTINO/qr.png"
  echo "   2. no celular: WhatsApp > Aparelhos conectados > Conectar um aparelho"
  echo "   3. aponte pro QR. O QR vence em ~20s e se renova sozinho."
  echo "   4. confira com: $DESTINO/wactl.sh status  (o numero de mensagens sobe)"
  echo
fi
echo "  Depois disso, rode de novo o instalador do app pra tela do"
echo "  WhatsApp aparecer na gaveta:  bash <kit>/base/app/instalar.sh"
