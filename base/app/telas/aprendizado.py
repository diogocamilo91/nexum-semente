# -*- coding: utf-8 -*-
"""
Tela "Aprendizado" — o que saiu de novo nos canais que a pessoa acompanha.

De onde vem o que aparece aqui:
  • a lista de canais é a MESMA que o robô usa
    (`~/.config/semente/aprendizado_canais.json`) — a tela não cadastra canal
    nenhum e não inventa canal nenhum;
  • os lançamentos são lidos na hora, do canal, e ficam só na memória por 15
    minutos (nada é gravado no disco da pessoa).

A tela é SÓ LEITURA: não grava, não apaga, não muda nada.
"""
import os
import json
import html
import time
import datetime
import threading
import importlib.util
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

from flask import Response, jsonify, request

CHAVE = "aprendizado"
TITULO = "Aprendizado"
ICONE = "chave"
GRUPO = "ferramentas"
ORDEM = 50

_BIN_PADRAO = os.path.expanduser("~/semente-bin")
_CANAIS_PADRAO = os.path.expanduser("~/.config/semente/aprendizado_canais.json")
_VALIDADE = 900          # 15 min de validade da leitura (só na memória)
_TEMPO_CANAL = 8         # segundos de paciência com cada canal
_JANELAS = (2, 7, 30)    # dias que a pessoa pode escolher
_JANELA_PADRAO = 7
_POR_DIA = 40

_lugar = {"bin": _BIN_PADRAO}
_robo_cache = {"tentou": False, "obj": None}
_leitura = {}            # dias -> {"quando", "itens", "hora", "falhas"}
_trava = threading.Lock()


# ------------------------------------------------------------------ o robô ---
def _caminho_robo():
    return os.path.join(_lugar["bin"], "aprendizado.py")


def _robo():
    """Carrega o robô de aprendizado pelo caminho do arquivo (sem mexer no resto)."""
    if _robo_cache["tentou"]:
        return _robo_cache["obj"]
    _robo_cache["tentou"] = True
    try:
        caminho = _caminho_robo()
        if os.path.isfile(caminho):
            spec = importlib.util.spec_from_file_location("semente_tela_aprendizado", caminho)
            obj = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(obj)
            _robo_cache["obj"] = obj
    except Exception:
        _robo_cache["obj"] = None
    return _robo_cache["obj"]


def _arquivo_canais():
    try:
        caminho = getattr(_robo(), "CONFIG", None)
        if caminho:
            return os.path.expanduser(str(caminho))
    except Exception:
        pass
    return _CANAIS_PADRAO


def _canais():
    """[(tema, nome, id)] — os canais cadastrados, na ordem em que foram gravados."""
    saida = []
    try:
        with open(_arquivo_canais(), encoding="utf-8") as f:
            dados = json.load(f)
    except Exception:
        return []
    try:
        temas = dados.get("temas") or {}
        for tema, lista in temas.items():
            for canal in (lista or []):
                try:
                    ident = str(canal.get("id") or "").strip()
                    nome = str(canal.get("nome") or "").strip() or "Canal"
                    if ident:
                        saida.append((str(tema).strip(), nome, ident))
                except Exception:
                    continue
    except Exception:
        return []
    return saida


# ------------------------------------------------------------------ leitura --
_CABECALHO = {"User-Agent": "Mozilla/5.0 (compatible; leitor-de-canais)"}
_ATOM = "{http://www.w3.org/2005/Atom}"
_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id="


def _momento(texto):
    try:
        d = datetime.datetime.fromisoformat(str(texto or "").strip().replace("Z", "+00:00"))
    except Exception:
        return None
    try:
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        return d
    except Exception:
        return None


