# 📱 base/app/ — o app pessoal (PRO CLAUDE instalador)

> **Este módulo NÃO se explica: se instala.** O código está pronto e testado. Sua parte é
> rodar um comando, conferir e apresentar à pessoa.

**O que a pessoa ganha:** um aplicativo só dela, no celular e no computador, com **gaveta
lateral** (☰) e as telas do assistente dentro. Nasce com quatro telas e **ganha telas
sozinho** conforme os módulos vão sendo instalados:

| Tela | O que é | Quando aparece |
|---|---|---|
| 💬 **Conversa** | o chat com você: resposta ao vivo, áudio, foto, print colado, anexo, arquivar | sempre |
| 📚 **Conhecimento** | navegar e buscar dentro da pasta de conhecimento (os `.md` que você escreve) | sempre |
| 🩺 **A casa** | disco, memória, o que está de pé, o backup, o que roda sozinho, os últimos erros | sempre |
| ⚙️ **Ajustes** e ❓ **Como usar** | tema, letra, trocar senha, e o manual em linguagem de gente | sempre |
| 📧 E-mails · 📅 Agenda · ☁️ Arquivos | as telas dos módulos do Google | quando o módulo entra |
| 🗞️ Notícias · 🎙️ Gravações · 🔑 Aprendizado · 📱 WhatsApp | as telas dos outros módulos | quando o módulo entra |

**Como a tela entra sozinha:** o servidor varre `telas/*.py`, importa cada uma e pergunta
`disponivel(cfg)`. Tela cujo módulo não está instalado simplesmente não aparece. Instalou o
Gmail depois? Rode o instalador de novo e a tela de e-mails está lá. **Ninguém edita menu.**

## Antes de rodar

O módulo do **Telegram (etapa 3)** precisa estar instalado — a transcrição de áudio reusa o
Whisper de lá (o modelo tem ~460 MB; baixar duas vezes numa VPS de 2 GB seria desperdício).
E as portas 80/443 abertas — o `blindar.sh` da etapa 2 já abre.

## Instalação (é isto, e só isto)

```bash
bash <pasta-do-repo-clonado>/base/app/instalar.sh
```

Ele faz sozinho, e para no primeiro passo que falhar:

1. **confere a fundação** — o `claude` responde em `stream-json`? (se não, nada adianta);
2. copia pra `~/semente-app/` **preservando as conversas** de uma instalação anterior;
3. monta o ambiente do Python;
4. escreve a config (senha **gerada**, segredo, porta) em `~/.config/semente/config.env`;
5. instala o **Caddy** e põe o app em `https://app.<IP>.sslip.io` — HTTPS de graça, sem
   precisar comprar domínio;
6. liga e instala o vigia (religa sozinho em até 2 min; sobe no boot);
7. **prova pelo caminho por onde a pessoa entra** (curl no endereço https) e lista as telas
   que subiram.

No fim imprime o endereço e a senha. **A senha aparece uma vez** — mande a pessoa anotar
(ela também fica no `config.env`, chave `CHAT_SENHA`).

Opções que quase ninguém precisa: `--sem-endereco` (não mexe no Caddy, pra quem já tem
servidor web) · `--sem-vigia` (não instala o despertador) · `APP_DIR=...` (instalar noutra pasta).

## CHECK — não avance com isto falhando

```bash
bash ~/semente-app/appctl.sh status     # >> VIVO  e o pulso com o nº de telas
bash ~/semente-app/appctl.sh telas      # a lista do que entrou e do que ficou de fora
curl -s -o /dev/null -w '%{http_code}\n' https://app.<IP>.sslip.io/   # 200
```

E o check que vale mais que os três: **peça pra pessoa abrir no celular, entrar com a senha,
tocar no ☰ pra ver a gaveta e te mandar um "oi".** Você responde. Só depois disso diga que
está no ar — HTTP 200 não prova tela.

| Problema | Causa provável | Conserto |
|---|---|---|
| o endereço não abre (000/timeout) | certificado subindo (1ª vez leva ~1 min) | espere e repita |
| abre mas dá 502 | o serviço caiu | `appctl.sh log 40` e `appctl.sh start` |
| a resposta chega toda de uma vez no fim | o bloco do Caddy perdeu o `flush_interval -1` | confira `/etc/caddy/Caddyfile` |
| falta uma tela na gaveta | o módulo dela não está instalado (é o esperado) | `appctl.sh telas` diz o motivo |
| áudio vira mensagem vazia | o Whisper do módulo do Telegram não está lá | instale a etapa 3 antes |

## Se você for MEXER no app (leia antes)

- **`CONTRATO.md` é a lei.** Toda tela obedece: `CHAVE/TITULO/ICONE/GRUPO/ORDEM`,
  `disponivel(cfg)`, `registra(app, casca, exige_login)`, e só as classes CSS de lá.
- **Tela nova = um arquivo em `telas/`.** Não existe menu pra editar.
- **Nunca escreva cor.** Use as fichas (`--fundo`, `--painel`, `--marca`...) ou você quebra
  o tema claro ou o escuro.
- **Mexeu no JavaScript? rode `node --check` antes de subir** — nada checa isso sozinho e o
  sintoma é tela em branco com deploy verde.
- **`appctl.sh restart` espera a linha ficar livre** (não reinicia em cima de uma resposta
  que está saindo). A contagem vem de uma placa que o próprio app publica em `/saude` —
  contar processo com `ps` dá zero fixo e o restart cai bem em cima do turno.

## O que dizer à pessoa quando terminar

- "Abra o endereço no celular e use **Adicionar à tela de início** — vira um app."
- "O **☰** no canto abre a gaveta: é por ali que você anda entre as telas."
- "Na **Conversa** dá pra gravar áudio, colar print (Ctrl+V), anexar arquivo e mandar foto."
- "Em **Conhecimento** você vê tudo que eu sei sobre você — e pode buscar."
- "Em **A casa** você olha se está tudo bem na máquina, sem precisar entender nada."
- "**Excluir aqui é esconder**: nada some de verdade nesta casa."
