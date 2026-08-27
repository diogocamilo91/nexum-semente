# -*- coding: utf-8 -*-
"""
Tela "Notícias" — as manchetes que o robô de notícias separou.

De onde vem o que aparece aqui:
  • a lista de portais é a do PRÓPRIO robô instalado (`~/semente-bin/news.py`,
    variável FONTES) — a tela não tem lista própria e não inventa fonte nenhuma;
  • as manchetes são lidas na hora, direto dos portais, e ficam só na memória
    por 10 minutos (nada é gravado no disco da pessoa);
  • os avisos de "notícia grande" saem do registro do robô, em
    `~/semente-bin/log/monitor-news.log`.

A tela é SÓ LEITURA: não grava, não apaga, não muda nada.
"""
import os
import re
import html
import time
import email.utils
import datetime
import threading
import importlib.util
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from flask import Response, jsonify, request

CHAVE = "noticias"
TITULO = "Notícias"
ICONE = "jornal"
GRUPO = "ferramentas"
ORDEM = 40

# ------------------------------------------------------------------ ajustes --
_BIN_PADRAO = os.path.expanduser("~/semente-bin")
_VALIDADE = 600        # 10 min: quanto tempo a leitura vale antes de buscar de novo
_TEMPO_PORTAL = 8      # segundos de paciência com cada portal
_POR_PORTAL = 12       # manchetes lidas de cada portal
_POR_DIA = 40          # manchetes mostradas por dia

_ROTULO_TEMA = {
    "": "Geral", "geral": "Geral", "brasil": "Brasil", "mundo": "Mundo",
    "futebol": "Futebol", "tecnologia": "Tecnologia", "economia": "Economia",
}

_lugar = {"bin": _BIN_PADRAO}
_robo_cache = {"tentou": False, "obj": None}
_leitura = {"quando": 0.0, "itens": [], "hora": "", "portais": 0}
_trava = threading.Lock()


# ------------------------------------------------------------------ o robô ---
def _caminho_robo(pasta_bin=None):
    return os.path.join(pasta_bin or _lugar["bin"], "news.py")


def _robo():
    """Carrega o robô de notícias pelo caminho do arquivo (sem mexer no resto)."""
    if _robo_cache["tentou"]:
        return _robo_cache["obj"]
    _robo_cache["tentou"] = True
    try:
        caminho = _caminho_robo()
        if os.path.isfile(caminho):
            spec = importlib.util.spec_from_file_location("semente_tela_news", caminho)
            obj = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(obj)
            _robo_cache["obj"] = obj
    except Exception:
        _robo_cache["obj"] = None
    return _robo_cache["obj"]


def _fontes():
    """[(id, nome, endereço, tema)] — a lista de portais do próprio robô."""
    saida = []
    try:
        for f in (getattr(_robo(), "FONTES", None) or []):
            try:
                endereco = str(f[2])
                if not endereco.startswith(("http://", "https://")):
                    continue
                saida.append((str(f[0]), str(f[1]), endereco,
                              (str(f[3]) if len(f) > 3 else "").strip().lower()))
            except Exception:
                continue
    except Exception:
        return []
    return saida


# ------------------------------------------------------------- leitura RSS --
_BLOCO = re.compile(r"<(item|entry)[\s>].*?</\1>", re.S | re.I)
_TITULO_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_LINK_RE = re.compile(r"<link[^>]*>(.*?)</link>", re.S | re.I)
_LINK_HREF = re.compile(r'<link[^>]*href="([^"]+)"', re.I)
_DATA_RE = re.compile(
    r"<(pubDate|published|updated|dc:date)[^>]*>(.*?)</\1>", re.S | re.I)
_CABECALHO = {"User-Agent": "Mozilla/5.0 (compatible; leitor-de-noticias)"}