def _le_canal_local(ident, limite):
    """Plano B: lê o feed público de lançamentos do canal (só stdlib)."""
    itens = []
    pedido = urllib.request.Request(
        _FEED + urllib.parse.quote(str(ident), safe=""), headers=_CABECALHO)
    with urllib.request.urlopen(pedido, timeout=_TEMPO_CANAL) as r:
        raiz = ET.fromstring(r.read())
    for entrada in raiz.findall(_ATOM + "entry"):
        try:
            titulo = (entrada.findtext(_ATOM + "title") or "").strip()
            elo = entrada.find(_ATOM + "link")
            link = (elo.get("href") if elo is not None else "") or ""
            quando = _momento(entrada.findtext(_ATOM + "published"))
            if not titulo or quando is None or quando < limite:
                continue
            itens.append({
                "titulo": titulo,
                "link": link,
                "pub": quando,
                "short": ("/shorts/" in link) or ("#shorts" in titulo.lower()),
            })
        except Exception:
            continue
    return itens


def _le_canal(canal, limite):
    """Devolve (itens, deu_certo). Usa o robô instalado; se não der, o plano B."""
    tema, nome, ident = canal
    funcao = getattr(_robo(), "uploads_canal", None)
    if callable(funcao):
        try:
            bruto = funcao({"nome": nome, "id": ident}, limite, False)
            if isinstance(bruto, dict):
                return [], False
            return list(bruto or []), True
        except Exception:
            pass
    try:
        return _le_canal_local(ident, limite), True
    except Exception:
        return [], False


def _coleta(dias):
    """Lê todos os canais em paralelo. Devolve (itens, canais que falharam)."""
    canais = _canais()
    if not canais:
        return [], []
    limite = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=dias)
    itens, falhas = [], []

    def um(canal):
        lidos, ok = _le_canal(canal, limite)
        return canal, lidos, ok

    try:
        with ThreadPoolExecutor(max_workers=6) as ex:
            for canal, lidos, ok in ex.map(um, canais):
                tema, nome, _ident = canal
                if not ok:
                    falhas.append(nome)
                    continue
                for v in lidos:
                    try:
                        quando = v.get("pub")
                        # coletor que devolva data em texto (ou sem fuso) derrubaria
                        # TODO item na comparação abaixo, e calado
                        if quando is not None and not isinstance(
                                quando, datetime.datetime):
                            quando = _momento(quando)
                        elif quando is not None and quando.tzinfo is None:
                            quando = quando.replace(tzinfo=datetime.timezone.utc)
                        # a janela é conferida aqui também: o que o coletor devolver
                        # fora dela não entra (o rótulo "últimos N dias" tem que ser verdade)
                        if quando is not None and quando < limite:
                            continue
                        link = str(v.get("link") or "")
                        if not link.startswith(("http://", "https://")):
                            link = ""
                        itens.append({
                            "titulo": str(v.get("titulo") or "").strip(),
                            "link": link,
                            "canal": nome,
                            "tema": tema,
                            "curto": bool(v.get("short")),
                            "quando": quando.astimezone() if quando else None,
                        })
                    except Exception:
                        continue
    except Exception:
        pass
    itens = [i for i in itens if i["titulo"]]
    itens.sort(key=lambda i: i["quando"].timestamp() if i["quando"] else -1.0, reverse=True)
    return itens, falhas


def _novidades(dias, forcar=False):
    with _trava:
        agora = time.monotonic()
        guardado = _leitura.get(dias)
        if guardado and not forcar and (agora - guardado["quando"]) < _VALIDADE:
            return dict(guardado, velha=False)
        try:
            itens, falhas = _coleta(dias)
        except Exception:
            itens, falhas = [], []
        pacote = {"quando": agora, "itens": itens, "falhas": falhas,
                  "hora": datetime.datetime.now().strftime("%H:%M")}
        if itens or not falhas:
            # só guarda leitura que deu certo: vazio POR FALHA guardado por 15 min
            # deixaria a tela repetindo "nada novo" mesmo depois da internet voltar
            _leitura[dias] = pacote
            return dict(pacote, velha=False)
        if guardado:
            return dict(guardado, velha=True)
        return dict(pacote, velha=False)


# ---------------------------------------------------------------- desenho ---
def _e(txt):
    return html.escape(str(txt if txt is not None else ""), quote=True)


