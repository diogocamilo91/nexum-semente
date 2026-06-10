# base/lib/ — LEIA-ME (instruções pra VOCÊ, Claude instalador)

Biblioteca compartilhada dos robôs. Por enquanto, uma peça só: **`alerta.sh`**, o mensageiro único — todo robô do kit (backup, monitor da VPS, fechamento do dia, e módulos futuros) avisa o dono chamando ele. Nenhum robô fala com a API do Telegram por conta própria.

## Instalação

Instale **antes** de backup/monitor/fechamento (eles dependem dele). Pré-requisito: o módulo `base/bot-telegram/` já gravou `TELEGRAM_BOT_TOKEN` e `TELEGRAM_OWNER_ID` em `~/.config/semente/config.env`.

```bash
mkdir -p ~/semente-bin/log
cp <pasta-do-repo-clonado>/base/lib/alerta.sh ~/semente-bin/alerta.sh
chmod +x ~/semente-bin/alerta.sh
```

> `~/semente-bin/` é a casa de TODOS os scripts instalados do kit (fora do `~/nexum/`, de propósito: script não é conhecimento, e o log não deve entrar no backup). `~/semente-bin/log/` guarda os logs.

## Verificação (obrigatória)

```bash
~/semente-bin/alerta.sh --titulo "🌱 Semente" "Teste do mensageiro — se você leu isso no Telegram, está funcionando." && echo OK
```

Peça pra pessoa confirmar que a mensagem chegou no Telegram.

**Se falhar:**
- `config não existe` → o config.env ainda não foi criado (volte ao `base/cerebro/` e `base/bot-telegram/`).
- `TELEGRAM_BOT_TOKEN/TELEGRAM_OWNER_ID faltando` → grave as duas variáveis no config.env (vêm da instalação do bot).
- Sai sem erro mas nada chega → confira se a pessoa **já mandou /start pro bot** (o Telegram só deixa o bot falar com quem falou com ele primeiro) e se o `TELEGRAM_OWNER_ID` está certo.

## Contrato (pra quem escreve robô novo)

- Chamada: `~/semente-bin/alerta.sh [--titulo "emoji Nome"] "texto"` (ou texto via stdin com `-`).
- Mensagem longa é quebrada sozinha em partes de ~3900 chars.
- Código de saída: `0` entregou, `1` falhou — o robô que chama loga e segue (alerta nunca pode derrubar o robô).
- Slots envolvidos (definidos na instalação do bot): `{TELEGRAM_BOT_TOKEN}`, `{TELEGRAM_OWNER_ID}`.
