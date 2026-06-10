# base/cerebro/ — LEIA-ME (instruções pra VOCÊ, Claude instalador)

Você está instalando o **cérebro** do assistente: o `CLAUDE.md` e o `_nexum/` da pessoa. É o primeiro módulo da base — instale ele **antes** de bot, backup e módulos opcionais, porque tudo depende da estrutura `~/nexum/` existir.

## O que tem aqui

| Arquivo | Vira o quê |
|---|---|
| `CLAUDE.md.template` | `~/nexum/CLAUDE.md` (regras lidas sozinhas ao abrir) |
| `identidade.md.template` | `~/nexum/_nexum/identidade.md` (como pensar/responder) |
| `convencoes.md.template` | `~/nexum/_nexum/convencoes.md` (regras fixas + SEGURANÇA) |
| `roteamento.md.template` | `~/nexum/_nexum/roteamento.md` (onde vai cada assunto) |
| `estrutura-inicial.sh` | roda 1x — cria a árvore `~/nexum/` (pastas + INDEX + LEIA-MEs) |

## Slots usados nos templates

| Slot | O que é | De onde vem |
|---|---|---|
| `{NOME_ASSISTENTE}` | nome do assistente | entrevista (a pessoa BATIZA — ver abaixo) |
| `{NOME_DONO}` | primeiro nome do dono | entrevista |
| `{DESCRICAO_DONO}` | 1 frase sobre o dono e o que quer do assistente | entrevista |
| `{PERSONALIDADE_DONO}` | 3-6 linhas: tom, formalidade, emoji, onde lê | entrevista |
| `{AREAS_DO_DONO}` | áreas da vida do dono + 1 linha de tom cada | entrevista |
| `{LINHAS_DA_TABELA}` | linhas extras da tabela de roteamento (uma por área) | você escreve, a partir das áreas |
| `{REPO_GITHUB_BACKUP}` | repo privado de backup (ex.: `usuario/nexum-backup`) | módulo `base/backup/` (se ainda não souber, deixe escrito "(backup ainda não configurado)" e volte depois) |

## Passo a passo

### 1. Entrevista (conversa, nunca formulário seco)

Pergunte **um item por vez**, explicando o porquê. Tudo em PT-BR, linguagem de gente. Colha:

1. **Primeiro nome da pessoa** → `{NOME_DONO}`.
2. **O nome do assistente — deixe a PESSOA batizar.** Diga algo como: *"Esse assistente vai ser seu — ele merece um nome. Pode ser qualquer coisa: um nome de pessoa, uma palavra que você gosta... Como você quer chamar ele?"* Sugira 2-3 exemplos só se a pessoa travar. → `{NOME_ASSISTENTE}` (grave também em caixa do jeito que a pessoa escreveu).
3. **O que a pessoa faz e o que espera do assistente** (1-2 frases) → `{DESCRICAO_DONO}`.
4. **Jeito de conversar:** mais formal ou descontraído? gosta de emoji? quer que o assistente discorde quando achar errado? lê mais no celular ou PC? → redija `{PERSONALIDADE_DONO}` em prosa (3-6 linhas) e **leia de volta pra pessoa confirmar**.
5. **Áreas da vida** que ela quer organizar (família, trabalho, estudos, finanças, viagem...) → `{AREAS_DO_DONO}` e, no roteamento, `{LINHAS_DA_TABELA}` (uma linha por área no formato da tabela; área de **trabalho/negócio** ou **saúde** = 🔴 Em Espera, o resto 🟢).

### 2. Gravar a configuração central

Tudo que for valor reaproveitável vai pro **único** arquivo de config (outros módulos vão acrescentar variáveis nele):

```bash
mkdir -p ~/.config/semente
chmod 700 ~/.config/semente
cat >> ~/.config/semente/config.env <<EOF
NOME_ASSISTENTE="<nome batizado>"
NOME_DONO="<primeiro nome>"
EOF
chmod 600 ~/.config/semente/config.env
```

(Use `>>` se o arquivo já existir; confira antes com `grep NOME_ASSISTENTE ~/.config/semente/config.env` pra não duplicar.)

### 3. Criar a árvore

```bash
bash <pasta-do-repo-clonado>/base/cerebro/estrutura-inicial.sh
```

**Check:** `ls ~/nexum` deve mostrar `INDEX.md  PENDENCIAS.md  _entrada  _nexum  estudo  pessoal`.
**Se falhar:** o script avisa o motivo (quase sempre config.env faltando ou variável vazia). Conserte e rode de novo — ele é idempotente, nunca sobrescreve nada.

### 4. Preencher os templates

Para cada `.template` desta pasta:

1. Copie pro destino (tabela lá em cima).
2. Substitua **todos** os `{SLOTS}` pelos valores da entrevista.
3. **Apague o bloco de comentário `<!-- TEMPLATE ... -->`** do topo.
4. Confira que não sobrou slot: `grep -rn '{[A-Z_]*}' ~/nexum/CLAUDE.md ~/nexum/_nexum/` deve voltar **vazio** (exceto `{REPO_GITHUB_BACKUP}` se o backup ainda não foi configurado — anote pra voltar).

⚠️ **Regra inegociável:** a seção **"🔒 Segurança — o way of life"** de `convencoes.md` entra **inteira, sem cortar nem afrouxar** — mesmo que a pessoa diga que não precisa. Pode endurecer a pedido; afrouxar, nunca. As regras de segurança equivalentes no `CLAUDE.md` e no `roteamento.md` idem.

### 5. git init (versionamento local — o backup remoto é outro módulo)

```bash
cd ~/nexum
git init -b main
git config user.name "{NOME_ASSISTENTE} (VPS)"
git config user.email "assistente@vps.local"
printf '*.env\n*.token\n*secret*\n' > .gitignore
git add -A
git commit -m "Nascimento do {NOME_ASSISTENTE} — estrutura inicial"
```

**Check:** `git -C ~/nexum log --oneline` mostra 1 commit.
**Se falhar:** `git` não instalado → `sudo apt-get install -y git` e repita.

### 6. Teste final

Abra uma sessão nova do Claude Code em `~/nexum` e pergunte "quem é você?". A resposta deve vir **em PT-BR, curta, conclusão primeiro**, com o nome batizado. Se vier genérica ("sou o Claude..."), o `CLAUDE.md` não está em `~/nexum/` ou ficou com slot sem preencher — confira o passo 4.

## Depois daqui

Siga pro próximo módulo da base na ordem do `LEIA-ME.md` da raiz do repo (bot Telegram → lib → segurança → backup → monitor → módulos → fechamento). Ao terminar cada um, registre uma linha em `~/nexum/_nexum/ponto_atual.md`.