def _dia_rotulo(dia):
    hoje = datetime.date.today()
    if dia == hoje:
        return "Hoje"
    if dia == hoje - datetime.timedelta(days=1):
        return "Ontem"
    return dia.strftime("%d/%m/%Y")


def _html_novidades(dados, dias):
    itens = dados.get("itens") or []
    falhas = dados.get("falhas") or []
    partes = []

    if not _canais():
        return ("<div class=vazio>Nenhum canal cadastrado ainda. Me diga qual canal você "
                "acompanha que eu passo a olhar os lançamentos dele todo dia.</div>")
    if not itens:
        if falhas:
            # "não consegui ler" NÃO é "não saiu nada": dizer que não saiu nada aqui
            # seria inventar uma resposta que a tela não tem
            return ("<div class=vazio>Não consegui olhar %s agora — então não dá pra "
                    "dizer se saiu coisa nova. Pode ser a internet da máquina ou o "
                    "próprio site fora do ar. Toque em <b>Atualizar</b> daqui a pouco."
                    "</div>" % _e(", ".join(falhas)))
        return ("<div class=vazio>Nada novo nos últimos %d dias nos seus canais. "
                "Assim que sair vídeo novo em algum deles, ele aparece aqui.</div>"
                % dias)

    partes.append(
        "<div class=kpis>"
        "<div class=kpi><b>%d</b><span>novidades</span></div>"
        "<div class=kpi><b>%d</b><span>dias olhados</span></div>"
        "<div class=kpi><b>%s</b><span>leitura das</span></div>"
        "</div>" % (len(itens), dias, _e(dados.get("hora") or "--:--")))
    if dados.get("velha"):
        partes.append("<div class='aviso atencao'>Os canais não responderam nesta "
                      "tentativa — o que está abaixo é a última leitura que deu certo.</div>")
    if falhas:
        partes.append("<div class='aviso atencao'>Não consegui ler %s. "
                      "O resto está aqui.</div>" % _e(", ".join(falhas)))

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

    def bloco(titulo, lista):
        linhas = ["<div class=nx-apr-dia><div class=nx-apr-cab>%s "
                  "<span class=fraco>· %d</span></div><div class=lista>"
                  % (_e(titulo), len(lista))]
        mostradas = lista[:_POR_DIA]
        for it in mostradas:
            hora = it["quando"].strftime("%H:%M") if it["quando"] else ""
            busca = _e((it["titulo"] + " " + it["canal"] + " " + it["tema"]).lower())
            miolo = ("<div class=nx-apr-tit>%s</div>"
                     "<div class=nx-apr-pe><span class=chip>%s</span>%s%s%s</div>"
                     % (_e(it["titulo"]), _e(it["canal"]),
                        ("<span class=fraco>%s</span>" % _e(it["tema"])) if it["tema"] else "",
                        ("<span class=fraco>· %s</span>" % _e(hora)) if hora else "",
                        "<span class=chip>curto</span>" if it["curto"] else ""))
            if it["link"]:
                linhas.append(
                    "<a class='item nx-apr-item' data-txt='%s' href='%s' "
                    "target='_blank' rel='noopener noreferrer'>%s</a>"
                    % (busca, _e(it["link"]), miolo))
            else:
                linhas.append("<div class='item nx-apr-item' data-txt='%s'>%s</div>"
                              % (busca, miolo))
        linhas.append("</div>")
        if len(lista) > len(mostradas):
            # o número do cabeçalho é o total do dia; sem esta linha a lista
            # mostraria menos itens do que o número prometido, calada
            linhas.append("<div class=fraco style='font-size:.82rem;margin-top:6px'>"
                          "Mostrando os %d mais recentes deste dia.</div>" % len(mostradas))
        linhas.append("</div>")
        return "".join(linhas)

    for dia in ordem:
        partes.append(bloco(_dia_rotulo(dia), grupos[dia]))
    if sem_data:
        partes.append(bloco("Sem data informada pelo canal", sem_data))
    return "".join(partes)


