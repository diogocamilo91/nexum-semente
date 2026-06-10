# 🗞️ Módulo News — roteiro de instalação (PRO CLAUDE instalador)

Você vai instalar o radar de notícias: **painel sob demanda** (a pessoa fala "News",
você roda o coletor e devolve o resumo) + **alerta de notícia GIGANTE** (cron de 5 min
que cruza ~7 portais brasileiros e só avisa quando a mesma notícia converge forte em
vários ao mesmo tempo — e mesmo assim só depois de VOCÊ, via `claude -p` headless,
julgar que é gigante de verdade).

**Antes de instalar:** leia `ENTREVISTA.md` e faça a entrevista. Só siga se o dono disse SIM.

**Pré-requisitos:** `base/lib/alerta.sh` instalado (o alerta gigante avisa por ele).
O fechamento (`base/fechamento/`) é opcional, mas se estiver instalado a seção 🗞️ entra nele.

**Dependências:** nenhuma — `news.py` é Python puro (stdlib). Custo: zero (RSS público).

**Slots usados:** nenhum direto nos arquivos. As escolhas da entrevista viram chaves
no `~/.config/semente/config.env`:

```
NEWS_ATIVO=sim                 # ou nao
NEWS_TIME=                     # time de futebol do dono (vazio = sem prioridade)
NEWS_ALERTA_GIGANTE=sim        # ou nao (só painel)
#NEWS_MIN_PORTAIS=5            # em quantos portais a notícia precisa convergir
```

## O que tem aqui

| Arquivo | Vira o quê |
|---|---|
| `news.py` | `~/semente-bin/news.py` — coletor: painel (`--painel`), espiada (sem args) e detector (`--check`) |
| `monitor-news.sh` | `~/semente-bin/monitor-news.sh` — cron 5 min: detector + juiz LLM + alerta |
| `30-news.sh` | `~/.config/semente/fechamento.d/30-news.sh` — seção 🗞️ no fechamento da noite |

## Passo a passo

### 1. Instalar os arquivos

```bash
cp <pasta-do-repo-clonado>/modulos/news/news.py ~/semente-bin/news.py
cp <pasta-do-repo-clonado>/modulos/news/monitor-news.sh ~/semente-bin/monitor-news.sh
chmod +x ~/semente-bin/news.py ~/semente-bin/monitor-news.sh
```

### 2. Gravar as escolhas da entrevista no config

Acrescente ao `~/.config/semente/config.env` (NÃO sobrescreva o arquivo, acrescente):

```
NEWS_ATIVO=sim
NEWS_TIME=<time que a pessoa falou, ou deixe vazio>
NEWS_ALERTA_GIGANTE=<sim ou nao>
```

**Temas:** os padrão (brasil, mundo, futebol, tecnologia, economia) já vêm no `news.py`.
- A pessoa **tirou** um tema → não mexa no script; só não tem como tirar do painel sem
  editar a lista `TEMAS_PAINEL` no topo do `news.py` — pode editar a cópia instalada
  (`~/semente-bin/news.py`), removendo a linha do tema. É a única edição aceitável no script.
- A pessoa **pediu tema extra** → crie `~/.config/semente/news_fontes.json` com as fontes
  RSS do tema. Formato (lista de objetos):

```json
[
  {"id": "tecmundo", "nome": "TecMundo", "url": "https://rss.tecmundo.com.br/feed",
   "tema": "games", "convergencia": false}
]
```

  Como achar o RSS de um portal: tente `<site>/feed`, `<site>/rss` ou busque
  "RSS" no rodapé do site. **Teste a URL antes de gravar** (passo 3 mostra como).
  `convergencia` deixe `false` — só os portais gerais padrão votam no alerta gigante.

### 3. Testar o painel

```bash
python3 ~/semente-bin/news.py --painel
```

**Check:** sai o painel "🗞️ News — dd/mm hh:mm" com manchetes por tema. Se um tema
extra que você adicionou não aparecer, a URL do RSS está errada/fora do ar — teste com
`python3 -c "import urllib.request;print(urllib.request.urlopen('<URL>').read(300))"`.

**Se falhar tudo** (painel vazio): a VPS está sem saída pra internet ou os portais
bloquearam — rode `curl -sI https://g1.globo.com/rss/g1/ | head -1` pra diferenciar.

### 4. Testar o detector (sem mandar nada)

```bash
python3 ~/semente-bin/news.py
```

**Check:** ou "Nada convergindo forte..." (o normal) ou a lista do que converge agora.
Os dois são sucesso.

### 5. Ligar o alerta gigante (só se NEWS_ALERTA_GIGANTE=sim)

```bash
( crontab -l 2>/dev/null | grep -v semente-bin/monitor-news.sh ; echo '*/5 * * * * /usr/bin/bash $HOME/semente-bin/monitor-news.sh' ) | crontab -
crontab -l | grep monitor-news
```

Rode uma vez na mão pra validar o caminho inteiro (vai sair calado se não houver
candidato — é o esperado):

```bash
bash ~/semente-bin/monitor-news.sh ; tail -5 ~/semente-bin/log/monitor-news.log
```

**Check:** sem erro no log (log vazio também é ok — só loga quando há candidato).

> Como funciona por dentro: o `--check` só imprime algo quando a MESMA notícia aparece
> em ≥5 portais. Aí o shell chama `claude -p` com uma régua rígida (fato consumado,
> súbito, chocante — na dúvida é NÃO) e só com "SIM" dispara o `alerta.sh`. Dedup por
> evento/dia já embutido. O Claude headless usa a sessão já logada da VPS — sem chave extra.

### 6. Seção no fechamento (se o fechamento estiver instalado)

```bash
cp <pasta-do-repo-clonado>/modulos/news/30-news.sh ~/.config/semente/fechamento.d/30-news.sh
chmod +x ~/.config/semente/fechamento.d/30-news.sh
SEMENTE_DRYRUN=1 bash ~/semente-bin/fechamento-dia.sh
```

**Check:** o fechamento de teste agora mostra a seção 🗞️ News.

### 7. Ensinar o atalho ao dono (e a você mesmo)

Grave no conhecimento do assistente (ex.: no roteamento ou num `.md` de ferramentas)
que **quando o dono falar "News"**, você roda `python3 ~/semente-bin/news.py --painel`
e devolve a saída (pode lapidar o texto, mas sem inventar manchete).

## Operação

- Painel na mão: `python3 ~/semente-bin/news.py --painel`
- Pausar o alerta: `touch ~/monitor-news.PAUSED` · religar: `rm ~/monitor-news.PAUSED`
- Log: `~/semente-bin/log/monitor-news.log`
- Calibrar: se o dono reclamar de alerta fraco, suba `NEWS_MIN_PORTAIS` no config (ex.: 6)
  e/ou endureça a régua no prompt do `monitor-news.sh` com o caso concreto que ele reclamou.

## Se o dono disse NÃO

Grave `NEWS_ATIVO=nao` no config.env e siga. Nada é instalado.
