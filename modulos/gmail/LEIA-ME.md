# 📧 Módulo Gmail — roteiro de instalação (PRO CLAUDE instalador)

Você vai dar ao assistente acesso de **leitura + organização + envio** ao Gmail do dono,
via um app OAuth que o PRÓPRIO DONO cria no Google Cloud (de graça, conta normal do Google).
Sem servidor extra, sem dependência: a ferramenta é `gmail.py` (Python, biblioteca padrão).

**Antes de instalar:** leia `ENTREVISTA.md` e faça a entrevista. Só siga se o dono disse SIM.

**Slots usados neste módulo** (pergunte na entrevista se ainda não tiver):
- `{EMAIL_DONO}` — o Gmail da pessoa (ex.: fulano@gmail.com)
- `{NOME_ASSISTENTE}` — nome do assistente (já está no config.env)

**Chaves que este módulo grava em `~/.config/semente/config.env`:**
```
EMAIL_DONO={EMAIL_DONO}
GMAIL_ATIVO=sim
GMAIL_LIMPA_PROPAGANDA=sim        # ou nao, conforme a entrevista
#GOOGLE_OAUTH_CLIENT=~/.config/semente/google/oauth_client.json   # só se mudar o padrão
```

---

## Visão do caminho (5 partes, ~15 min com o dono junto)

1. Dono cria um projeto no Google Cloud + credencial OAuth (você dita passo a passo).
2. Dono manda o arquivo JSON da credencial pra VPS.
3. Autorização: você gera um link, o dono aprova no navegador, cola a resposta de volta.
4. Você testa (ler + rascunho). 5. (Opcional) liga o robô limpa-propaganda no cron.

> ♻️ **Credencial compartilhada:** o arquivo `~/.config/semente/google/oauth_client.json`
> serve TAMBÉM pros módulos Agenda e Drive/Docs. Crie uma vez aqui; nos outros módulos
> só se ativa a API e se autoriza de novo (cada módulo tem seu próprio token, com o
> escopo mínimo dele).

---

## PARTE 1 — o dono cria a credencial no Google (você dita, ele clica)

Peça pro dono abrir **https://console.cloud.google.com/** no PC ou celular, **logado em
`{EMAIL_DONO}`**. Dite um passo de cada vez e espere o "feito" antes do próximo:

1. **Criar o projeto:** no topo da página tem um seletor de projeto → clicar →
   **"Novo projeto"** → nome: `{NOME_ASSISTENTE}` → **Criar**. Esperar uns segundos e
   **selecionar** o projeto recém-criado no mesmo seletor.
2. **Ativar a API do Gmail:** menu ☰ → **APIs e serviços → Biblioteca** → buscar
   **"Gmail API"** → clicar nela → **Ativar**.
3. **Tela de permissão OAuth:** menu ☰ → **APIs e serviços → Tela de permissão OAuth**
   (em consoles novos: "Branding"/"Público"):
   - Tipo de usuário: **Externo** → Criar.
   - Nome do app: `{NOME_ASSISTENTE}` · E-mail de suporte: `{EMAIL_DONO}` ·
     E-mail de contato do desenvolvedor (no fim): `{EMAIL_DONO}` → **Salvar e continuar**.
   - Tela de "Escopos": **pular** (Salvar e continuar).
   - **Usuários de teste:** Adicionar → `{EMAIL_DONO}` → Salvar e continuar.
4. **⚠️ Publicar o app (importante!):** ainda na Tela de permissão OAuth (ou em "Público"),
   clicar **"Publicar app"** → confirmar (status sai de "Em teste" pra "Em produção").
   *Por quê:* em modo "Em teste" o Google **mata a autorização a cada 7 dias** e o
   assistente para de funcionar "do nada". Publicado, a autorização é permanente.
   O aviso de "app não verificado" na hora de autorizar é normal pra uso pessoal.
5. **Criar a credencial:** menu ☰ → **APIs e serviços → Credenciais →
   Criar credenciais → ID do cliente OAuth**:
   - Tipo de aplicativo: **App para computador (Desktop app)** · Nome: `{NOME_ASSISTENTE}`
     → **Criar**.
   - Na janela que aparece: **Fazer o download do JSON**. Guardar o arquivo.