_CSS = """
.nx-apr-topo{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.nx-apr-topo .campo{flex:1 1 180px;min-width:0}
.nx-apr-filtros{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px}
.nx-apr-f{cursor:pointer;font:inherit;font-size:.82rem;min-height:34px;padding:5px 13px;
  border:1px solid var(--linha);background:transparent;color:var(--fraco)}
.nx-apr-f.on{background:var(--marca);border-color:var(--marca);color:var(--fundo)}
.nx-apr-dia{margin-top:14px}
.nx-apr-cab{font-weight:700;font-size:.95rem;margin:0 0 6px;color:var(--texto)}
/* `.lista .item` do estilo da casa é display:flex e ganha de `.nx-apr-item` sozinho:
   sem o `.lista` na frente, título e rodapé ficam lado a lado no celular. */
.lista .nx-apr-item{display:block;text-decoration:none;color:inherit}
.nx-apr-tit{font-weight:600;line-height:1.35}
.nx-apr-pe{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:4px;font-size:.82rem}
.nx-apr-tema{font-weight:700;font-size:.9rem;margin:10px 0 4px}
.nx-apr-canais{display:flex;gap:6px;flex-wrap:wrap}
"""

_JS = """
(function(){
  var caixa=document.getElementById('nx-apr-lista');
  var busca=document.getElementById('nx-apr-busca');
  var nada=document.getElementById('nx-apr-nada');
  var botao=document.getElementById('nx-apr-atualizar');
  var chips=document.querySelectorAll('.nx-apr-f');
  var dias='7';
  if(!caixa){return;}
  function filtra(){
    var q=(busca&&busca.value?busca.value:'').trim().toLowerCase();
    var blocos=caixa.querySelectorAll('.nx-apr-dia'), total=0, vistos=0;
    for(var i=0;i<blocos.length;i++){
      var itens=blocos[i].querySelectorAll('.nx-apr-item'), n=0;
      for(var j=0;j<itens.length;j++){
        var ok=!q||(itens[j].getAttribute('data-txt')||'').indexOf(q)>=0;
        itens[j].style.display=ok?'':'none';
        total++; if(ok){n++;vistos++;}
      }
      blocos[i].style.display=n?'':'none';
    }
    if(nada){nada.style.display=(total&&!vistos)?'':'none';}
  }
  function carrega(forcar){
    caixa.innerHTML='<div class=vazio>Olhando os seus canais… leva alguns segundos.</div>';
    if(nada){nada.style.display='none';}
    if(botao){botao.disabled=true;}
    fetch('/api/aprendizado/novidades?dias='+encodeURIComponent(dias)+(forcar?'&atualizar=1':''),
          {credentials:'same-origin'})
      .then(function(r){return r.json();})
      .then(function(d){
        caixa.innerHTML=(d&&d.html)?d.html:'<div class=vazio>Não consegui olhar os canais agora.</div>';
        filtra();
      })
      .catch(function(){
        caixa.innerHTML='<div class=vazio>Não consegui falar com a máquina agora. Tente de novo em instantes.</div>';
      })
      .then(function(){ if(botao){botao.disabled=false;} });
  }
  for(var k=0;k<chips.length;k++){
    chips[k].addEventListener('click',function(){
      for(var m=0;m<chips.length;m++){chips[m].classList.remove('on');}
      this.classList.add('on');
      dias=this.getAttribute('data-dias')||'7';
      carrega(false);
    });
  }
  if(busca){busca.addEventListener('input',filtra);}
  if(botao){botao.addEventListener('click',function(){carrega(true);});}
  carrega(false);
})();
"""


def disponivel(cfg):
    """A tela existe se o módulo de aprendizado foi instalado nesta máquina."""
    try:
        valor = str((cfg or {}).get("APRENDIZADO_ATIVO", "")).strip().lower()
        if valor in ("sim", "s", "1", "true", "yes"):
            return True
        if valor in ("nao", "não", "n", "0", "false", "no"):
            return False
        pasta = str((cfg or {}).get("DIR_BIN") or "").strip()
        if pasta:
            _lugar["bin"] = os.path.expanduser(pasta)
        return os.path.isfile(_caminho_robo()) or os.path.isfile(_CANAIS_PADRAO)
    except Exception:
        return False


