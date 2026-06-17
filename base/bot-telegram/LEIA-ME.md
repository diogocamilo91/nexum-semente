# base/bot-telegram — instruções de instalação (PRO CLAUDE instalador)

> **Você (Claude) é o instalador.** Este módulo é a peça mais importante do kit:
> o bot do Telegram que vira a porta do assistente no celular do dono.
> Siga os passos NA ORDEM. Cada passo tem um CHECK — não avance sem ele passar.

## O que este módulo entrega

- Um grupo no Telegram (só o dono + o bot) com **Tópicos** ligados.
- **Cada tópico = uma conversa separada do Claude Code** (sessão própria, com `--resume`).
- O dono manda **texto, foto (até álbuns) e áudio** (transcrito por Whisper local, de graça).
- O assistente responde com texto formatado e, quando pedido (ou quando a mensagem
  veio em áudio), também em **voz** (Edge-TTS, de graça; marca `[VOZ]` na resposta).
- **Auto-título**: na 1ª mensagem de um tópico, o bot renomeia o tópico com o assunto.
- **Watchdog**: se o bot cair, religa sozinho em até 2 min; sobe junto com a VPS.
- Tópico com **⚡ no nome** = "chat livre" (perguntas aleatórias, sem assumir trabalho).

## Segurança (explicar pro dono na entrevista, antes de instalar)

- O bot **só responde ao ID do dono** e **só dentro do grupo dele**. Qualquer outra
  pessoa é ignorada em silêncio.
- O Claude roda em `--permission-mode bypassPermissions` (age na VPS sem confirmar
  cada passo). Isso é seguro PORQUE só o dono fala com ele — diga isso explicitamente.
- O **way of life** vale aqui também: o assistente nunca apaga nada (move, não
  deleta) e ação externa (e-mail, mensagem pra terceiros, agenda) só com OK do dono.
- Segredos ficam em `~/.config/semente/config.env` (`chmod 600`), **fora** da pasta
  de conhecimento — não vão pro backup do GitHub.

## Slots que você vai preencher (vêm da entrevista)

| Slot | O que é | De onde vem |
|---|---|---|
| `{TELEGRAM_BOT_TOKEN}` | token do bot | dono cria no **@BotFather** (`/newbot`) |
| `{TELEGRAM_OWNER_ID}` | ID numérico do dono | dono manda `/start` pro **@userinfobot** |
| `{TELEGRAM_GROUP_ID}` | ID do grupo (começa com `-100`) | passo 5 abaixo |
| `{NOME_ASSISTENTE}` | nome do assistente | escolha do dono na entrevista |
| `{NOME_DONO}` | como o assistente chama o dono | escolha do dono |

---

## Passo 0 — pré-checagens

```bash
claude --version            # Claude Code instalado e logado?
python3 --version           # precisa >= 3.10
free -h && df -h /          # RAM e disco (Whisper "small" usa ~700 MB de RAM no pico)
```

**CHECK:** os 3 comandos respondem. Se `python3` < 3.10, instale
(`sudo apt install -y python3 python3-venv`). Se não houver `python3-venv`:
`sudo apt install -y python3-venv`.

> Não precisa de ffmpeg do sistema: o PyAV (instalado junto com o faster-whisper)
> já traz os codecs. Se `pip install` de alguma roda falhar pedindo compilador,
> rode `sudo apt install -y build-essential` e tente de novo.

## Passo 1 — copiar os arquivos e criar o venv

```bash
mkdir -p ~/semente-bot
cp -r <pasta-do-repo-clonado>/base/bot-telegram/* <pasta-do-repo-clonado>/base/bot-telegram/.gitignore ~/semente-bot/
cd ~/semente-bot
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
chmod +x run.sh nexumctl.sh
```

**CHECK:**
```bash
~/semente-bot/venv/bin/python -c "import telegram, faster_whisper, edge_tts, av; print('deps OK')"
```

