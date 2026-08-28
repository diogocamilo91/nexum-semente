# 📱 Módulo WhatsApp — roteiro (PRO CLAUDE instalador) — ⚠️ EXPERIMENTAL

Este módulo põe a VPS como mais um **aparelho conectado** do WhatsApp do dono (igual ao
WhatsApp Web) e guarda uma cópia **só-leitura** das conversas, que vira a tela 📱 WhatsApp
do app e a seção do resumo da noite.

**Ele tem instalador**, e o instalador **não congela a biblioteca**: a Baileys muda todo mês
acompanhando o próprio WhatsApp, então o `instalar.sh` baixa a versão **do dia**, confere se
as peças que o coletor usa continuam existindo nela, prova o que o coletor grava — e só
então liga. Se a biblioteca tiver mudado de forma, ele **para e te manda pro `desenho.md`**,
que é a planta completa pra você construir na mão. Esse é o desenho: tenta o caminho pronto,
e o caminho manual continua ali como rede.

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


## A instalação

```bash
bash <pasta-do-repo-clonado>/modulos/whatsapp/instalar.sh
```

Sete passos, e ele para no primeiro que falhar:

1. **Node** — instala o 20 se não houver (a biblioteca precisa da 20 ou maior);
2. copia pra `~/semente-whatsapp/` (fora da pasta de conhecimento = fora do backup);
3. **confere a trava de só-leitura** no coletor — procura qualquer chamada de envio, de
   marcar-como-lido, de presença ou de alteração. Achou uma? **não instala**;
4. baixa a biblioteca **na versão de hoje** e confere que as peças que o coletor usa
   continuam existindo nela;
5. **prova o que o coletor grava sem precisar do celular** (`coletor.js --autoteste`):
   escreve duas mensagens inventadas pelo mesmo caminho de gravação e confere que saíram no
   formato que a tela do app lê — e que mídia entrou **só como marca**, sem vazar o arquivo;
6. liga, grava `WHATSAPP_ATIVO=sim` na config e **deixa o `qr.png` pronto**;
7. encaixa a seção do WhatsApp no resumo das 21h.

**O pareamento é do DONO** — o instalador não pareia nada, e você também não. Ele para no
QR e te dá o texto pra conduzir a pessoa: abrir o `qr.png`, e no celular
*WhatsApp → Aparelhos conectados → Conectar um aparelho*. O QR vence em ~20s e se renova
sozinho. Confirmou? `wactl.sh status` mostra o número de mensagens subindo.

**Depois de parear, rode de novo `bash base/app/instalar.sh`** — é o que faz a tela 📱
WhatsApp aparecer na gaveta do app. Mostre a tela nova pra pessoa.

### CHECK — não avance com isto falhando

```bash
bash ~/semente-whatsapp/wactl.sh status     # >> VIVO, e o nº de mensagens
bash ~/semente-whatsapp/wactl.sh log 30     # sem erro repetindo
```

| Problema | O que é | Conserto |
|---|---|---|
| o QR não aparece em 60s | a biblioteca mudou, ou sem saída pra internet | `wactl.sh log 40`; se for a biblioteca, vá pro `desenho.md` |
| "DESLOGADO" no log | o aparelho foi removido no celular | `wactl.sh parear` (a credencial velha é **movida**, não apagada) |
| a ligação cai e volta sempre | pode ser recusa do WhatsApp | **não mexa no tempo de espera**: ele cresce de propósito. Martelar é o que arrisca o número |
| a tela do app não mostra nada | o app não foi reinstalado depois | rode `base/app/instalar.sh` de novo |


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
