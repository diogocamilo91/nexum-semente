# CONTRATO DA CASCA — leia antes de escrever qualquer tela

> Este arquivo é a lei do app do kit. **Toda tela obedece a ele.** Se uma tela precisar
> de algo que não está aqui, ela está errada — ou o contrato precisa mudar primeiro.

## O desenho

```
servidor.py   → o motor: login, sessão, descoberta de telas, /saude
casca.py      → a casca: appbar (☰ · marca · ⚙️), gaveta lateral, tema, PWA
estatico/     → estilo.css (o sistema visual) + app.js (gaveta, tema, service worker)
nucleo/       → motores sem tela (o motor do chat mora aqui)
telas/*.py    → UMA tela por arquivo. É isto que você escreve.
```

**A gaveta é DADO, não código.** O servidor varre `telas/*.py`, importa cada uma e
pergunta se ela está disponível. Tela que existe e está disponível **aparece sozinha na
gaveta** — ninguém edita menu na mão. Módulo instalado depois entra do mesmo jeito: basta
o arquivo da tela existir.

## O que TODA tela expõe (obrigatório)

```python
CHAVE   = "emails"          # minúscula, sem espaço. Único no app.
TITULO  = "E-mails"         # o rótulo na gaveta (PT-BR)
ICONE   = "envelope"        # um nome da lista de ícones abaixo
GRUPO   = "principal"       # "principal" | "ferramentas" | "casa"
ORDEM   = 20                # menor primeiro, dentro do grupo

def disponivel(cfg: dict) -> bool:
    """True se esta tela faz sentido nesta instalação. `cfg` é o config.env lido.
    Ex.: a tela de e-mails só existe se o módulo do Gmail foi instalado.
    Tela que não está disponível NÃO aparece na gaveta e as rotas dela dão 404."""

def registra(app, casca, exige_login) -> None:
    """Registra as rotas Flask desta tela. Chamado uma vez, no boot."""
```

### O molde de uma tela

```python
import os
from flask import Response, request, jsonify

CHAVE, TITULO, ICONE, GRUPO, ORDEM = "exemplo", "Exemplo", "caixa", "ferramentas", 50

def disponivel(cfg):
    return True

def registra(app, casca, exige_login):
    @app.get("/exemplo")
    def tela_exemplo():
        exige_login()
        corpo = "<div class=cartao><h2>Oi</h2><p class=fraco>conteúdo</p></div>"
        return Response(casca.shell("Exemplo", corpo, "/exemplo"), mimetype="text/html")
```

- `casca.shell(titulo, corpo, ativo, css="", js="")` devolve a página inteira.
  `ativo` é o href da tela (pinta o item da gaveta).
- `exige_login()` derruba com 401 se não estiver logado. **Chame sempre, em toda rota**,
  inclusive nas de API.
- Rota de API da tela: prefixo `/api/<chave>/...` — nunca colidir com outra tela.

## Ícones disponíveis (nomes válidos em `ICONE`)

`conversa` · `envelope` · `calendario` · `pasta` · `jornal` · `microfone` · `livro`
`pulso` · `engrenagem` · `caixa` · `chave` · `nuvem` · `grafico` · `casa` · `busca`
`telefone` · `raio` · `escudo` · `controles`

Não invente nome — se faltar um, use `caixa`.

## O sistema visual (use SÓ estas classes)

**Nunca escreva cor no CSS da tela.** Use as fichas (variáveis CSS). O tema claro/escuro
troca sozinho, e cor chumbada quebra um dos dois.

| Ficha | Pra quê |
|---|---|
| `--fundo` | fundo da página |
| `--painel` | fundo de cartão/appbar/gaveta |
| `--linha` | bordas e divisórias |
| `--texto` | texto normal |
| `--fraco` | texto secundário |
| `--marca` | a cor de destaque (botão, item ativo) |
| `--ok` `--atencao` `--erro` | verde, âmbar, vermelho |

| Classe | O que é |
|---|---|
| `.cartao` | o bloco branco/escuro com borda e cantos — a caixa de tudo |
| `.kpis` + `.kpi` | linha de números grandes (`<div class=kpi><b>12</b><span>abertos</span></div>`) |
| `.tabela` | `<table class=tabela>` já vem estilizada, com rolagem no celular |
| `.btn` / `.btn.primario` / `.btn.perigo` | botões |
| `.campo` | `<input>`, `<textarea>`, `<select>` |
| `.chip` | etiqueta pequena (`.chip.ok`, `.chip.atencao`, `.chip.erro`) |
| `.fraco` | texto secundário |
| `.vazio` | o estado "não tem nada aqui" (sempre tenha um) |
| `.lista` + `.item` | lista de linhas clicáveis |
| `.aviso` (`.ok` `.atencao` `.erro`) | faixa de recado no topo do conteúdo |

**Grade:** o conteúdo já vem dentro de `<main class=area>` com largura máxima e respiro.
A tela só escreve o miolo.

## Regras que não se negociam

1. **PT-BR em tudo que a pessoa lê.** Data DD/MM/AAAA, hora 24h. Sem jargão: ela é leiga.
2. **Nada de dado nosso.** Nenhum IP, domínio, nome de pessoa, caminho de máquina real,
   token. Isto vai pro GitHub público de terceiros.
3. **Nada quebra a tela.** Toda leitura de arquivo/serviço vai em `try/except`; faltou o
   dado, a tela mostra `.vazio` com uma frase honesta — nunca traceback, nunca tela branca.
4. **Nada de segredo na tela.** Nunca imprima o conteúdo do `config.env`; mostre no
   máximo "configurado ✓" ou "faltando".
5. **Só leitura, salvo onde o contrato disser o contrário.** Tela não apaga arquivo.
   "Excluir" nesta casa é esconder (marcar), nunca deletar.
6. **JavaScript:** só o necessário, embutido via o argumento `js=` do `shell()`. Sem
   biblioteca externa, sem CDN (a VPS pode estar sem saída, e é mais rápido).
7. **Celular primeiro.** Tudo tem que caber em 390px de largura sem rolagem lateral.
8. **Config:** leia com `casca.config()` (devolve o dict do `~/.config/semente/config.env`).
   Caminhos úteis: `casca.dir_conhecimento()` (a pasta que a PESSOA escolheu — use a
   função, não chumbe `~/nexum`), `casca.DIR_BIN`, `casca.DIR_DADOS`.

## Como saber se um módulo está instalado

`disponivel(cfg)` recebe o config. As chaves que o kit grava:

| Módulo | Chave | Onde os dados dele ficam |
|---|---|---|
| Gmail | `GMAIL_ATIVO=sim` | script em `~/semente-bin/gmail.py` |
| Agenda | `AGENDA_ATIVO=sim` | script em `~/semente-bin/agenda.py` |
| Drive/Docs | `DRIVE_ATIVO=sim` | `~/semente-bin/drive.py` |
| Notícias | `NEWS_ATIVO=sim` | `~/semente-bin/news.py`, saída em `~/semente-bin/log/` |
| Aprendizado | `APRENDIZADO_ATIVO=sim` | `~/semente-bin/aprendizado.py` |
| Gravações | `GRAVACOES_ATIVO=sim` | transcrições em `~/semente-gravacoes/` |
| WhatsApp | `WHATSAPP_ATIVO=sim` | `~/semente-whatsapp/` |

Módulo ausente **não é erro**: `disponivel()` devolve False e pronto.
