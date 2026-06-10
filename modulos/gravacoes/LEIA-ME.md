# 🎙️ Módulo Gravações — roteiro de instalação (PRO CLAUDE instalador)

Você vai instalar a esteira mínima de gravações: **pasta vigiada → transcrição via
Gemini (com separação de locutores) → ficha (resumo/decisões/pendências) escrita por
você (claude headless) → documento .md no acervo do dono + aviso no Telegram**.

É a versão 1 de propósito: SEM app web, SEM player, SEM reavaliação interativa
(isso é evolução futura). O que ela entrega já resolve o caso real: "gravei, quero
o texto e o resumo, e quero poder perguntar depois".

**Antes de instalar:** leia `ENTREVISTA.md` e faça a entrevista — inclusive a criação
da chave do Gemini guiada e o aviso de custo/privacidade. Só siga se o dono disse SIM
e te deu a chave.

**Pré-requisitos:** `base/lib/alerta.sh` instalado. Internet de saída liberada
(o upload vai pro Google).

**Dependências de sistema:** `ffmpeg` (converte/fatia o áudio). VPS de 2 GB aguenta
tranquilo — o trabalho pesado (transcrever) roda no Gemini, fora da máquina.

**Slots usados:**
- `{GEMINI_API_KEY}` — chave que o dono criou em aistudio.google.com/apikey (começa com `AIza`)

**Chaves que este módulo grava em `~/.config/semente/config.env`:**

```
GRAVACOES_ATIVO=sim            # ou nao
GEMINI_API_KEY={GEMINI_API_KEY}
#GEMINI_MODELO=gemini-2.5-flash   # só se um dia precisar trocar o modelo
```

> ⚠️ A chave é SEGREDO: só no config.env (`chmod 600`), nunca em arquivo dentro de
> `~/nexum/` (iria pro backup do GitHub), nunca em log, nunca repetida em chat.

## O que tem aqui

| Arquivo | Vira o quê |
|---|---|
| `gravacao_processar.py` | `~/semente-bin/gravacao_processar.py` — transcreve 1 áudio + ficha + grava o .md |
| `gravacoes-vigia.sh` | `~/semente-bin/gravacoes-vigia.sh` — cron 5 min: pega o que cair em `~/gravacoes/entrada/` |

Pastas que o vigia cria sozinho: `~/gravacoes/entrada/` (o dono solta o áudio aqui),
`~/gravacoes/processadas/` (originais já feitos — NUNCA apagar), `~/gravacoes/com-problema/`
(falhou — original preservado). O .md final vai pra `~/nexum/pessoal/gravacoes/`.

## Passo a passo

### 1. Dependência de sistema

```bash
sudo apt install -y ffmpeg
ffmpeg -version | head -1
```

**Check:** imprime a versão. Sem sudo? Rode com o usuário que instalou a base.

### 2. Instalar os scripts

```bash
cp <pasta-do-repo-clonado>/modulos/gravacoes/gravacao_processar.py ~/semente-bin/gravacao_processar.py
cp <pasta-do-repo-clonado>/modulos/gravacoes/gravacoes-vigia.sh ~/semente-bin/gravacoes-vigia.sh
chmod +x ~/semente-bin/gravacao_processar.py ~/semente-bin/gravacoes-vigia.sh
mkdir -p ~/gravacoes/entrada ~/nexum/pessoal/gravacoes
```

### 3. Gravar a chave no config

Acrescente ao `~/.config/semente/config.env` (confira que o arquivo está `chmod 600`):

```
GRAVACOES_ATIVO=sim
GEMINI_API_KEY=<a chave AIza... que o dono te mandou>
```

Teste a chave (barato, 1 chamada de texto mínima):

```bash
curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=$(grep ^GEMINI_API_KEY ~/.config/semente/config.env | cut -d= -f2)" \
  -H 'Content-Type: application/json' \
  -d '{"contents":[{"parts":[{"text":"responda só: ok"}]}]}' | grep -o '"text"[^,]*'
```

