# base/fechamento/ — LEIA-ME (instruções pra VOCÊ, Claude instalador)

Você vai instalar o **fechamento do dia**: toda noite às 21h, o dono recebe no Telegram UM resumo do dia dele — a saúde da VPS sempre, mais a seção de cada módulo que ele tiver ativado (agenda de amanhã, resumo de e-mails, etc.). É o "relatório de vida" do assistente: a pessoa sente o presente funcionando todo dia, mesmo sem pedir nada.

Pré-requisitos: `base/lib/alerta.sh` e `base/monitor-vps/` instalados. Os módulos opcionais NÃO são pré-requisito — o fechamento nasce só com a saúde da VPS e **cresce sozinho** conforme módulos forem instalados.

## Como cresce (arquitetura de plugins)

O `fechamento-dia.sh` não conhece módulo nenhum. Cada módulo instalado **dropa um snippet executável** em `~/.config/semente/fechamento.d/` e pronto: a seção passa a aparecer toda noite. Contrato do snippet (completo no topo do `fechamento-dia.sh`):

- arquivo `NN-nome.sh` com `+x` (NN dá a ordem: `10-agenda.sh`, `20-emails.sh`, `30-news.sh`...);
- imprime a seção pronta (1ª linha = título com emoji); **imprimir nada = seção omitida hoje** (não é erro);
- termina em <120s, não pede input, não manda mensagem (quem manda é o fechamento), sem efeito colateral.

Quando você instalar um módulo opcional (gmail, agenda...), o LEIA-ME dele manda criar o snippet. Use `exemplo-snippet.sh` como modelo.

## O que tem aqui

| Arquivo | Vira o quê |
|---|---|
| `fechamento-dia.sh` | `~/semente-bin/fechamento-dia.sh` — monta e manda o resumo das 21h |
| `exemplo-snippet.sh` | modelo de snippet (pra você e pros módulos futuros) |

Slots: nenhum — tudo vem do `config.env` em tempo de execução (via `alerta.sh`).

## Passo a passo

### 1. Instalar

```bash
cp <pasta-do-repo-clonado>/base/fechamento/fechamento-dia.sh ~/semente-bin/fechamento-dia.sh
chmod +x ~/semente-bin/fechamento-dia.sh
mkdir -p ~/.config/semente/fechamento.d
```

### 2. Testar a seco (não manda nada)

```bash
SEMENTE_DRYRUN=1 bash ~/semente-bin/fechamento-dia.sh
```

**Check:** imprime o fechamento com a data em português + o bloco "🖥️ VPS — ...". Sem módulo instalado é curto mesmo — está certo.

### 3. Testar de verdade (manda no Telegram)

```bash
bash ~/semente-bin/fechamento-dia.sh
```

Peça pra pessoa confirmar que chegou. Aproveite e explique: *"Toda noite às 21h você vai receber esse resumo. Hoje ele só fala da máquina; conforme formos ligando módulos (agenda, e-mails...), ele vai ganhando seções — sem você configurar nada."*

**Se falhar:** ver `~/semente-bin/log/fechamento.log`. Quase sempre é o `alerta.sh` (config.env) ou um snippet travado — o log diz qual seção falhou; o fechamento NUNCA morre por causa de um snippet (a seção vira "⚠️ falhou hoje" e o resto vai).

### 4. Cron das 21h

```bash
( crontab -l 2>/dev/null | grep -v semente-bin/fechamento-dia.sh ; echo '0 21 * * * /usr/bin/bash $HOME/semente-bin/fechamento-dia.sh' ) | crontab -
crontab -l | grep fechamento
```

Confirme com a pessoa se 21h é um bom horário (algumas preferem 20h ou 22h — é só mudar o `0 21` pra `0 20`/`0 22`).

## Operação

- Rodar agora: `bash ~/semente-bin/fechamento-dia.sh` · seco: `SEMENTE_DRYRUN=1 ...`
- Pausar: `touch ~/fechamento-dia.PAUSED` · religar: `rm ~/fechamento-dia.PAUSED`
- Ver/remover seções: `ls ~/.config/semente/fechamento.d/` (pra desativar uma seção sem desinstalar o módulo, tire o `+x` dela: `chmod -x NN-nome.sh`)

## Evolução natural (não faça agora)

Quando a pessoa quiser mais, este esqueleto aceita upgrades sem mudar a arquitetura: um snippet pode chamar `claude -p` pra redigir uma "leitura do dia", ou o fechamento pode virar página HTML com link — mas a versão mensagem-no-Telegram é a certa pra nascer: simples, leve e nunca fica muda.
