# 📱 WhatsApp — o DESENHO (planta técnica pro Claude instalador construir)

> Você vai escrever o código na hora, com a Baileys ATUAL (`npm info baileys version`
> antes de começar). Esta planta diz o que cada peça faz, as travas que não podem
> faltar e os esqueletos. Foi extraída de uma instalação real que roda estável.

## Estrutura (tudo FORA de `~/nexum/` — não vai pro backup)

```
~/semente-whatsapp/
├── package.json          # deps: baileys, pino, qrcode
├── index.js              # o coletor (só-leitura)
├── run.sh                # supervisor: roda o index.js e religa se cair
├── wactl.sh              # painel: start/stop/restart/status/log
├── auth/                 # credencial da sessão pareada (chmod 700, NUNCA sair da VPS)
├── dados/
│   ├── mensagens.jsonl   # 1 mensagem por linha (append-only)
│   ├── chats.json        # id do chat -> nome do grupo/conversa
│   └── contatos.json     # id -> nome da pessoa
├── logs/
└── qr.png                # o QR de pareamento (apagar depois de parear)
```

## index.js — o coletor (as decisões que importam)

Esqueleto do comportamento (a API exata confira na doc da versão instalada):

```js
const { default: makeWASocket, useMultiFileAuthState,
        fetchLatestBaileysVersion } = require('baileys');
const pino = require('pino');

async function main() {
  const { state, saveCreds } = await useMultiFileAuthState('./auth');
  const { version } = await fetchLatestBaileysVersion();
  const sock = makeWASocket({
    version, auth: state,
    printQRInTerminal: false,          // nós geramos o qr.png nós mesmos
    markOnlineOnConnect: false,        // TRAVA: não aparece online, não rouba notificação
    syncFullHistory: false,
    logger: pino({ level: 'warn' }),
  });
  sock.ev.on('creds.update', saveCreds);

  // QR: no evento connection.update, se vier "qr", gravar como PNG:
  //   require('qrcode').toFile('./qr.png', qr, { scale: 8 })
  // Reconectar quando connection === 'close' (a menos que loggedOut).

  // A COLETA: só estes dois eventos, e NADA de chamada de escrita.
  sock.ev.on('messages.upsert', ({ messages }) => gravar(messages));
  sock.ev.on('messaging-history.set', ({ messages }) => gravar(messages));
}
```

`gravar(msgs)`: pra cada mensagem, append em `dados/mensagens.jsonl` de um objeto
`{ts, chat, chatNome, de, deNome, texto, tipo}` — extrair o texto de
`message.conversation || message.extendedTextMessage?.text || ...`; mídia grava só o
tipo (`"[imagem]"`, `"[áudio]"`), **não baixa o arquivo** (disco e privacidade).
Atualizar `chats.json`/`contatos.json` quando vierem eventos de metadados
(`chats.upsert`, `contacts.upsert`).

**TRAVA DE REVISÃO (faça sempre):** depois de escrever o index.js, rode
`grep -nE 'sendMessage|readMessages|sendPresence|chatModify' index.js` — tem que
voltar VAZIO. É o teste objetivo de "só-leitura".

## run.sh e wactl.sh

Mesmo padrão dos outros serviços do kit:
- `run.sh`: loop `while true; do node index.js >> logs/saida.log 2>&1; sleep 5; done`,
  com PID em `run.pid`.
- `wactl.sh start|stop|restart|status|log [n]`: start é idempotente (se o PID vive,
  não faz nada — é o que o cron chama a cada 2 min).

Cron:
```
@reboot bash $HOME/semente-whatsapp/wactl.sh start
*/2 * * * * bash $HOME/semente-whatsapp/wactl.sh start >/dev/null 2>&1
```

## Pareamento (QR, sempre)

1. `wactl.sh start` → em ~10s aparece `qr.png` (se renova a cada ~20s; reabrir se expirar).
2. Dono abre o `qr.png` (VS Code Remote-SSH ou SFTP) e escaneia:
   WhatsApp → Aparelhos conectados → Conectar um aparelho.
3. Conectou: `messages.upsert` começa a pingar no jsonl. Apagar o `qr.png`.
4. Re-parear no futuro: parar, `rm -rf auth/*`, repetir. (O WhatsApp reenvia o
   histórico recente ao vincular.)

⚠️ NÃO use o pareamento por código (`requestPairingCode`): falha em contas antigas
sem o nono dígito e não tem vantagem sobre o QR aqui.

## O resumo diário (snippet do fechamento)

`~/.config/semente/fechamento.d/50-whatsapp.sh` (+x), no contrato padrão dos snippets:

1. Filtra `dados/mensagens.jsonl` pelas últimas 24h (python/jq), agrupa por chat,
   troca ids por nomes, e LIMITA o material (ex.: últimos ~300 itens) pra caber no prompt.
2. Chama `claude -p` (headless, `--mcp-config ~/.config/semente/empty-mcp.json
   --strict-mcp-config`) com a instrução: *"resuma POR CONVERSA o que importa
   (combinados, avisos, pendências, datas), até 2 linhas por conversa, ignore
   figurinha/bom-dia; 1ª linha exatamente '📱 WhatsApp hoje'"*.
3. Valida que a resposta começa com `📱 WhatsApp hoje`; senão, **imprime nada**
   (seção omitida — nunca despejar mensagem crua no fechamento).
4. Timeout total <120s (contrato do fechamento).

## Aceitação (checklist final)

- [ ] mensagem de teste aparece no `mensagens.jsonl` em segundos
- [ ] o destinatário NÃO viu "visto"/online por causa da VPS
- [ ] `grep` de escrita no index.js voltou vazio
- [ ] derrubar o processo (`kill`) → cron religa em ≤2 min
- [ ] reboot da VPS → volta sozinho
- [ ] snippet do fechamento sai com resumo decente (ou omite quando não há nada)
- [ ] dono sabe desconectar pelo celular (ensine na prática, mostrando a tela)