**Check:** o dono tem um arquivo `client_secret_....json` baixado. Se travou em algum
passo, peça um print da tela e oriente pelo que aparece — os nomes de menu variam um
pouco entre versões do console, mas a ordem (projeto → API → consentimento → credencial)
é sempre essa.

## PARTE 2 — subir o JSON pra VPS

```
[DENTRO DA VPS]
mkdir -p ~/.config/semente/google
```

O dono manda o arquivo pra VPS do jeito que ele já acessa os arquivos (SFTP/Termius no
celular, VS Code Remote-SSH no PC — o mesmo caminho que ele usou na instalação base).
Se nada disso estiver à mão, alternativa que sempre funciona: peça pra ele **abrir o
JSON, copiar o conteúdo inteiro e colar no chat**; aí você mesmo grava com um `cat >`.

Destino final (nome exato):
```
~/.config/semente/google/oauth_client.json
```
```
[DENTRO DA VPS]
chmod 600 ~/.config/semente/google/oauth_client.json
python3 -c "import json;d=json.load(open('$HOME/.config/semente/google/oauth_client.json'));print('OK -', (d.get('installed') or d.get('web'))['client_id'][:20]+'...')"
```
**Check:** imprime `OK - ...`. Se der erro de JSON, o arquivo veio cortado — repetir o envio.

## PARTE 3 — instalar a ferramenta e autorizar

```
[DENTRO DA VPS]
mkdir -p ~/semente-bin/log
cp <pasta-do-repo-clonado>/modulos/gmail/gmail.py ~/semente-bin/gmail.py
cp <pasta-do-repo-clonado>/modulos/gmail/limpa-propaganda.sh ~/semente-bin/limpa-propaganda.sh
chmod +x ~/semente-bin/gmail.py ~/semente-bin/limpa-propaganda.sh
```

Autorizar (uma vez):
```
[DENTRO DA VPS]
~/semente-bin/gmail.py auth-url
```
Mande o link impresso pro dono e explique ANTES o que ele vai ver:
1. Abrir o link no navegador, logado em `{EMAIL_DONO}`.
2. Vai aparecer **"O Google não verificou este app"** → clicar **Avançado →
   Acessar {NOME_ASSISTENTE} (não seguro)**. (É o app DELE mesmo; o aviso é padrão.)
3. **Permitir** os acessos pedidos.
4. No fim o navegador tenta abrir `localhost:8765` e dá **"não foi possível conectar" —
   isso é o esperado e significa que deu certo.** Pedir pra ele copiar a **URL INTEIRA**
   da barra de endereço e colar no chat.
   ⚠️ O código dentro da URL **expira em poucos minutos** — concluir logo:
```
[DENTRO DA VPS]
~/semente-bin/gmail.py auth-finish "<URL colada>"
```
**Check:** imprime `OK - autorizado.` Se reclamar de `invalid_grant`, o código expirou ou
veio cortado → gerar `auth-url` de novo e repetir.

## PARTE 4 — testar

```
[DENTRO DA VPS]
~/semente-bin/gmail.py nao-lidos 5          # lista os 5 não-lidos mais recentes
~/semente-bin/gmail.py rascunho --para {EMAIL_DONO} --assunto "Teste do {NOME_ASSISTENTE}" --corpo "Se este rascunho apareceu no seu Gmail, o módulo está no ar. Pode apagar o rascunho."
```
**Check:** a lista sai sem erro E o dono confirma que viu o rascunho na pasta Rascunhos.
(Teste com RASCUNHO de propósito — envio de verdade só com ok dele, desde o dia 1.)

Grave no config:
```
[DENTRO DA VPS]
printf '\nEMAIL_DONO={EMAIL_DONO}\nGMAIL_ATIVO=sim\n' >> ~/.config/semente/config.env
```

## PARTE 5 (opcional) — robô limpa-propaganda

Só se o dono topou na entrevista. O robô marca como **lida** a aba Promoções
(`category:promotions is:unread`). **Não apaga, não arquiva, não mexe em mais nada.**