def _limpa(texto):
    texto = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", texto or "", flags=re.S)
    texto = re.sub(r"<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()


def _baixa(endereco):
    ler = getattr(_robo(), "buscar_raw", None)
    if callable(ler):
        return ler(endereco, timeout=_TEMPO_PORTAL)
    pedido = urllib.request.Request(endereco, headers=_CABECALHO)
    with urllib.request.urlopen(pedido, timeout=_TEMPO_PORTAL) as r:
        bruto = r.read()
    try:
        return bruto.decode("utf-8")
    except Exception:
        return bruto.decode("latin-1", "replace")


def _momento(texto):
    """Converte a data do feed em data/hora local. None se não der pra ler."""
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        d = email.utils.parsedate_to_datetime(texto)
    except Exception:
        d = None
    if d is None:
        try:
            d = datetime.datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except Exception:
            return None
    try:
        if d.tzinfo is None:
            return d
        return d.astimezone()
    except Exception:
        return None


def _le_portal(fonte):
    _fid, nome, endereco, tema = fonte
    itens = []
    try:
        xml = _baixa(endereco)
    except Exception:
        return itens
    try:
        blocos = list(_BLOCO.finditer(xml))[:_POR_PORTAL]
    except Exception:
        return itens
    for bloco in blocos:
        try:
            pedaco = bloco.group(0)
            mt = _TITULO_RE.search(pedaco)
            if not mt:
                continue
            manchete = _limpa(mt.group(1))
            if len(manchete) < 9:
                continue
            ml = _LINK_RE.search(pedaco)
            link = _limpa(ml.group(1)) if ml else ""
            if not link:
                mh = _LINK_HREF.search(pedaco)
                link = (mh.group(1) if mh else "").strip()
            if not link.startswith(("http://", "https://")):
                link = ""
            md = _DATA_RE.search(pedaco)
            quando = _momento(md.group(2)) if md else None
            itens.append({
                "manchete": manchete,
                "link": html.unescape(link),
                "fonte": nome,
                "tema": tema or "geral",
                "quando": quando,
            })
        except Exception:
            continue
    return itens


def _assinatura(manchete):
    texto = re.sub(r"[^0-9a-zà-ÿ ]+", " ", (manchete or "").lower())
    return " ".join(texto.split())[:90]


def _coleta():
    """Lê todos os portais em paralelo. Devolve (itens, quantos portais deram certo)."""
    fontes = _fontes()
    if not fontes:
        return [], 0
    tudo, ok = [], 0
    try:
        with ThreadPoolExecutor(max_workers=6) as ex:
            for parte in ex.map(_le_portal, fontes):
                if parte:
                    ok += 1
                    tudo.extend(parte)
    except Exception:
        pass
    vistas, limpo = set(), []
    for it in tudo:
        chave = _assinatura(it["manchete"])
        if not chave or chave in vistas:
            continue
        vistas.add(chave)
        limpo.append(it)
    limpo.sort(key=lambda i: (i["quando"] or datetime.datetime.min).timestamp()
               if i["quando"] else -1.0, reverse=True)
    return limpo, ok


def _manchetes(forcar=False):
    """Leitura com validade de 10 minutos, guardada só na memória."""
    with _trava:
        agora = time.monotonic()
        fresca = (_leitura["itens"] and (agora - _leitura["quando"]) < _VALIDADE)
        if fresca and not forcar:
            return dict(_leitura, velha=False)
        try:
            itens, portais = _coleta()
        except Exception:
            itens, portais = [], 0
        if itens:
            _leitura.update({
                "quando": agora, "itens": itens, "portais": portais,
                "hora": datetime.datetime.now().strftime("%H:%M"),
            })
            return dict(_leitura, velha=False)
        if _leitura["itens"]:
            return dict(_leitura, velha=True)
        return {"quando": agora, "itens": [], "hora": "", "portais": 0, "velha": False}


# ------------------------------------------------- avisos de notícia grande --
_LINHA_ALERTA = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}:\d{2}):\d{2}\s+ALERTA GIGANTE enviado:\s*(.+)$")


