#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Semente — News: painel de notícias + detector de notícia GIGANTE (cross-portal).

A ideia (provada no NEXUM original): notícia GRANDE de verdade sai em VÁRIOS
portais ao mesmo tempo, não em um só. Então este script cruza muitos portais
brasileiros e só considera "candidato a gigante" o que converge em todos.

Duas funções:
  1) PAINEL (sob demanda + no fechamento da noite): puxa VÁRIOS portais, por tema,
     e devolve um resumo pronto pra ler. Sempre fresco — busca na hora.
  2) ALERTA GIGANTE: a cada X min cruza os portais gerais; quando a MESMA notícia
     aparece forte em VÁRIOS ao mesmo tempo, vira "candidato". Aí o monitor-news.sh
     chama o Claude pra dar o veredito final e só então avisa no Telegram.
     Sinal barato (convergência) + juiz inteligente (LLM) = quase zero alarme falso.

Modos:
  (sem args)     espiada manual: o que está convergindo nos portais AGORA.
  --painel       resumo por tema, pronto pro Telegram/fechamento (busca na hora).
  --check        para o cron: se há candidato a gigante novo, imprime o bloco
                 CANDIDATO_GIGANTE (pro shell julgar). Senão, nada. Dedup por dia.

Sem dependência externa: só stdlib (urllib, re, concurrent.futures).

Configuração (nada fixo no código):
  ~/.config/semente/config.env       NEWS_TIME (time de futebol do dono, opcional),
                                     NEWS_MIN_PORTAIS (padrão 5)
  ~/.config/semente/news_fontes.json (opcional) fontes EXTRAS além das padrão:
                                     [{"id","nome","url","tema","convergencia"}]
