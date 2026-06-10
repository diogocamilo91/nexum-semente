# 🎓 Módulo Aprendizado — roteiro de instalação (PRO CLAUDE instalador)

Você vai instalar a curadoria de canais de YouTube do dono: um coletor RSS
(`aprendizado.py`, sem chave, sem custo) + uma seção 🎓 no fechamento da noite,
redigida por você mesmo (claude headless) com fallback pra lista simples.

**Antes de instalar:** leia `ENTREVISTA.md` e faça a entrevista — inclusive a coleta
interativa dos canais (o `--achar` resolve @handle/URL em channel_id). Só siga se o
dono disse SIM e te deu pelo menos 1 canal.

**Pré-requisitos:** `base/fechamento/` instalado (a entrega diária É a seção do
fechamento). Sem o fechamento, o módulo só funciona sob demanda.

**Dependências:** nenhuma — Python puro (stdlib). Custo: zero.

**Slots usados:** nenhum direto. Chaves que este módulo grava no
`~/.config/semente/config.env`:

```
APRENDIZADO_ATIVO=sim          # ou nao
```

(Os canais NÃO vão no config.env — vão no JSON próprio, abaixo.)

## O que tem aqui

| Arquivo | Vira o quê |
|---|---|
| `aprendizado.py` | `~/semente-bin/aprendizado.py` — coletor RSS + `--achar` (descobre channel_id) |
| `40-aprendizado.sh` | `~/.config/semente/fechamento.d/40-aprendizado.sh` — seção 🎓 da noite |

## Passo a passo

### 1. Instalar o coletor

```bash
cp <pasta-do-repo-clonado>/modulos/aprendizado/aprendizado.py ~/semente-bin/aprendizado.py
chmod +x ~/semente-bin/aprendizado.py
```

### 2. Montar a config dos canais (com o material da entrevista)

Pra cada canal que a pessoa deu, descubra o id:

```bash
python3 ~/semente-bin/aprendizado.py --achar '@nomedocanal'
# sai: {"nome": "Nome do Canal", "id": "UCxxxxxxxxxxxxxxxxxxxxxx"}
```

**Se falhar** ("não achei o channelId"): peça o link de um VÍDEO do canal e rode o
`--achar` com ele — a página do vídeo sempre tem o id.

Grave `~/.config/semente/aprendizado_canais.json` (temas = como a pessoa agrupou;
um grupo só também vale):

```json
{
  "temas": {
    "meus canais": [
      {"nome": "Canal A", "id": "UCxxxxxxxxxxxxxxxxxxxxxx"},
      {"nome": "Canal B", "id": "UCyyyyyyyyyyyyyyyyyyyyyy"}
    ]
  }
}
```

### 3. Testar a coleta

```bash
python3 ~/semente-bin/aprendizado.py --horas 72
```

**Check:** sai "=== YOUTUBE — N vídeo(s) novo(s)..." com itens (72h quase sempre pega
algo; se sair 0 com vários canais, confira os ids). Canal com "(falhou ler: ...)" =
id errado — refaça o `--achar` daquele canal.

### 4. Ligar a seção no fechamento

```bash
cp <pasta-do-repo-clonado>/modulos/aprendizado/40-aprendizado.sh ~/.config/semente/fechamento.d/40-aprendizado.sh
chmod +x ~/.config/semente/fechamento.d/40-aprendizado.sh
```

Se a pessoa quis INCLUIR shorts: edite a cópia instalada e tire o `--sem-shorts` da
linha do `MATERIAL=`.

Teste:

```bash
bash ~/.config/semente/fechamento.d/40-aprendizado.sh
```

**Check:** ou a seção "🎓 Aprendizado" redigida, ou NADA (= nenhum lançamento nas
últimas 30h — normal; force com `--horas 200` na cópia só pra ver, e desfaça).
Se sair a lista crua (plano B), o `claude -p` falhou — confira `CLAUDE_BIN` no config
e se a sessão do Claude está logada; o plano B funcionando já é aceitável.

### 5. Gravar no config e ensinar o atalho

```bash
# acrescentar ao ~/.config/semente/config.env:
APRENDIZADO_ATIVO=sim
```

Grave no conhecimento do assistente: quando o dono mandar **"o que saiu nos meus
canais?"**, rodar `python3 ~/semente-bin/aprendizado.py` e responder em cima disso.
Quando ele mandar **um canal novo**, rodar o `--achar` e acrescentar ao JSON — sem
perguntar formato, só confirmar o nome do canal.

## Operação

- Coleta na mão: `python3 ~/semente-bin/aprendizado.py [--horas N]`
- Adicionar/remover canal: editar `~/.config/semente/aprendizado_canais.json`
- Desligar só a seção da noite: `chmod -x ~/.config/semente/fechamento.d/40-aprendizado.sh`

## Evolução natural (não faça agora)

Quando a pessoa pedir "me resume esse vídeo": a transcrição pública do YouTube costuma
ser bloqueada pra IPs de datacenter — pode precisar de proxy. Trate como melhoria
futura, caso a caso; não prometa na entrevista.

## Se o dono disse NÃO

Grave `APRENDIZADO_ATIVO=nao` no config.env e siga. Nada é instalado.