def _avisos_grandes(limite=4):
    """Os avisos de 'notícia grande' que o robô já mandou (do registro dele)."""
    achados = []
    try:
        caminho = os.path.join(_lugar["bin"], "log", "monitor-news.log")
        if not os.path.isfile(caminho):
            return []
        tamanho = os.path.getsize(caminho)
        with open(caminho, "rb") as f:
            if tamanho > 60000:
                f.seek(tamanho - 60000)
            bruto = f.read().decode("utf-8", "replace")
        for linha in bruto.splitlines():
            m = _LINHA_ALERTA.match(linha.strip())
            if m:
                achados.append({
                    "dia": "%s/%s/%s" % (m.group(3), m.group(2), m.group(1)),
                    "hora": m.group(4),
                    "texto": m.group(5).strip(),
                })
    except Exception:
        return []
    achados.reverse()
    return achados[:limite]


# ---------------------------------------------------------------- desenho ---
def _dia_rotulo(dia):
    hoje = datetime.date.today()
    if dia == hoje:
        return "Hoje"
    if dia == hoje - datetime.timedelta(days=1):
        return "Ontem"
    return dia.strftime("%d/%m/%Y")


def _e(txt):
    return html.escape(str(txt if txt is not None else ""), quote=True)


def _html_manchetes(dados):
    itens = dados.get("itens") or []
    if not itens:
        if not _fontes():
            return ("<div class=vazio>O robô de notícias ainda não está instalado nesta "
                    "máquina — quando ele entrar, as manchetes aparecem aqui sozinhas.</div>")
        return ("<div class=vazio>Não consegui ler os portais agora. Pode ser a internet "
                "da máquina ou os próprios sites fora do ar. Toque em <b>Atualizar</b> "
                "daqui a pouco.</div>")

    grupos, ordem, sem_data = {}, [], []
    for it in itens:
        if it["quando"] is None:
            sem_data.append(it)
            continue
        dia = it["quando"].date()
        if dia not in grupos:
            grupos[dia] = []
            ordem.append(dia)
        grupos[dia].append(it)
    ordem.sort(reverse=True)

    partes = []
    partes.append(
        "<div class=kpis>"
        "<div class=kpi><b>%d</b><span>manchetes</span></div>"
        "<div class=kpi><b>%d</b><span>portais lidos</span></div>"
        "<div class=kpi><b>%s</b><span>leitura das</span></div>"
        "</div>" % (len(itens), dados.get("portais") or 0,
                    _e(dados.get("hora") or "--:--")))
    if dados.get("velha"):
        partes.append("<div class='aviso atencao'>Os portais não responderam nesta "
                      "tentativa — o que está abaixo é a última leitura que deu certo.</div>")

    def bloco(titulo, lista):
        mostradas = lista[:_POR_DIA]
        linhas = ["<div class=nx-not-dia><div class=nx-not-cab>%s <span class=fraco>· %d</span></div><div class=lista>"
                  % (_e(titulo), len(lista))]
        for it in mostradas:
            hora = it["quando"].strftime("%H:%M") if it["quando"] else ""
            busca = _e((it["manchete"] + " " + it["fonte"]).lower())
            miolo = ("<div class=nx-not-tit>%s</div>"
                     "<div class=nx-not-pe><span class=chip>%s</span>"
                     "<span class=fraco>%s</span>%s</div>"
                     % (_e(it["manchete"]), _e(it["fonte"]),
                        _e(_ROTULO_TEMA.get(it["tema"], it["tema"].capitalize())),
                        ("<span class=fraco>· %s</span>" % _e(hora)) if hora else ""))
            if it["link"]:
                linhas.append(
                    "<a class='item nx-not-item' data-tema='%s' data-txt='%s' "
                    "href='%s' target='_blank' rel='noopener noreferrer'>%s</a>"
                    % (_e(it["tema"]), busca, _e(it["link"]), miolo))
            else:
                linhas.append("<div class='item nx-not-item' data-tema='%s' data-txt='%s'>%s</div>"
                              % (_e(it["tema"]), busca, miolo))
        linhas.append("</div>")
        if len(lista) > len(mostradas):
            # o número do cabeçalho é o total do dia; sem esta linha a lista
            # mostraria menos manchetes do que o número prometido, calada
            linhas.append("<div class=fraco style='font-size:.82rem;margin-top:6px'>"
                          "Mostrando as %d mais recentes deste dia.</div>" % len(mostradas))
        linhas.append("</div>")
        return "".join(linhas)

    for dia in ordem:
        partes.append(bloco(_dia_rotulo(dia), grupos[dia]))
    if sem_data:
        partes.append(bloco("Sem data informada pelo portal", sem_data))
    return "".join(partes)