Teste manual primeiro:
```
[DENTRO DA VPS]
~/semente-bin/gmail.py limpa-propaganda --max 50
```
**Check:** imprime quantas marcou (pode ser 0 se a aba está limpa). Depois o cron, de hora
em hora:
```
[DENTRO DA VPS]
( crontab -l 2>/dev/null | grep -v semente-bin/limpa-propaganda.sh ; echo '17 * * * * $HOME/semente-bin/limpa-propaganda.sh' ) | crontab -
printf 'GMAIL_LIMPA_PROPAGANDA=sim\n' >> ~/.config/semente/config.env
```
Log em `~/semente-bin/log/limpa-propaganda.log`. Se o dono recusou:
`printf 'GMAIL_LIMPA_PROPAGANDA=nao\n' >> ~/.config/semente/config.env`.

---

## A ferramenta `gmail.py` (referência rápida pro dia a dia)

```
gmail.py nao-lidos [n]                      # não-lidos da caixa de entrada
gmail.py buscar "<busca do gmail>" [n]      # ex.: "from:banco is:unread", "boleto newer_than:7d"
gmail.py ler <id>                           # cabeçalhos + corpo em texto
gmail.py rascunho --para X --assunto Y --corpo "..."     # cria rascunho (sem ok não vira envio)
gmail.py enviar   --para X --assunto Y --corpo "..." [--anexo arq]   # ⚠️ SÓ com ok explícito do dono
gmail.py responder <id> --corpo "..."       # responde na mesma conversa  ⚠️ SÓ com ok do dono
gmail.py arquivar <id>                      # tira da caixa de entrada (continua na conta)
gmail.py marcar-lido <id>
gmail.py rotular <id> "Nome do rótulo"      # cria o rótulo se não existir
gmail.py limpa-propaganda [--max N]         # marca Promoções como lidas
```
Corpo também entra por stdin: `echo "texto" | gmail.py enviar --para X --assunto Y --corpo -`

**Não existe comando de apagar.** É de propósito (way of life: nunca apagar). Se um dia o
dono pedir exclusão, explique a regra e ofereça arquivar/rotular.

## Escopos, arquivos e privacidade

- Escopo OAuth: `gmail.modify` (ler/enviar/organizar; **não** inclui exclusão permanente).
- Credencial: `~/.config/semente/google/oauth_client.json` (600).
- Token: `~/.config/semente/google/token_gmail.json` (600, criado pelo `auth-finish`).
- **Nada disso entra no backup do GitHub** (estão fora de `~/nexum/`). Confirme que o
  `.gitignore`/backup da base não cobre `~/.config` — não cobre, por desenho.
- Revogar: myaccount.google.com → Segurança → Conexões de terceiros → remover o app.

## Se falhar (mapa rápido)

| Sintoma | Causa provável | Conserto |
|---|---|---|
| `auth-finish` → `invalid_grant` | código expirou/veio cortado | gerar `auth-url` de novo, concluir em minutos |
| `403 access_denied` na autorização | dono não está como usuário de teste E app não publicado | Parte 1, passos 3-4 |
| Funcionou e parou ~7 dias depois | app ficou "Em teste" | publicar "Em produção" (Parte 1 passo 4) e refazer auth |
| `403 accessNotConfigured` | Gmail API não ativada no projeto | Parte 1, passo 2 |
| `ERRO OAuth 400 invalid_client` | JSON errado/cortado | reenviar o arquivo da credencial |

## PARTE 6 — seção 📧 no fechamento do dia

O fechamento (`base/fechamento/`) funciona por snippets em `~/.config/semente/fechamento.d/`.
Crie o de e-mails (vale criar mesmo antes do fechamento ser instalado — ele é o último da base):

```
[DENTRO DA VPS]
mkdir -p ~/.config/semente/fechamento.d
cat > ~/.config/semente/fechamento.d/20-emails.sh <<'EOF'
#!/usr/bin/env bash
# Seção 📧 do fechamento — não-lidos da caixa de entrada (silêncio se em dia).
set -u
SAIDA="$("$HOME/semente-bin/gmail.py" nao-lidos 8 2>/dev/null)"
case "$SAIDA" in ""|"(nenhum"*) exit 0 ;; esac
echo "📧 E-mails não lidos"
echo "$SAIDA"
EOF
chmod +x ~/.config/semente/fechamento.d/20-emails.sh
bash ~/.config/semente/fechamento.d/20-emails.sh   # teste: lista os não-lidos (ou nada, se a caixa está em dia)
```

Depois de instalado: registre o módulo no `INDEX.md` e no roteamento do assistente
(assunto "e-mail" → este módulo).