Se falhar por pouca RAM durante o install (VPS de 2 GB pode matar o pip), crie um
swap temporário: `sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile` — e repita o install.

## Passo 2 — entrevista: criar o bot no BotFather (o DONO faz, você guia)

Peça ao dono, no app do Telegram:
1. Falar com **@BotFather** → `/newbot` → dar um nome (ex.: o `{NOME_ASSISTENTE}`)
   e um username terminando em `bot`.
2. Copiar o **token** que o BotFather devolve e te mandar.
3. Ainda no BotFather: `/setprivacy` → escolher o bot → **Disable**
   (sem isso o bot não enxerga as mensagens do grupo).
4. Falar com **@userinfobot** → `/start` → te mandar o número do campo **Id**
   (esse é o `{TELEGRAM_OWNER_ID}`).

**CHECK:** você tem token (formato `numeros:letras`) e um ID numérico do dono.

## Passo 3 — criar a config única

```bash
mkdir -p ~/.config/semente
# NÃO sobrescrever se já existe (o base/cerebro/ cria esse arquivo antes):
[ -f ~/.config/semente/config.env ] || cp ~/semente-bot/config.env.example ~/.config/semente/config.env
chmod 600 ~/.config/semente/config.env
```

Edite `~/.config/semente/config.env` preenchendo:
- `TELEGRAM_BOT_TOKEN=` (passo 2)
- `TELEGRAM_OWNER_ID=` (passo 2)
- `TELEGRAM_GROUP_ID=` — **deixe vazio por enquanto** (descobre no passo 5)
- `NOME_ASSISTENTE=` e `NOME_DONO=` (entrevista)
- `DIR_CONHECIMENTO=` — a pasta de conhecimento já criada pela base (padrão `~/nexum`)

> Se este arquivo já existir (outro módulo do kit criou), só ACRESCENTE as chaves
> que faltam — nunca sobrescreva o arquivo.

**CHECK:** `grep -c '=' ~/.config/semente/config.env` ≥ 5 e `ls -l` mostra `-rw-------`.

## Passo 4 — entrevista: criar o grupo com Tópicos (o DONO faz, você guia)

Peça ao dono:
1. Criar um **grupo novo** no Telegram (ex.: nome = `{NOME_ASSISTENTE}`), só com ele.
2. Adicionar o bot ao grupo.
3. Configurações do grupo → ativar **Tópicos** (Topics).
4. Promover o bot a **administrador** com a permissão **"Gerenciar tópicos"**
   (Manage Topics) — sem isso o auto-título falha em silêncio.

**CHECK:** dono confirma que o grupo existe, com tópicos, e o bot é admin.

## Passo 5 — descobrir o ID do grupo

Peça ao dono pra mandar qualquer mensagem **no grupo**. Depois:

```bash
source <(grep TELEGRAM_BOT_TOKEN ~/.config/semente/config.env)
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates" | grep -o '"chat":{"id":-100[0-9]*' | head -1
```

O número que começa com `-100` é o `{TELEGRAM_GROUP_ID}`. Grave em
`~/.config/semente/config.env` na chave `TELEGRAM_GROUP_ID=`.

> Se vier vazio: o privacy mode ainda está ligado (refaça `/setprivacy` → Disable
> e REMOVA e RE-ADICIONE o bot ao grupo), ou o bot já está rodando e "comeu" os
> updates (pare com `bash ~/semente-bot/nexumctl.sh stop` e tente de novo).

**CHECK:** `TELEGRAM_GROUP_ID` preenchido com um número `-100…`.

## Passo 6 — ligar + instalar o vigia

```bash
bash ~/semente-bot/nexumctl.sh start
sleep 5
bash ~/semente-bot/nexumctl.sh status      # esperado: >> VIVO
bash ~/semente-bot/nexumctl.sh log 20      # esperado: "... bot iniciando (owner=... group=...)"
bash ~/semente-bot/nexumctl.sh install-watchdog   # @reboot + vigia a cada 2 min
crontab -l | grep nexumctl               # esperado: 2 linhas
```