_CSS = """
.nx-not-topo{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.nx-not-topo .campo{flex:1 1 180px;min-width:0}
.nx-not-filtros{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px}
.nx-not-f{cursor:pointer;font:inherit;font-size:.82rem;min-height:34px;padding:5px 13px;
  border:1px solid var(--linha);background:transparent;color:var(--fraco)}
.nx-not-f.on{background:var(--marca);border-color:var(--marca);color:var(--fundo)}
.nx-not-dia{margin-top:14px}
.nx-not-cab{font-weight:700;font-size:.95rem;margin:0 0 6px;color:var(--texto)}
/* `.lista .item` do estilo da casa é display:flex e ganha de `.nx-not-item` sozinho:
   sem o `.lista` na frente, manchete e rodapé ficam lado a lado no celular. */
.lista .nx-not-item{display:block;text-decoration:none;color:inherit}
.nx-not-tit{font-weight:600;line-height:1.35}
.nx-not-pe{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:4px;font-size:.82rem}
.nx-not-grande{display:flex;gap:8px;align-items:baseline;padding:6px 0;border-bottom:1px solid var(--linha)}
.nx-not-grande:last-child{border-bottom:0}
"""

_JS = """
(function(){
  var caixa=document.getElementById('nx-not-lista');
  var busca=document.getElementById('nx-not-busca');
  var vazioBusca=document.getElementById('nx-not-nada');
  var botao=document.getElementById('nx-not-atualizar');
  var tema='';
  if(!caixa){return;}
  function filtra(){
    var q=(busca&&busca.value?busca.value:'').trim().toLowerCase();
    var dias=caixa.querySelectorAll('.nx-not-dia'), total=0, vistos=0;
    for(var i=0;i<dias.length;i++){
      var itens=dias[i].querySelectorAll('.nx-not-item'), n=0;
      for(var j=0;j<itens.length;j++){
        var it=itens[j]; total++;
        var t=it.getAttribute('data-tema')||'';
        var txt=it.getAttribute('data-txt')||'';
        var ok=(!tema||t===tema)&&(!q||txt.indexOf(q)>=0);
        it.style.display=ok?'':'none';
        if(ok){n++;vistos++;}
      }
      dias[i].style.display=n?'':'none';
    }
    if(vazioBusca){vazioBusca.style.display=(total&&!vistos)?'':'none';}
  }
  function carrega(forcar){
    caixa.innerHTML='<div class=vazio>Lendo os portais agora… leva alguns segundos.</div>';
    if(vazioBusca){vazioBusca.style.display='none';}
    if(botao){botao.disabled=true;}
    fetch('/api/noticias/manchetes'+(forcar?'?atualizar=1':''),{credentials:'same-origin'})
      .then(function(r){return r.json();})
      .then(function(d){
        caixa.innerHTML=(d&&d.html)?d.html:'<div class=vazio>Não consegui ler os portais agora.</div>';
        filtra();
      })
      .catch(function(){
        caixa.innerHTML='<div class=vazio>Não consegui falar com a máquina agora. Tente de novo em instantes.</div>';
      })
      .then(function(){ if(botao){botao.disabled=false;} });
  }
  var chips=document.querySelectorAll('.nx-not-f');
  for(var k=0;k<chips.length;k++){
    chips[k].addEventListener('click',function(){
      for(var m=0;m<chips.length;m++){chips[m].classList.remove('on');}
      this.classList.add('on');
      tema=this.getAttribute('data-tema')||'';
      filtra();
    });
  }
  if(busca){busca.addEventListener('input',filtra);}
  if(botao){botao.addEventListener('click',function(){carrega(true);});}
  carrega(false);
})();
"""