**Check:** sai algo com "ok". `API_KEY_INVALID` → chave colada errada (espaço, corte).
`429` → cota grátis do dia esgotada (a chave é válida; siga).
**Se o modelo `gemini-2.5-flash` der 404** (modelo aposentado): liste os atuais com
`curl -s ".../v1beta/models?key=..."`, escolha o flash mais novo e grave
`GEMINI_MODELO=<nome>` no config.env.

### 4. Teste de ponta a ponta (com um áudio de verdade)

Peça ao dono um áudio curto (1-2 min, qualquer formato: m4a, mp3, ogg, opus) ou gere
um de teste. Rode na mão:

```bash
python3 ~/semente-bin/gravacao_processar.py ~/gravacoes/entrada/<arquivo> --titulo "teste"
```

**Check:** imprime o caminho de um `.md` em `~/nexum/pessoal/gravacoes/`. Abra e
confira: ficha (tipo/resumo/destaques) + transcrição com `[mm:ss] Locutor N:`.
- Falha no upload/transcrição → mensagem de erro diz o ponto; cheque chave e internet.
- Ficha veio com aviso de "avaliação automática falhou" → o `claude -p` headless não
  rodou; confira `CLAUDE_BIN`/login do Claude. A transcrição em si não depende disso.

Depois mova o teste pra `processadas/` (`mv`, nunca `rm`).

### 5. Ligar o vigia no cron

```bash
( crontab -l 2>/dev/null | grep -v semente-bin/gravacoes-vigia.sh ; echo '*/5 * * * * /usr/bin/bash $HOME/semente-bin/gravacoes-vigia.sh' ) | crontab -
crontab -l | grep gravacoes
```

Teste o fluxo real: o DONO manda um áudio pra `~/gravacoes/entrada/` pelo caminho que
ele escolheu na entrevista (SFTP/Termius no celular, VS Code no PC). Espere o ciclo.

**Check:** chega no Telegram "🎙️ Gravação pronta" e o .md existe. O áudio original
foi pra `~/gravacoes/processadas/`.

### 6. Ensinar o uso ao dono (e gravar no conhecimento)

Grave no conhecimento do assistente:
- áudios novos chegam em `~/gravacoes/entrada/`; o vigia processa sozinho;
- quando o dono perguntar sobre uma gravação ("o que ficou decidido na reunião X?"),
  ler o .md em `~/nexum/pessoal/gravacoes/` e responder citando os tempos;
- conteúdo de gravação é SENSÍVEL: nunca citar em link público, nunca resumir pra
  terceiros sem OK do dono.

E avise o dono: "pra transcrever, é só soltar o áudio na pasta `gravacoes/entrada` —
o resto é comigo."

## Operação

- Processar um arquivo na mão: `python3 ~/semente-bin/gravacao_processar.py <audio> [--titulo "..."]`
- Pausar o vigia: `touch ~/gravacoes-vigia.PAUSED` · religar: `rm ~/gravacoes-vigia.PAUSED`
- Log: `~/semente-bin/log/gravacoes.log`
- Áudio longo: >30 min é fatiado em blocos de 25 min automaticamente (qualquer duração).
- Falhou? O original está intacto em `~/gravacoes/com-problema/` — investigue o log e
  reprocesse na mão. **Nunca apague um áudio**, nem o com-problema.

## Custo (pra você calibrar a conversa)

Gemini Flash cobra o áudio por tempo (~32 tokens/segundo de áudio). Na prática:
**hora de áudio ≈ R$ 0,50–1,00** (estimativa 06/2026; confira o preço vigente se o dono
perguntar). Uso leve costuma caber na cota gratuita diária. Se o dono quiser, anote os
processamentos num CSV pra prestação de contas — evolução simples, não obrigatória.

## Se o dono disse NÃO

Grave `GRAVACOES_ATIVO=nao` no config.env e siga. Nada é instalado e nenhuma chave é criada.
