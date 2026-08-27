# -*- coding: utf-8 -*-
"""
Tela "Gravações" — as gravações que já foram transcritas.

De onde vem o que aparece aqui: os arquivos de texto que o robô de gravações
escreve depois de transcrever um áudio (um arquivo `.md` por gravação, dentro
da pasta de conhecimento, em `pessoal/gravacoes/`). A tela lê esses arquivos e
mostra a ficha e a transcrição.

Regras desta tela:
  • SÓ LEITURA — não grava, não apaga, não move nada;
  • o ÁUDIO ORIGINAL nunca é servido nem aberto por aqui (pode ter conversa de
    terceiro); só o texto aparece.
"""
import os
import re
import html
import datetime
import urllib.parse

from flask import Response

CHAVE = "gravacoes"
TITULO = "Gravações"
ICONE = "microfone"
GRUPO = "ferramentas"
ORDEM = 45

def _pastas_padrao(cfg=None):
    """Onde as gravações podem estar. A pasta de conhecimento é ESCOLHA da pessoa
    (DIR_CONHECIMENTO no config) — chumbar ~/nexum aqui faz a tela olhar o lugar
    errado em quem escolheu outra pasta."""
    raiz = os.path.expanduser(
        ((cfg or {}).get("DIR_CONHECIMENTO") or "~/nexum").strip() or "~/nexum")
    return [os.path.join(raiz, "pessoal", "gravacoes"),
            os.path.expanduser("~/semente-gravacoes")]


_PASTAS_PADRAO = _pastas_padrao()
_TETO_CABECA = 40000       # bytes lidos de cada arquivo pra montar a lista
_TETO_INTEIRO = 4000000    # bytes lidos pra abrir uma gravação
# só barra o que sai da pasta; quem de fato manda é a conferência contra a lista
# (nome com espaço/parêntese é gravação legítima — barrar aqui matava o link dela)
_NOME_RUIM = re.compile(r"[/\\\x00-\x1f]")

_lugar = {"pastas": list(_PASTAS_PADRAO), "bin": os.path.expanduser("~/semente-bin")}
_cache = {}   # caminho -> (assinatura, resumo da gravação)


# ------------------------------------------------------------------ pastas --
def _pastas():
    vistas, saida = set(), []
    for p in (_lugar["pastas"] + _PASTAS_PADRAO):
        try:
            p = os.path.expanduser(str(p))
            if p and p not in vistas and os.path.isdir(p):
                vistas.add(p)
                saida.append(p)
        except Exception:
            continue
    return saida


def _existe_lugar():
    """True se a esteira de gravações existe nesta máquina (pasta ou robô)."""
    try:
        if _pastas():
            return True
        return os.path.isfile(
            os.path.join(_lugar.get("bin") or "", "gravacao_processar.py")) \
            or os.path.isfile(os.path.expanduser("~/semente-bin/gravacao_processar.py"))
    except Exception:
        return False


# ------------------------------------------------------------------ leitura --
_META = re.compile(r"^-\s*\*\*(.+?):\*\*\s*(.*)$")
_FALA = re.compile(r"^\[\s*([0-9:]{1,9})\s*\]\s*(.*)$")
_QUEM = re.compile(r"^([^:,;.!?]{1,40}?):\s*(.*)$")
_MARCO_TRANSCRICAO = re.compile(r"^#{1,3}\s*Transcri", re.I)
_DATA_NOME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_MARCAS = ("data do processamento", "duração", "duracao",
           "arquivo original", "falas transcritas")


def _le(caminho, teto):
    with open(caminho, encoding="utf-8", errors="replace") as f:
        return f.read(teto)


def _le_com_corte(caminho, teto):
    """Lê até o teto e diz se sobrou texto — transcrição cortada em silêncio
    faria a tela mostrar meia gravação como se fosse a gravação inteira."""
    with open(caminho, encoding="utf-8", errors="replace") as f:
        texto = f.read(teto + 1)
    if len(texto) > teto:
        return texto[:teto], True
    return texto, False