**CHECK:** status `>> VIVO`, log sem traceback, 2 linhas no crontab.

## Passo 7 — teste de ponta a ponta (com o dono)

1. **Texto:** dono cria um tópico e manda "oi". Esperado: "digitando…", resposta
   do assistente e o **tópico renomeado** com o assunto.
2. **Áudio:** dono manda um recado de voz curto. Esperado: resposta começa com
   "🎧 você disse: …" e vem **também em áudio**. (A 1ª vez demora mais: o modelo
   Whisper ~460 MB baixa sozinho — avise o dono.)
3. **Foto:** dono manda uma foto com uma pergunta na legenda. Esperado: resposta
   considerando a imagem.
4. **/new** no tópico: "Conversa zerada".

**CHECK:** os 4 testes passam. Só então marque o módulo como concluído.

---

## Problemas comuns (e o que fazer)

| Sintoma | Causa provável | Conserto |
|---|---|---|
| Bot não responde nada | token errado, ou `OWNER_ID`/`GROUP_ID` não batem | `nexumctl.sh log 40` — linhas `IGNORADO user=... chat=...` mostram os IDs REAIS que chegaram; corrija a config e `restart` |
| `Conflict: terminated by other getUpdates` no log | duas instâncias do bot | `nexumctl.sh stop`, confira `pgrep -af bot.py`, depois `start` |
| Auto-título não acontece | bot sem permissão "Gerenciar tópicos" | promover o bot a admin com Manage Topics |
| Bot não vê mensagens do grupo | privacy mode ligado | @BotFather `/setprivacy` → Disable; remover e re-adicionar o bot ao grupo |
| Transcrição muito lenta / mata a VPS | modelo grande demais pra RAM | `WHISPER_MODELO=base` na config (não precisa reiniciar o bot) |
| Resposta em voz não chega | sem internet pro Edge-TTS e Piper não instalado | normal: o texto sempre chega; voz é melhor-esforço. Pra reserva offline, instalar `piper-tts` + baixar a voz (ver `config.env.example`) |
| `TELEGRAM_BOT_TOKEN nao encontrado` ao iniciar | config não existe / sem a chave | refazer o passo 3 |
| Bot morre logo após `start` | erro de import/config | `nexumctl.sh log 40` mostra o traceback; o supervisor reinicia a cada 3 s — corrija a causa antes |

## Mapa dos arquivos (depois de instalado, em `~/semente-bot/`)

| Arquivo | O que é |
|---|---|
| `bot.py` | o programa do bot (núcleo: sessões por tópico, streaming, batch, voz) |
| `transcribe.py` | áudio → texto (faster-whisper, CPU) — subprocesso |
| `falar.py` | texto → voz (Edge-TTS; Piper reserva opcional) — subprocesso |
| `run.sh` | supervisor (reinicia o bot se cair) |
| `nexumctl.sh` | painel: start/stop/restart/pause/resume/status/log/install-* |
| `config.env.example` | modelo da config única (`~/.config/semente/config.env`) |
| `sessions.json` etc. | estado criado sozinho (sessões, nomes de tópicos…) |
| `incoming/` | fotos e áudios baixados do Telegram |
| `whisper-models/` | modelo Whisper baixado na 1ª transcrição |

## O que dizer pro dono no fim (resumo de uso)

- "Cada **tópico** é uma conversa separada. Assunto novo = tópico novo."
- "**/new** zera a conversa do tópico atual."
- "Pode mandar **texto, foto e áudio**; pra ouvir a resposta, é só pedir ('me responde em áudio')."
- "Tópico com **⚡** no nome = papo livre / perguntas aleatórias."
- "Pra ligar/desligar na mão (via SSH): `bash ~/semente-bot/nexumctl.sh start|stop|status`."