Estado: ~/.config/semente/news/alertados-AAAA-MM-DD.txt (eventos já emitidos hoje)
"""
import sys, os, re, html, json, datetime, unicodedata, urllib.request
from concurrent.futures import ThreadPoolExecutor

CONFIG_ENV = os.path.expanduser(
    os.environ.get("SEMENTE_CONFIG", "~/.config/semente/config.env"))
FONTES_JSON = os.path.expanduser("~/.config/semente/news_fontes.json")
DIR = os.path.expanduser("~/.config/semente/news")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def ler_config():
    """Lê ~/.config/semente/config.env (CHAVE=valor, # comenta)."""
    cfg = {}
    try:
        with open(CONFIG_ENV, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                k, v = linha.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return cfg


CFG = ler_config()

# ---- Fontes padrão (RSS públicos, testados; valem pra qualquer pessoa) -------
# convergencia=True => entram na DETECÇÃO de notícia gigante (mesma língua).
# tema="" => fica FORA do painel (só conta na convergência) — feeds "mangueira"
# de notas regionais são péssimos pro painel mas ótimos como +1 portal no cruzamento.
FONTES = [
    # id,          nome,            url,                                                          tema,         convergencia
    ("g1",        "G1",            "https://g1.globo.com/rss/g1/",                                "",           True),
    ("cnn",       "CNN Brasil",    "https://www.cnnbrasil.com.br/feed/",                          "brasil",     True),
    ("folha",     "Folha",         "https://feeds.folha.uol.com.br/emcimadahora/rss091.xml",      "brasil",     True),
    ("uol",       "UOL",           "https://rss.uol.com.br/feed/noticias.xml",                    "",           True),
    ("poder360",  "Poder360",      "https://www.poder360.com.br/feed/",                           "brasil",     True),
    ("jovempan",  "Jovem Pan",     "https://jovempan.com.br/feed/",                               "brasil",     True),
    ("bbcbr",     "BBC Brasil",    "https://feeds.bbci.co.uk/portuguese/rss.xml",                 "mundo",      True),
    # internacional (inglês) — só painel
    ("bbcworld",  "BBC",           "https://feeds.bbci.co.uk/news/world/rss.xml",                 "mundo",      False),
    ("nyt",       "New York Times","https://rss.nytimes.com/services/xml/rss/nyt/World.xml",      "mundo",      False),
    ("guardian",  "The Guardian",  "https://www.theguardian.com/world/rss",                       "mundo",      False),
    # temas
    ("ge",        "ge",            "https://ge.globo.com/rss/ge/",                                "futebol",    False),
    ("g1tec",     "G1 Tecnologia", "https://g1.globo.com/rss/g1/tecnologia/",                     "tecnologia", False),
    ("g1eco",     "G1 Economia",   "https://g1.globo.com/rss/g1/economia/",                       "economia",   False),
]

# fontes extras da pessoa (a entrevista pode adicionar portal/tema que ela segue)
try:
    with open(FONTES_JSON, encoding="utf-8") as _f:
        for _x in json.load(_f):
            FONTES.append((_x["id"], _x["nome"], _x["url"],
                           _x.get("tema", ""), bool(_x.get("convergencia", False))))
except (OSError, ValueError, KeyError):
    pass

TOP_CONVERG = 12     # janela p/ detectar convergência (feeds vêm do mais novo pro mais velho)
MIN_PORTAIS = int(CFG.get("NEWS_MIN_PORTAIS", "5") or 5)
TIME_DONO = CFG.get("NEWS_TIME", "")   # time de futebol do dono (prioriza no painel)

TEMAS_PAINEL = [
    ("brasil",     "🇧🇷 Brasil",      6),
    ("mundo",      "🌍 Mundo",        5),
    ("futebol",    "⚽ Futebol",      4),
    ("tecnologia", "💻 Tecnologia",   4),
    ("economia",   "💰 Economia",     4),
]
# temas extras vindos do news_fontes.json ganham seção própria, no fim
for (_fid, _nome, _url, _tema, _conv) in FONTES:
    if _tema and _tema not in [t for t, _, _ in TEMAS_PAINEL]:
        TEMAS_PAINEL.append((_tema, "📌 " + _tema.capitalize(), 4))

# Palavras que aparecem em manchete mas NÃO são entidade de evento
# (chamadas, verbos, lugares/órgãos genéricos, meses). Sem acento e minúsculo.
STOP = set("""
veja saiba como apos entenda confira assista leia ouca olha veja onde quando quem
porque por que para com sem mais menos sobre entre apos durante contra ate desde
o a os as um uma uns umas de do da dos das no na nos nas em ao aos pelo pela
isso isto esse essa este esta aquele aquela ele ela eles elas seu sua seus suas
foi sao ser ter tem tinha vai vao pode podem deve devem teve houve fica ficou
hoje ontem amanha agora ja nao sim tudo nada todo toda todos todas
brasil governo policia justica ministerio camara senado congresso presidente
prefeitura estado pais cidade regiao zona bairro rio sao paulo minas bahia
video fotos foto imagens audio live veja entenda balanco caso operacao
janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro
segunda terca quarta quinta sexta sabado domingo
""".split())


def buscar_raw(url, timeout=14):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    bruto = urllib.request.urlopen(req, timeout=timeout).read()
    # detecta o charset: 1º pelo prólogo XML, senão tenta utf-8 e cai pra latin-1
    cab = bruto[:200].decode("ascii", "ignore").lower()
    m = re.search(r'encoding=["\']([\w-]+)["\']', cab)
    if m:
        try:
            return bruto.decode(m.group(1), "replace")
        except (LookupError, UnicodeDecodeError):
            pass
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return bruto.decode("latin-1", "replace")


def _texto(s):
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def parse_feed(xml, limite=15):
    """Devolve [(titulo, link)] na ordem do feed (mais novo primeiro)."""
    itens = []
    blocos = re.findall(r"<item[ >].*?</item>", xml, re.S)
    if not blocos:  # Atom
        blocos = re.findall(r"<entry[ >].*?</entry>", xml, re.S)
    for b in blocos[:limite]:
        mt = re.search(r"<title[^>]*>(.*?)</title>", b, re.S)
        if not mt:
            continue
        titulo = _texto(mt.group(1))
        ml = re.search(r"<link[^>]*>(.*?)</link>", b, re.S)
        link = _texto(ml.group(1)) if ml else ""
        if not link:
            mh = re.search(r'<link[^>]*href="([^"]+)"', b)
            link = mh.group(1) if mh else ""
        if titulo and len(titulo) > 8:
            itens.append((titulo, link))
    return itens


def coletar(fontes, limite=15):
    """Busca todos os feeds em paralelo. Devolve {id: [(titulo, link)]}."""
    res = {}
    def um(f):
        fid, nome, url, tema, conv = f
        try:
            return fid, parse_feed(buscar_raw(url), limite)
        except Exception:
            return fid, []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for fid, itens in ex.map(um, fontes):
            res[fid] = itens
    return res


def norm(w):
    w = unicodedata.normalize("NFKD", w)
    w = "".join(c for c in w if not unicodedata.combining(c))
    return w.lower()


def entidades(titulo):
    """Nomes próprios (entidades de evento) de uma manchete, normalizados."""
    palavras = re.findall(r"[0-9A-Za-zÀ-ÿ]+", titulo)
    ents = set()
    for w in palavras:
        if len(w) < 3:
            continue
        proprio = w[0].isupper() or w.isupper()
        if not proprio:
            continue
        n = norm(w)
        if n in STOP or n.isdigit():
            continue
        ents.add(n)
    return ents


# ============================ DETECÇÃO GIGANTE ================================

def convergencia(dados):
    """
    Cruza os portais PT-geral. Devolve (entidades_convergentes, exemplos)
    onde exemplos = [(nome_portal, manchete)]. Vazio se nada converge.
    """
    pt = [(fid, nome) for (fid, nome, url, tema, conv) in FONTES if conv]
    nome_de = {fid: nome for (fid, nome, url, tema, conv) in FONTES}

    inv = {}       # entidade -> conjunto de portais que a citam
    exemplo = {}   # entidade -> (portal -> primeira manchete que a cita)
    for fid, _ in pt:
        for titulo, link in dados.get(fid, [])[:TOP_CONVERG]:
            for e in entidades(titulo):
                inv.setdefault(e, set()).add(fid)
                if e not in exemplo:
                    exemplo[e] = {}
                if fid not in exemplo[e]:
                    exemplo[e][fid] = titulo

    fortes = {e: pids for e, pids in inv.items() if len(pids) >= MIN_PORTAIS}
    if not fortes:
        return set(), []

    # junta entidades que andam juntas (compartilham portais) num só evento;
    # escolhe o evento com mais portais.
    ents = sorted(fortes, key=lambda e: -len(fortes[e]))
    ancora = ents[0]
    portais_ev = set(fortes[ancora])
    grupo = {ancora}
    for e in ents[1:]:
        if len(fortes[e] & portais_ev) >= MIN_PORTAIS - 1:
            grupo.add(e)
            portais_ev |= fortes[e]

    # exemplos: uma manchete por portal envolvido
    exemplos = []
    usados = set()
    for fid in portais_ev:
        for e in grupo:
            if fid in exemplo.get(e, {}):
                t = exemplo[e][fid]
                if t not in usados:
                    exemplos.append((nome_de[fid], t))
                    usados.add(t)
                break
    return grupo, exemplos


def _estado_path(dia=None):
    dia = dia or datetime.date.today().isoformat()
    return os.path.join(DIR, f"alertados-{dia}.txt")


def _ja_alertado(grupo):
    """True se um evento parecido (>=2 entidades em comum) já foi emitido hoje."""
    p = _estado_path()
    if not os.path.exists(p):
        return False
    g = set(grupo)
    with open(p, encoding="utf-8") as f:
        for linha in f:
            antigo = set(linha.strip().split(","))
            if len(g & antigo) >= min(2, len(g)):
                return True
    return False


def _marcar(grupo):
    os.makedirs(DIR, exist_ok=True)
    with open(_estado_path(), "a", encoding="utf-8") as f:
        f.write(",".join(sorted(grupo)) + "\n")


def cmd_check():
    dados = coletar(FONTES, limite=TOP_CONVERG)
    grupo, exemplos = convergencia(dados)
    if not grupo or len(exemplos) < MIN_PORTAIS:
        return
    if _ja_alertado(grupo):
        return
    _marcar(grupo)  # emite uma vez por evento por dia (o juiz decide se avisa)
    print("CANDIDATO_GIGANTE")
    print("entidades: " + ", ".join(sorted(grupo)))
    print(f"portais: {len(exemplos)}")
    print("---")
    for nome, titulo in exemplos:
        print(f"{nome}: {titulo}")


def cmd_agora():
    dados = coletar(FONTES, limite=TOP_CONVERG)
    grupo, exemplos = convergencia(dados)
    if grupo:
        print(f"Convergindo agora em {len(exemplos)} portais "
              f"(entidades: {', '.join(sorted(grupo))}):\n")
        for nome, titulo in exemplos:
            print(f"• {nome}: {titulo}")
    else:
        print("Nada convergindo forte entre os portais agora "
              "(nenhuma notícia gigante em curso).")


# ================================ PAINEL =====================================

def _dedup(itens):
    """Tira manchetes repetidas/parecidas (mesma entidade-chave)."""
    out, assinaturas = [], []
    for titulo, link in itens:
        ents = entidades(titulo)
        dup = False
        for a in assinaturas:
            if ents and len(ents & a) >= 2:
                dup = True
                break
        if not dup:
            out.append((titulo, link))
            assinaturas.append(ents)
    return out


def _prioriza_time(itens):
    """Se o dono tem time (NEWS_TIME), manchetes do time sobem pro topo."""
    if not TIME_DONO:
        return itens
    alvo = norm(TIME_DONO)
    do_time = [i for i in itens if alvo in norm(i[0])]
    resto = [i for i in itens if alvo not in norm(i[0])]
    return do_time + resto


def cmd_painel():
    dados = coletar(FONTES, limite=8)
    por_tema = {}
    for (fid, nome, url, tema, conv) in FONTES:
        if not tema:
            continue
        por_tema.setdefault(tema, [])
        for titulo, link in dados.get(fid, [])[:3]:
            por_tema[tema].append((titulo, link))

    agora = datetime.datetime.now().strftime("%d/%m %H:%M")
    linhas = [f"🗞️ News — {agora}", ""]
    teve = False
    for tema, rotulo, n in TEMAS_PAINEL:
        itens = _dedup(por_tema.get(tema, []))
        if tema == "futebol":
            itens = _prioriza_time(itens)
        itens = itens[:n]
        if not itens:
            continue
        teve = True
        linhas.append(rotulo)
        for titulo, link in itens:
            linhas.append(f"• {titulo}")
        linhas.append("")
    if not teve:
        linhas.append("Não consegui ler os portais agora — tento de novo já.")
    print("\n".join(linhas).rstrip())


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if arg == "--check":
            cmd_check()
        elif arg == "--painel":
            cmd_painel()
        else:
            cmd_agora()
    except Exception as e:
        if arg != "--check":   # no cron, erro = silêncio (não spammar)
            print(f"Erro no News: {e}")
        sys.exit(0)