def _data_br(iso, caminho=None):
    """AAAA-MM-DD -> DD/MM/AAAA. Cai pro nome do arquivo e depois pra data do arquivo."""
    try:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
        if m:
            return "%s/%s/%s" % (m.group(3), m.group(2), m.group(1)), m.group(0)
    except Exception:
        pass
    try:
        if caminho:
            m = _DATA_NOME.match(os.path.basename(caminho))
            if m:
                return "%s/%s/%s" % (m.group(3), m.group(2), m.group(1)), m.group(0)
            d = datetime.date.fromtimestamp(os.path.getmtime(caminho))
            return d.strftime("%d/%m/%Y"), d.isoformat()
    except Exception:
        pass
    return "", ""


def _duracao_legivel(bruto):
    """'12:34' -> '12 min'. Devolve (curta, exata) sem inventar o que não veio."""
    bruto = (bruto or "").strip()
    if not bruto:
        return "", ""
    try:
        partes = [int(x) for x in bruto.split(":") if x.strip().isdigit()]
        if len(partes) == 3:
            seg = partes[0] * 3600 + partes[1] * 60 + partes[2]
        elif len(partes) == 2:
            seg = partes[0] * 60 + partes[1]
        else:
            return bruto, bruto
        if seg >= 3600:
            curta = "%d h %02d min" % (seg // 3600, (seg % 3600) // 60)
        elif seg >= 60:
            curta = "%d min" % (seg // 60)
        else:
            curta = "%d s" % seg
        return curta, bruto
    except Exception:
        return bruto, bruto


def _separa(texto, caminho):
    """Quebra o arquivo em: título, fichas (dados), ficha escrita e transcrição."""
    linhas = (texto or "").splitlines()
    titulo, dados, ficha, transcricao = "", {}, [], []
    onde = "cabeca"
    for linha in linhas:
        crua = linha.rstrip()
        if onde == "transcricao":
            transcricao.append(crua)
            continue
        if _MARCO_TRANSCRICAO.match(crua.strip()):
            onde = "transcricao"
            continue
        if onde == "cabeca":
            if not titulo and crua.startswith("# "):
                titulo = crua[2:].strip()
                continue
            m = _META.match(crua.strip())
            if m:
                dados[m.group(1).strip().lower()] = m.group(2).strip()
                continue
            if crua.strip().startswith("#"):
                onde = "ficha"
            elif crua.strip():
                onde = "ficha"
            else:
                continue
        if onde == "ficha":
            ficha.append(crua)
    while ficha and not ficha[-1].strip().strip("-"):
        ficha.pop()
    if ficha and ficha[-1].strip() in ("---", "***"):
        ficha.pop()
    if not titulo:
        titulo = os.path.splitext(os.path.basename(caminho))[0]
    titulo = re.sub(r"^[^\wÀ-ÿ(]+", "", titulo).strip() or "Gravação"
    return titulo, dados, "\n".join(ficha).strip(), "\n".join(transcricao).strip()


_ROTULO_QUEM = re.compile(r"^(?:locutor|interlocutor|falante|voz|speaker)\s*\d*$", re.I)


def _parece_nome(texto):
    """'Locutor 2', 'Ana', 'Dr. Paulo' = sim. 'Ele disse' = não (é frase)."""
    if _ROTULO_QUEM.match(texto):
        return True
    palavras = texto.split()
    if not 1 <= len(palavras) <= 3:
        return False
    return all(p[:1].isupper() or p[:1].isdigit() for p in palavras)


def _falas(transcricao):
    """[(tempo, quem, texto)] — linha torta vira parágrafo sem tempo, sem drama."""
    saida = []
    for linha in (transcricao or "").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        m = _FALA.match(linha)
        if m:
            resto = m.group(2).strip()
            mq = _QUEM.match(resto)
            quem = mq.group(1).strip() if mq else ""
            # rótulo de quem fala é curto e parece nome ("Locutor 2", "Ana"):
            # frase com dois-pontos no meio continua frase, não vira nome
            if quem and _parece_nome(quem):
                saida.append((m.group(1), quem, mq.group(2).strip()))
            else:
                saida.append((m.group(1), "", resto))
        else:
            saida.append(("", "", linha))
    return saida


def _resumo_arquivo(caminho):
    """Lê o começo do arquivo e monta o cartão da lista (com cache por arquivo)."""
    try:
        st = os.stat(caminho)
        assinatura = (st.st_mtime, st.st_size)
    except Exception:
        return None
    guardado = _cache.get(caminho)
    if guardado and guardado[0] == assinatura:
        return guardado[1]
    try:
        texto = _le(caminho, _TETO_CABECA)
    except Exception:
        return None
    try:
        titulo, dados, ficha, transcricao = _separa(texto, caminho)
        # arquivo de gravação tem a marca do robô: a transcrição ou os dados dela.
        # (assim um índice ou um bloco de notas na mesma pasta não vira "gravação")
        if not transcricao and not any(k in dados for k in _MARCAS):
            return None
        data_br, data_iso = _data_br(dados.get("data do processamento", ""), caminho)
        curta, exata = _duracao_legivel(dados.get("duração", "") or dados.get("duracao", ""))
        comeco = ""
        for _t, quem, txt in _falas(transcricao):
            pedaco = ("%s: %s" % (quem, txt)) if quem else txt
            comeco = (comeco + " " + pedaco).strip()
            if len(comeco) > 200:
                break
        if not comeco and ficha:
            m = re.search(r"##\s*Resumo\s*\n(.+?)(?:\n##|\Z)", ficha, re.S | re.I)
            if m:
                comeco = re.sub(r"\s+", " ", m.group(1)).strip()
        if len(comeco) > 200:
            comeco = comeco[:200].rsplit(" ", 1)[0] + "…"
        item = {
            "id": os.path.splitext(os.path.basename(caminho))[0],
            "caminho": caminho,
            "titulo": titulo,
            "data_br": data_br,
            "data_iso": data_iso,
            "duracao": curta,
            "duracao_exata": exata,
            "falas": dados.get("falas transcritas", ""),
            "comeco": comeco,
        }
        _cache[caminho] = (assinatura, item)
        if len(_cache) > 400:
            _cache.clear()
        return item
    except Exception:
        return None


def _lista():
    itens, vistos = [], set()
    for pasta in _pastas():
        try:
            nomes = sorted(os.listdir(pasta), reverse=True)
        except Exception:
            continue
        for nome in nomes:
            if not nome.lower().endswith(".md") or nome.startswith("."):
                continue
            ident = os.path.splitext(nome)[0]
            if ident in vistos:
                continue
            caminho = os.path.join(pasta, nome)
            if not os.path.isfile(caminho):
                continue
            item = _resumo_arquivo(caminho)
            if item:
                vistos.add(ident)
                itens.append(item)
    itens.sort(key=lambda i: (i.get("data_iso") or "", i.get("id") or ""), reverse=True)
    return itens


def _nome_seguro(ident):
    ident = str(ident or "")
    if not ident or len(ident) > 200 or _NOME_RUIM.search(ident):
        return False
    return ident.strip(". ") != ""


def _acha(ident):
    if not _nome_seguro(ident):
        return None
    for item in _lista():
        if item["id"] == ident:
            return item
    return None


# ---------------------------------------------------------------- desenho ---
def _e(txt):
    return html.escape(str(txt if txt is not None else ""), quote=True)


def _negrito(txt):
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", txt)


def _texto_rico(md):
    """Converte a ficha (títulos, listas, negrito) em HTML — tudo escapado antes."""
    saida, lista_aberta = [], False
    for linha in _e(md).splitlines():
        crua = linha.strip()
        if not crua or crua in ("---", "***"):
            if lista_aberta:
                saida.append("</ul>")
                lista_aberta = False
            continue
        m = re.match(r"^(#{2,4})\s*(.+)$", crua)
        if m:
            if lista_aberta:
                saida.append("</ul>")
                lista_aberta = False
            saida.append("<h3 class=nx-grv-h>%s</h3>" % _negrito(m.group(2)))
            continue
        m = re.match(r"^[-*]\s+(.+)$", crua)
        if m:
            if not lista_aberta:
                saida.append("<ul class=nx-grv-ul>")
                lista_aberta = True
            saida.append("<li>%s</li>" % _negrito(m.group(1)))
            continue
        if lista_aberta:
            saida.append("</ul>")
            lista_aberta = False
        saida.append("<p>%s</p>" % _negrito(crua))
    if lista_aberta:
        saida.append("</ul>")
    return "".join(saida)


_CSS = """
/* `.lista .item` do estilo da casa é display:flex e ganha de `.nx-grv-item`
   sozinho: sem o `.lista` na frente, título, marcas e resumo ficam lado a lado. */
.lista .nx-grv-item{display:block;text-decoration:none;color:inherit}
.nx-grv-tit{font-weight:600;line-height:1.35}
.nx-grv-pe{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:4px;font-size:.82rem}
.nx-grv-comeco{margin-top:6px;font-size:.88rem;color:var(--fraco);line-height:1.4}
.nx-grv-h{font-size:1rem;margin:14px 0 6px;color:var(--texto)}
.nx-grv-ul{margin:0 0 8px 18px;padding:0}
.nx-grv-ul li{margin:3px 0}
.nx-grv-topo{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.nx-grv-fala{display:flex;gap:8px;align-items:baseline;margin:0 0 10px;line-height:1.5}
.nx-grv-t{flex:0 0 auto;font-size:.75rem;color:var(--fraco);font-variant-numeric:tabular-nums;
          border:1px solid var(--linha);border-radius:6px;padding:1px 5px}
.nx-grv-quem{font-weight:700;margin-right:4px}
.nx-grv-txt mark{background:var(--marca);color:var(--fundo);border-radius:3px;padding:0 2px}
.nx-grv-conta{font-size:.82rem;color:var(--fraco);margin:-4px 0 10px}
"""

_JS_LISTA = """
(function(){
  var busca=document.getElementById('nx-grv-busca');
  var nada=document.getElementById('nx-grv-nada');
  if(!busca){return;}
  busca.addEventListener('input',function(){
    var q=(busca.value||'').trim().toLowerCase();
    var itens=document.querySelectorAll('.nx-grv-item'), vistos=0;
    for(var i=0;i<itens.length;i++){
      var ok=!q||(itens[i].getAttribute('data-txt')||'').indexOf(q)>=0;
      itens[i].style.display=ok?'':'none';
      if(ok){vistos++;}
    }
    if(nada){nada.style.display=(itens.length&&!vistos)?'':'none';}
  });
})();
"""

_JS_UMA = """
(function(){
  var busca=document.getElementById('nx-grv-busca');
  var conta=document.getElementById('nx-grv-conta');
  var falas=document.querySelectorAll('.nx-grv-fala');
  if(!busca||!falas.length){return;}
  var originais=[];
  for(var i=0;i<falas.length;i++){
    var alvo=falas[i].querySelector('.nx-grv-txt');
    originais.push(alvo?alvo.textContent:'');
  }
  function esc(s){return s.replace(/[&<>]/g,function(c){
    return c==='&'?'&amp;':(c==='<'?'&lt;':'&gt;');});}
  function pinta(alvo,orig,q){
    if(!q){alvo.textContent=orig;return;}
    var baixo=orig.toLowerCase(),saida='',i=0,p;
    while((p=baixo.indexOf(q,i))>=0){
      saida+=esc(orig.slice(i,p))+'<mark>'+esc(orig.slice(p,p+q.length))+'</mark>';
      i=p+q.length;
    }
    saida+=esc(orig.slice(i));
    alvo.innerHTML=saida;
  }
  function roda(){
    var q=(busca.value||'').trim().toLowerCase(), achou=0;
    for(var i=0;i<falas.length;i++){
      var orig=originais[i], tem=!q||orig.toLowerCase().indexOf(q)>=0;
      falas[i].style.display=tem?'':'none';
      var alvo=falas[i].querySelector('.nx-grv-txt');
      if(alvo){pinta(alvo,orig,tem?q:'');}
      if(tem&&q){achou++;}
    }
    if(conta){
      conta.textContent=q?(achou?(achou+' trecho(s) com essa palavra'):
        'Nenhum trecho com essa palavra nesta gravação'):'';
    }
  }
  busca.addEventListener('input',roda);
})();
"""


def disponivel(cfg):
    """A tela existe se o módulo de gravações foi instalado nesta máquina."""
    try:
        valor = str((cfg or {}).get("GRAVACOES_ATIVO", "")).strip().lower()
        if valor in ("sim", "s", "1", "true", "yes"):
            return True
        if valor in ("nao", "não", "n", "0", "false", "no"):
            return False
        _lugar["pastas"] = _pastas_padrao(cfg)
        pasta = str((cfg or {}).get("DIR_BIN") or "").strip()
        if pasta:
            _lugar["bin"] = os.path.expanduser(pasta)
        return _existe_lugar()
    except Exception:
        return False


def registra(app, casca, exige_login):
    try:
        pastas = []
        conhecimento = getattr(casca, "DIR_CONHECIMENTO", None)
        if conhecimento:
            pastas.append(os.path.join(os.path.expanduser(str(conhecimento)),
                                       "pessoal", "gravacoes"))
        dados = getattr(casca, "DIR_DADOS", None)
        if dados:
            pastas.append(os.path.join(os.path.expanduser(str(dados)), "gravacoes"))
        if pastas:
            _lugar["pastas"] = pastas + _PASTAS_PADRAO
        pasta_bin = getattr(casca, "DIR_BIN", None)
        if pasta_bin:
            _lugar["bin"] = os.path.expanduser(str(pasta_bin))
    except Exception:
        pass

    @app.get("/gravacoes")
    def tela_gravacoes():
        exige_login()
        try:
            itens = _lista()
        except Exception:
            itens = []
        try:
            if not itens:
                corpo = (
                    "<div class=cartao><h2>Gravações</h2>"
                    "<div class=vazio>Nenhuma gravação transcrita até agora — "
                    "o robô ainda não rodou nenhuma vez.<br>"
                    "É só deixar um áudio na pasta de entrada das gravações: "
                    "em poucos minutos ele aparece aqui, com o texto inteiro.</div></div>")
            else:
                cartoes = []
                for it in itens:
                    marcas = []
                    if it["data_br"]:
                        marcas.append("<span class=chip>%s</span>" % _e(it["data_br"]))
                    if it["duracao"]:
                        marcas.append("<span class=chip>%s</span>" % _e(it["duracao"]))
                    if it["falas"]:
                        marcas.append("<span class=fraco>%s falas</span>" % _e(it["falas"]))
                    busca = _e((it["titulo"] + " " + it["comeco"] + " " +
                                it["data_br"]).lower())
                    cartoes.append(
                        "<a class='item nx-grv-item' data-txt='%s' href='/gravacoes/%s'>"
                        "<div class=nx-grv-tit>%s</div>"
                        "<div class=nx-grv-pe>%s</div>"
                        "%s</a>" % (
                            busca, _e(urllib.parse.quote(it["id"], safe="")),
                            _e(it["titulo"]), "".join(marcas),
                            ("<div class=nx-grv-comeco>%s</div>" % _e(it["comeco"]))
                            if it["comeco"] else ""))
                corpo = (
                    "<div class=cartao>"
                    "<h2 style='margin-top:0'>Gravações</h2>"
                    "<p class=fraco>Tudo que já foi transcrito. Toque em uma para ler o "
                    "texto inteiro. O áudio original fica guardado na máquina e não é "
                    "aberto por aqui.</p>"
                    "<div class=kpis><div class=kpi><b>%d</b><span>gravações</span></div></div>"
                    "<div class=nx-grv-topo>"
                    "<input class=campo id=nx-grv-busca type=search "
                    "placeholder='Procurar pelo nome ou pelo começo…' autocomplete=off>"
                    "</div>"
                    "<div class=lista>%s</div>"
                    "<div class=vazio id=nx-grv-nada style='display:none'>"
                    "Nenhuma gravação com essa palavra.</div>"
                    "</div>" % (len(itens), "".join(cartoes)))
        except Exception:
            corpo = ("<div class=cartao><div class=vazio>Não consegui montar a lista de "
                     "gravações agora. Nada foi perdido — tente abrir de novo.</div></div>")
        return Response(casca.shell(TITULO, corpo, "/gravacoes", css=_CSS, js=_JS_LISTA),
                        mimetype="text/html")

    @app.get("/gravacoes/<ident>")
    def tela_gravacoes_uma(ident):
        exige_login()
        item = None
        try:
            item = _acha(ident)
        except Exception:
            item = None
        if not item:
            corpo = ("<div class=cartao><h2>Gravação não encontrada</h2>"
                     "<div class=vazio>Essa gravação não está mais aqui (ou nunca esteve). "
                     "Nada foi apagado por esta tela.</div>"
                     "<p><a class=btn href='/gravacoes'>Voltar para a lista</a></p></div>")
            return Response(casca.shell(TITULO, corpo, "/gravacoes", css=_CSS),
                            mimetype="text/html")
        try:
            texto, cortado = _le_com_corte(item["caminho"], _TETO_INTEIRO)
            titulo, dados, ficha, transcricao = _separa(texto, item["caminho"])
            falas = _falas(transcricao)

            marcas = []
            if item["data_br"]:
                marcas.append("<div class=kpi><b>%s</b><span>data</span></div>"
                              % _e(item["data_br"]))
            if item["duracao"]:
                marcas.append("<div class=kpi><b>%s</b><span>duração</span></div>"
                              % _e(item["duracao"]))
            if falas:
                marcas.append("<div class=kpi><b>%d</b><span>falas</span></div>" % len(falas))

            corpo_ficha = _texto_rico(ficha) if ficha else (
                "<div class=vazio>Esta gravação ainda não tem ficha escrita — "
                "só a transcrição, logo abaixo.</div>")

            linhas = []
            for tempo, quem, txt in falas:
                linhas.append(
                    "<p class=nx-grv-fala>%s<span>%s<span class=nx-grv-txt>%s</span></span></p>"
                    % (("<span class=nx-grv-t>%s</span>" % _e(tempo)) if tempo else "",
                       ("<span class=nx-grv-quem>%s</span>" % _e(quem)) if quem else "",
                       _e(txt)))
            corpo_transcricao = "".join(linhas) if linhas else (
                "<div class=vazio>A transcrição desta gravação está vazia.</div>")
            if cortado:
                corpo_transcricao = (
                    "<div class='aviso atencao'>Esta gravação é grande demais para "
                    "caber na tela inteira — abaixo está o começo dela. O texto "
                    "completo continua guardado na máquina.</div>" + corpo_transcricao)

            corpo = (
                "<div class=cartao>"
                "<div class=nx-grv-topo>"
                "<a class=btn href='/gravacoes'>← Voltar</a>"
                "<span class=fraco>%s</span></div>"
                "<h2 style='margin:0 0 8px'>%s</h2>"
                "<div class=kpis>%s</div>"
                "%s"
                "</div>"
                "<div class=cartao>"
                "<h2 style='margin-top:0'>Transcrição</h2>"
                "<p class=fraco>Só o texto: o áudio original não é aberto por esta tela.</p>"
                "<div class=nx-grv-topo>"
                "<input class=campo id=nx-grv-busca type=search "
                "placeholder='Procurar uma palavra nesta gravação…' autocomplete=off>"
                "</div>"
                "<div class=nx-grv-conta id=nx-grv-conta></div>"
                "%s</div>" % (
                    _e(item["data_br"]), _e(titulo), "".join(marcas),
                    corpo_ficha, corpo_transcricao))
        except Exception:
            corpo = ("<div class=cartao><h2>Gravação</h2>"
                     "<div class=vazio>Não consegui ler o texto desta gravação agora. "
                     "O arquivo continua guardado na máquina, intacto.</div>"
                     "<p><a class=btn href='/gravacoes'>Voltar para a lista</a></p></div>")
        return Response(casca.shell(TITULO, corpo, "/gravacoes", css=_CSS, js=_JS_UMA),
                        mimetype="text/html")