def disponivel(cfg):
    """A tela existe se o módulo de notícias foi instalado nesta máquina."""
    try:
        valor = str((cfg or {}).get("NEWS_ATIVO", "")).strip().lower()
        if valor in ("sim", "s", "1", "true", "yes"):
            return True
        if valor in ("nao", "não", "n", "0", "false", "no"):
            return False
        pasta = str((cfg or {}).get("DIR_BIN") or "").strip()
        if pasta:
            _lugar["bin"] = os.path.expanduser(pasta)
        return os.path.isfile(_caminho_robo())
    except Exception:
        return False


def registra(app, casca, exige_login):
    try:
        pasta = getattr(casca, "DIR_BIN", None)
        if pasta:
            _lugar["bin"] = os.path.expanduser(str(pasta))
    except Exception:
        pass

    @app.get("/noticias")
    def tela_noticias():
        exige_login()
        try:
            temas, vistos = [], set()
            for (_i, _n, _u, tema) in _fontes():
                tema = tema or "geral"
                if tema not in vistos:
                    vistos.add(tema)
                    temas.append(tema)
            chips = ["<button type=button class='chip nx-not-f on' data-tema=''>Tudo</button>"]
            for tema in temas:
                chips.append("<button type=button class='chip nx-not-f' data-tema='%s'>%s</button>"
                             % (_e(tema), _e(_ROTULO_TEMA.get(tema, tema.capitalize()))))

            grandes = _avisos_grandes()
            bloco_grandes = ""
            if grandes:
                linhas = "".join(
                    "<div class=nx-not-grande><span class=chip>%s %s</span>"
                    "<span>%s</span></div>" % (_e(g["dia"]), _e(g["hora"]), _e(g["texto"]))
                    for g in grandes)
                bloco_grandes = (
                    "<div class=cartao><h2>Avisos de notícia grande</h2>"
                    "<p class=fraco>Quando a mesma notícia estoura em vários portais ao "
                    "mesmo tempo, você recebe um aviso. Estes foram os últimos:</p>%s</div>"
                    % linhas)

            corpo = (
                "<div class=cartao>"
                "<div class=nx-not-topo>"
                "<h2 style='margin:0;flex:1 1 auto'>Manchetes de agora</h2>"
                "<button type=button class=btn id=nx-not-atualizar>Atualizar</button>"
                "</div>"
                "<p class=fraco>As manchetes que os portais estão publicando, "
                "agrupadas por dia. Toque em uma para abrir no site de origem.</p>"
                "<div class=nx-not-topo>"
                "<input class=campo id=nx-not-busca type=search "
                "placeholder='Procurar por palavra ou portal…' autocomplete=off>"
                "</div>"
                "<div class=nx-not-filtros>%s</div>"
                "<div id=nx-not-lista><div class=vazio>Lendo os portais agora…</div></div>"
                "<div class=vazio id=nx-not-nada style='display:none'>"
                "Nenhuma manchete com essa palavra nesta leitura.</div>"
                "</div>%s" % ("".join(chips), bloco_grandes))
        except Exception:
            corpo = ("<div class=cartao><div class=vazio>Não consegui montar a tela de "
                     "notícias agora. Nada foi perdido — tente abrir de novo em instantes."
                     "</div></div>")
        return Response(casca.shell(TITULO, corpo, "/noticias", css=_CSS, js=_JS),
                        mimetype="text/html")

    @app.get("/api/noticias/manchetes")
    def api_noticias_manchetes():
        exige_login()
        try:
            forcar = str(request.args.get("atualizar", "")).strip() == "1"
            dados = _manchetes(forcar=forcar)
            return jsonify({"ok": True, "html": _html_manchetes(dados),
                            "quantas": len(dados.get("itens") or [])})
        except Exception:
            return jsonify({"ok": False, "quantas": 0, "html":
                            "<div class=vazio>Não consegui ler os portais agora. "
                            "Toque em Atualizar daqui a pouco.</div>"})
