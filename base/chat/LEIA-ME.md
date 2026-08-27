# 💬 base/chat/ — o chat web (PRO CLAUDE instalador)

> **Este módulo NÃO se explica: se instala.** Diferente de tudo que você já leu por aqui,
> aqui você não constrói nada — o código está pronto, testado, e um script faz o serviço
> inteiro. Sua parte é rodar, conferir e apresentar à pessoa.

**O que a pessoa ganha:** um chat no navegador (celular + PC) que fala com você — a
resposta saindo ao vivo, cada conversa com memória própria, áudio, foto, print colado,
anexo, arquivar e excluir. É a segunda porta (a primeira é o Telegram) e é a que serve
pra trabalho longo: dá pra ler com calma, voltar, anexar arquivo.

## Antes de rodar

O módulo do **Telegram (etapa 3)** precisa estar instalado — a transcrição de áudio
reusa o Whisper de lá (o modelo tem ~460 MB; baixar duas vezes numa VPS de 2 GB seria
desperdício). E as portas 80/443 abertas — o `blindar.sh` da etapa 2 já abre.

## Instalação (é isto, e só isto)

```bash
bash <pasta-do-repo-clonado>/base/chat/instalar.sh
```

Ele faz sozinho, nesta ordem, e para no primeiro que falhar:

1. **confere a fundação** — o `claude` responde em `stream-json`? (se não, nada adianta);
2. copia pra `~/semente-chat/` e monta o ambiente do Python;
3. escreve a config (senha **gerada**, segredo, porta) em `~/.config/semente/config.env`;
4. instala o **Caddy** e põe o chat num endereço `https://chat.<IP>.sslip.io` — HTTPS de
   graça, sem precisar comprar domínio;
5. liga o serviço e instala o vigia (religa sozinho em até 2 min, e sobe no boot);
6. **prova pelo caminho por onde a pessoa entra**: `curl` no endereço https. Só carimba
   se voltar 200.

No fim ele imprime o endereço e a senha. **A senha aparece uma vez** — mande a pessoa
anotar (ela também fica no `config.env`, chave `CHAT_SENHA`).

## CHECK — não avance com isto falhando

```bash
bash ~/semente-chat/chatctl.sh status              # esperado: >> VIVO
curl -s -o /dev/null -w '%{http_code}\n' https://chat.<IP>.sslip.io/   # esperado: 200
bash ~/semente-chat/chatctl.sh log 20              # sem traceback
```

E o check que vale mais que os três: **peça pra pessoa abrir o endereço no celular,
entrar com a senha e te mandar um "oi".** Você responde. Só depois disso diga que está
no ar — HTTP 200 não prova tela.

| Problema | Causa provável | Conserto |
|---|---|---|
| o endereço não abre (000/timeout) | certificado ainda subindo (1ª vez leva ~1 min) | espere e repita o curl |
| abre mas dá 502 | o serviço caiu | `chatctl.sh log 40` e `chatctl.sh start` |
| a resposta chega toda de uma vez no fim | o bloco do Caddy perdeu o `flush_interval -1` | confira `/etc/caddy/Caddyfile` |
| áudio vira mensagem vazia | o Whisper do módulo do Telegram não está lá | instale a etapa 3 antes |
| "senha errada" com a senha certa | espaço/aspas na chave `CHAT_SENHA` | `grep CHAT_SENHA ~/.config/semente/config.env` |

## O que dizer à pessoa quando terminar

- "Abra `https://chat.<IP>.sslip.io` no celular e use **Adicionar à tela de início** —
  vira um app."
- "Cada conversa é um assunto, e cada uma lembra da sua própria história."
- "Dá pra **gravar áudio** (o microfone), **colar um print** (Ctrl+V), **anexar arquivo**
  (o clipe) e mandar foto."
- "Se eu estiver demorando, aparece o que estou fazendo e há quanto tempo — e tem um
  botão **parar**."
- "**Excluir aqui é esconder**: a conversa sai da lista e continua guardada. Nada some
  de verdade nesta casa."

## Como isto funciona por dentro (só se precisar mexer)

O desenho inteiro obedece a uma regra: **todo estado do turno sobrevive a (1) a pessoa
fechar a tela e (2) o serviço reiniciar.** Por isso a "fase" e o texto parcial moram no
servidor (não no navegador), o cronômetro é ancorado na hora da mensagem **gravada no
banco**, e existe um reconciliador de órfãos no boot — **com freio** (2 tentativas, 30
min de idade máxima, e um bilhete quando desiste; sem o freio isso vira bomba de tokens).

- `chat.py` — servidor (Flask + SQLite/WAL). Turno, SSE, anexos, login.
- `tela.html` — a tela. **Mexeu no JavaScript? rode `node --check` antes de subir** —
  nada checa isso sozinho e o sintoma é tela em branco com deploy verde.
- `chatctl.sh` — start/stop/status/log. O `restart` **espera a linha ficar livre** (não
  reinicia em cima de um turno que está respondendo).
- Config: `CHAT_PORTA`, `CHAT_SENHA`, `CHAT_MAX_TURNOS` (2 numa VPS de 2 GB).

Foi testado ponta a ponta nos 6 cenários que quebram chat caseiro: sair-e-voltar no meio
do turno, duas mensagens coladas virando uma resposta, o serviço morrer com turno em voo,
morrer três vezes seguidas (o freio), parar no meio da escrita, e cinco conversas ao
mesmo tempo.
