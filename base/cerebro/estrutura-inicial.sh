#!/usr/bin/env bash
# estrutura-inicial.sh — cria a árvore de conhecimento ~/nexum/ do dono.
#
# Parte do kit NEXUM Semente. Rodar UMA vez, na instalação, DEPOIS que o
# instalador (Claude) criou ~/.config/semente/config.env na entrevista.
#
# Lê de ~/.config/semente/config.env:
#   NOME_ASSISTENTE  (obrigatório) — nome batizado pelo dono
#   NOME_DONO        (obrigatório) — primeiro nome do dono
#
# Idempotente: pode rodar de novo sem estragar nada — NUNCA sobrescreve
# arquivo que já existe (way of life: nunca apagar).

set -euo pipefail

CONFIG="${HOME}/.config/semente/config.env"
BASE="${HOME}/nexum"

if [[ ! -f "$CONFIG" ]]; then
  echo "ERRO: $CONFIG não existe. O instalador precisa criar o config.env (entrevista) antes." >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$CONFIG"

: "${NOME_ASSISTENTE:?ERRO: NOME_ASSISTENTE não definido em $CONFIG}"
: "${NOME_DONO:?ERRO: NOME_DONO não definido em $CONFIG}"

HOJE="$(date +%d/%m/%Y)"

# --- pastas -----------------------------------------------------------------
mkdir -p \
  "$BASE/_nexum" \
  "$BASE/pessoal" \
  "$BASE/estudo" \
  "$BASE/_entrada/em-espera"

# --- helper: escreve arquivo SÓ se não existir ------------------------------
escreve_se_novo() {
  local destino="$1"
  if [[ -e "$destino" ]]; then
    echo "  (já existe, não mexo) $destino"
    return 0
  fi
  cat > "$destino"
  echo "  criado: $destino"
}

echo "Montando a árvore em $BASE ..."

# --- INDEX.md ----------------------------------------------------------------
escreve_se_novo "$BASE/INDEX.md" <<EOF
# ${NOME_ASSISTENTE} — INDEX (mapa de tudo)

> Mapa dos repositories de ${NOME_DONO}. Atualizado pelo ${NOME_ASSISTENTE} a cada organização.
> Criado em ${HOJE}.

## _nexum/ — o cérebro do ${NOME_ASSISTENTE}
- identidade.md · convencoes.md · roteamento.md · ponto_atual.md

## pessoal/ — vida pessoal de ${NOME_DONO}
- (vazio por enquanto — pasta nasce quando chegar o 1º assunto)

## estudo/ — o que ${NOME_DONO} aprende
- (vazio por enquanto)

## _entrada/ — coisa nova esperando ser organizada
- em-espera/ — aguardando autorização de ${NOME_DONO}
EOF

# --- PENDENCIAS.md -------------------------------------------------------------
escreve_se_novo "$BASE/PENDENCIAS.md" <<EOF
# Pendências

> O que ficou pra depois. O ${NOME_ASSISTENTE} adiciona e risca daqui.
> Criado em ${HOJE}. Nada pendente ainda.
EOF

# --- _nexum/ponto_atual.md ----------------------------------------------------
escreve_se_novo "$BASE/_nexum/ponto_atual.md" <<EOF
# ${NOME_ASSISTENTE} — Ponto atual (cola pra retomar)

> Estado vivo da VPS e do que está em andamento. O ${NOME_ASSISTENTE} mantém.

- **${HOJE}** — instalação do kit semente concluída. Estrutura criada.
EOF

# --- LEIA-MEs das áreas ---------------------------------------------------------
escreve_se_novo "$BASE/pessoal/LEIA-ME.md" <<EOF
# pessoal/ — vida pessoal de ${NOME_DONO}

**O que é:** um repository (pasta de .md) por assunto da vida pessoal.
**Status:** vazio — pasta de assunto nasce quando chegar o 1º conteúdo, sempre com um LEIA-ME.md curto.
**Regra:** saúde é 🔒 privado e só entra com autorização (ver \`_nexum/roteamento.md\`).
EOF

escreve_se_novo "$BASE/estudo/LEIA-ME.md" <<EOF
# estudo/ — o que ${NOME_DONO} aprende

**O que é:** uma pasta por área de aprendizado (linux, ia, ...).
**Status:** vazio — área nasce quando chegar o 1º assunto.
EOF

escreve_se_novo "$BASE/_entrada/LEIA-ME.md" <<EOF
# _entrada/ — caixa de chegada

**O que é:** onde cai coisa nova que ainda não tem casa. O ${NOME_ASSISTENTE} roteia depois (mapa em \`_nexum/roteamento.md\`).
**em-espera/:** conhecimento sério (trabalho, saúde) aguardando ${NOME_DONO} autorizar. Nada entra sozinho.
EOF

escreve_se_novo "$BASE/_entrada/em-espera/LEIA-ME.md" <<EOF
# em-espera/ — aguardando autorização

Conteúdo que o ${NOME_ASSISTENTE} NÃO incorpora sozinho (trabalho/negócio, saúde).
Fica aqui até ${NOME_DONO} dar OK no Telegram. Nunca apagar — autorizado vira repository, negado fica aqui marcado.
EOF

echo
echo "Pronto. Árvore criada/conferida em $BASE."
echo "Próximo passo do instalador: preencher os templates do cérebro (CLAUDE.md, _nexum/*.md) e fazer o git init."