def registra(app, casca, exige_login):
    try:
        pasta = getattr(casca, "DIR_BIN", None)
        if pasta:
            _lugar["bin"] = os.path.expanduser(str(pasta))
    except Exception:
        pass

    @app.get("/aprendizado")
    def tela_aprendizado():
        exige_login()
        try:
            canais = _canais()
            chips = []
            for dias in _JANELAS:
                rotulo = "Últimos %d dias" % dias
                chips.append("<button type=button class='chip nx-apr-f%s' data-dias='%d'>%s</button>"
                             % (" on" if dias == _JANELA_PADRAO else "", dias, rotulo))

            if canais:
                por_tema, ordem = {}, []
                for tema, nome, _ident in canais:
                    tema = tema or "canais"
                    if tema not in por_tema:
                        por_tema[tema] = []
                        ordem.append(tema)
                    por_tema[tema].append(nome)
                blocos = []
                for tema in ordem:
                    blocos.append(
                        "<div class=nx-apr-tema>%s</div><div class=nx-apr-canais>%s</div>"
                        % (_e(tema), "".join("<span class=chip>%s</span>" % _e(n)
                                             for n in por_tema[tema])))
                bloco_canais = (
                    "<div class=cartao><h2 style='margin-top:0'>Canais que você acompanha</h2>"
                    "<p class=fraco>São estes que eu olho todo dia. Para incluir ou tirar "
                    "algum, é só me falar.</p>%s</div>" % "".join(blocos))
            else:
                bloco_canais = (
                    "<div class=cartao><h2 style='margin-top:0'>Canais que você acompanha</h2>"
                    "<div class=vazio>Nenhum canal cadastrado ainda — me diga qual canal "
                    "você acompanha que eu cuido do resto.</div></div>")

            corpo = (
                "<div class=cartao>"
                "<div class=nx-apr-topo>"
                "<h2 style='margin:0;flex:1 1 auto'>O que saiu de novo</h2>"
                "<button type=button class=btn id=nx-apr-atualizar>Atualizar</button>"
                "</div>"
                "<p class=fraco>Os lançamentos dos canais que você acompanha, agrupados "
                "por dia. Toque em um para abrir. A escolha comentada do dia continua "
                "chegando no resumo da noite.</p>"
                "<div class=nx-apr-filtros>%s</div>"
                "<div class=nx-apr-topo>"
                "<input class=campo id=nx-apr-busca type=search "
                "placeholder='Procurar por palavra ou canal…' autocomplete=off>"
                "</div>"
                "<div id=nx-apr-lista><div class=vazio>Olhando os seus canais…</div></div>"
                "<div class=vazio id=nx-apr-nada style='display:none'>"
                "Nenhuma novidade com essa palavra nesta janela.</div>"
                "</div>%s" % ("".join(chips), bloco_canais))
        except Exception:
            corpo = ("<div class=cartao><div class=vazio>Não consegui montar a tela de "
                     "aprendizado agora. Nada foi perdido — tente abrir de novo em "
                     "instantes.</div></div>")
        return Response(casca.shell(TITULO, corpo, "/aprendizado", css=_CSS, js=_JS),
                        mimetype="text/html")

    @app.get("/api/aprendizado/novidades")
    def api_aprendizado_novidades():
        exige_login()
        try:
            try:
                dias = int(str(request.args.get("dias", _JANELA_PADRAO)).strip())
            except Exception:
                dias = _JANELA_PADRAO
            if dias not in _JANELAS:
                dias = _JANELA_PADRAO
            forcar = str(request.args.get("atualizar", "")).strip() == "1"
            dados = _novidades(dias, forcar=forcar)
            return jsonify({"ok": True, "dias": dias,
                            "quantas": len(dados.get("itens") or []),
                            "html": _html_novidades(dados, dias)})
        except Exception:
            return jsonify({"ok": False, "quantas": 0, "html":
                            "<div class=vazio>Não consegui olhar os canais agora. "
                            "Toque em Atualizar daqui a pouco.</div>"})
