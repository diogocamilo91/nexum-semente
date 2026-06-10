# 📱 Módulo WhatsApp — roteiro (PRO CLAUDE instalador) — ⚠️ EXPERIMENTAL

Este módulo NÃO vem com scripts prontos pra copiar, de propósito. Ele é um **espelho
só-leitura do WhatsApp do dono** feito com a biblioteca **Baileys** (Node.js, mesmo
protocolo do WhatsApp Web) — e a Baileys muda com frequência, acompanhando as mudanças
do próprio WhatsApp. Um `index.js` congelado no repo estaria quebrado em meses.
Então aqui o caminho é outro: **você CONSTRÓI o coletor na hora**, seguindo o
`desenho.md` (a planta completa, com o esqueleto do código e as travas inegociáveis),
usando a versão atual da Baileys.

## Antes de tudo: a avaliação com a pessoa

1. Leia `ENTREVISTA.md` e faça a conversa honesta inteira (risco de bloqueio do número,
   caráter experimental, privacidade). **Não instale se a pessoa hesitou.**
2. Avalie VOCÊ também, e diga o que concluiu:
   - A pessoa usa o WhatsApp pra trabalho/clientes? → recomende NÃO ativar.
   - A VPS tem menos de 2 GB de RAM livre? (`free -h`) → o Node + Baileys roda, mas
     aperta; pondere se o ganho compensa.
   - O ganho real é volume de grupo. Pouca mensagem por dia = módulo não se paga.
3. Registre a decisão no `~/.config/semente/config.env`:

```
WHATSAPP_ATIVO=sim    # ou nao
```

## Se for instalar: o contrato inegociável (way of life)

Estas regras vão no código E no conhecimento do assistente — sem exceção:

- **SÓ LEITURA, blindado no código**: nenhuma chamada de envio (`sendMessage`),
  de leitura (`readMessages`) ou de presença. `markOnlineOnConnect: false`
  (não rouba notificação do celular, não aparece online).
- **Dados FORA do backup**: tudo em `~/semente-whatsapp/` (fora de `~/nexum/`).
  As conversas de terceiros nunca sobem pro GitHub nem saem da VPS.
- **Só o destilado entra no acervo**: resumo que você escrever pode virar `.md` em
  `~/nexum/`, com OK do dono — mensagem crua, nunca.
- **Nunca apagar**: o histórico espelhado só cresce (se um dia pesar, mover/compactar,
  não deletar).
- **O dono manda no plugue**: ensine a ele que o desligamento de emergência é no
  CELULAR (Aparelhos conectados → desconectar) — funciona mesmo com a VPS fora do ar.

## O caminho da instalação (resumo; o passo a passo técnico está no desenho.md)

1. **Node.js 20+** na VPS (`node -v`; se faltar, instale pelo NodeSource ou nvm).
2. Montar `~/semente-whatsapp/` conforme o `desenho.md`: `index.js` (coletor),
   `run.sh` (supervisor que religa), `wactl.sh` (start/stop/status/log),
   `npm install baileys pino qrcode`.
3. **Parear por QR**: o coletor gera `qr.png`; o dono abre o arquivo (SFTP/VS Code)
   e escaneia em WhatsApp → Aparelhos conectados → Conectar um aparelho.
   *Gotcha aprendido na prática: o pareamento por CÓDIGO falha em certas contas
   (números antigos sem o nono dígito) — use QR sempre, que não depende do número.*
4. Cron de resiliência (`@reboot` + a cada 2 min chama o `start`, que não faz nada
   se já estiver rodando).
5. Resumo diário: snippet `50-whatsapp.sh` em `~/.config/semente/fechamento.d/`
   (modelo no `desenho.md`) — prepara as mensagens das últimas 24h e pede a você
   (claude headless) o resumo por grupo/conversa. SÓ o resumo sai no fechamento.
6. Teste de aceitação: dono manda uma mensagem de teste pra alguém; ela aparece no
   `dados/mensagens.jsonl` em segundos; o "visto" NÃO aparece pro outro lado.

## Operação e manutenção (gravar no conhecimento do assistente)

- Status: `bash ~/semente-whatsapp/wactl.sh status` · log: `... log 40`
- Caiu a sessão (acontece): gerar QR de novo e o dono re-parear — o WhatsApp reenvia
  o histórico recente sozinho.
- Baileys quebrou após update do WhatsApp: `npm update baileys` e reler o changelog;
  é a manutenção típica deste módulo.
- Se o dono relatar QUALQUER aviso do WhatsApp sobre o aparelho conectado: desligar
  na hora, contar pro dono e reavaliar juntos.

## Se o dono disse NÃO

`WHATSAPP_ATIVO=nao` no config.env e nada é instalado. Deixe registrado no
conhecimento que o módulo existe e ficou de fora por decisão dele.
