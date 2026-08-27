#!/usr/bin/env python3
"""
Tela "E-mails" — a caixa de entrada do dono, SÓ LEITURA.

Ela não fala com o Google direto: chama a ferramenta que o módulo Gmail já
instalou (`~/semente-bin/gmail.py`) como um programa à parte, com prazo pra
responder, e lê o texto que ele devolve. Toda a lógica de credencial, token e
API mora lá — aqui só se mostra.

O que esta tela NÃO faz (de propósito, é o way of life da casa):
não envia, não responde, não arquiva, não marca como lido e não apaga nada.
Enviar e-mail é do assistente, no chat, e só com o OK do dono.

Comandos usados (interface pública do módulo):
    gmail.py buscar "in:inbox" N      → os mais recentes da caixa de entrada
    gmail.py nao-lidos N              → só os não lidos
    gmail.py buscar "<termo>" N       → a busca que a pessoa digitou
    gmail.py ler <id>                 → cabeçalhos + corpo em texto
"""

import os
import re
import sys
import html
import subprocess
from email.header import decode_header, make_header
from email.utils import parseaddr

from flask import Response, request, jsonify

CHAVE  = "emails"
TITULO = "E-mails"
ICONE  = "envelope"
GRUPO  = "principal"
ORDEM  = 20

MAX_LISTA     = 25      # quantos e-mails a lista pede de cada vez
TIMEOUT_LISTA = 75      # segundos pra montar a lista
TIMEOUT_MSG   = 45      # segundos pra abrir um e-mail
MAX_CORPO     = 20000   # caracteres de corpo mostrados na tela
MAX_BRUTO     = 400000  # teto do texto cru antes de virar legível


# ----------------------------------------------------------------- a ferramenta

def _dir_bin(casca=None, cfg=None):
    """A pasta onde o kit instala os scripts. Cai no padrão se não souber.

    A função da casca vem primeiro (ela lê o config na hora); a constante é o
    valor congelado no boot. Quem escolheu outra pasta continua sendo achado."""
    candidatos = []
    fresca = getattr(casca, "dir_bin", None)
    if callable(fresca):
        try:
            candidatos.append(fresca())
        except Exception:
            pass
    candidatos += [getattr(casca, "DIR_BIN", None),
                   (cfg or {}).get("DIR_BIN"),
                   os.environ.get("SEMENTE_BIN"),
                   "~/semente-bin"]
    for candidato in candidatos:
        if candidato:
            try:
                return os.path.expanduser(str(candidato))
            except Exception:
                continue
    return os.path.expanduser("~/semente-bin")


def _script(casca=None, cfg=None):
    return os.path.join(_dir_bin(casca, cfg), "gmail.py")


def disponivel(cfg):
    """A tela só existe se o módulo do Gmail foi instalado nesta máquina."""
    try:
        if str((cfg or {}).get("GMAIL_ATIVO", "")).strip().strip('"').lower() == "sim":
            return True
        return os.path.exists(_script(None, cfg))
    except Exception:
        return False


def _recado_do_erro(bruto):
    """Traduz a reclamação técnica da ferramenta pra uma frase de gente."""
    t = (bruto or "").lower()
    if "sem autorização" in t or "sem autorizacao" in t or "auth-url" in t:
        return ("O acesso à sua conta do Google ainda não foi autorizado nesta máquina. "
                "Me peça no chat pra refazer a autorização — leva um minuto.")
    if "credencial não encontrada" in t or "credencial nao encontrada" in t:
        return ("Falta a autorização do Google aqui na máquina. "
                "Me peça no chat pra ligar o e-mail de novo.")
    if "invalid_grant" in t or "invalid_client" in t or "erro oauth" in t:
        return ("A autorização do Google venceu e precisa ser refeita. "
                "Me peça isso no chat que eu resolvo.")
    if "accessnotconfigured" in t:
        return ("O acesso ao e-mail não está liberado na sua conta do Google. "
                "Me peça no chat pra conferir isso.")
    if "erro api 401" in t or "erro api 403" in t:
        return ("O Google recusou o acesso agora. Se continuar, me peça no chat "
                "pra refazer a autorização.")
    if "erro api 429" in t or "ratelimit" in t or "erro api 5" in t:
        return ("O Google pediu pra esperar um pouco antes de responder de novo. "
                "Tente daqui a alguns minutos.")
    return ("Não consegui falar com o Google agora. Tente de novo em instantes — "
            "se insistir, me avise no chat.")


def _roda(args, timeout, casca=None):
    """Roda a ferramenta. Devolve (ok, saída, recado_pra_pessoa)."""
    script = _script(casca)
    try:
        if not os.path.exists(script):
            return False, "", ("A ferramenta de e-mail ainda não está instalada nesta "
                               "máquina. Me peça no chat pra ligar o e-mail.")
    except Exception:
        return False, "", "Não consegui abrir a ferramenta de e-mail agora."

    python = sys.executable or "python3"
    try:
        p = subprocess.run([python, script] + [str(a) for a in args],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "", ("O Google está demorando demais pra responder. "
                           "Tente de novo daqui a pouco.")
    except Exception:
        return False, "", "Não consegui abrir a ferramenta de e-mail agora."

    saida = p.stdout or ""
    if p.returncode != 0:
        return False, saida, _recado_do_erro(saida + " " + (p.stderr or ""))
    return True, saida, ""


# ------------------------------------------------------------------- limpezinha

_MESES = {"jan": 1, "feb": 2, "fev": 2, "mar": 3, "apr": 4, "abr": 4, "may": 5,
          "mai": 5, "jun": 6, "jul": 7, "aug": 8, "ago": 8, "sep": 9, "set": 9,
          "oct": 10, "out": 10, "nov": 11, "dec": 12, "dez": 12}


def _limpa(txt):
    """Tira caracteres de controle e espaço sobrando."""
    txt = "".join(c for c in (txt or "") if c == "\n" or c == "\t" or ord(c) >= 32)
    return txt.strip()


def _remenda_pedaco(pedaco):
    """Pedaço codificado que veio cortado no meio: salva o que dá, sem inventar.

    A ferramenta corta o cabeçalho no tamanho, então o último trecho pode vir
    sem o fecho (`?=`). Aqui a gente aproveita a parte legível e marca o corte
    com reticências — melhor do que mostrar '=?UTF-8?B?...' na tela."""
    m = re.match(r"^=\?([^?]+)\?([BbQq])\?(.*)$", pedaco)
    if not m:
        return ""
    charset, tipo, dado = m.group(1), m.group(2).upper(), m.group(3)
    try:
        if tipo == "B":
            import base64
            dado = dado[:len(dado) // 4 * 4]
            if not dado:
                return ""
            bruto = base64.b64decode(dado)
        else:
            import quopri
            bruto = quopri.decodestring(dado.replace("_", " ").encode())
        texto = bruto.decode(charset, "ignore")
    except Exception:
        return ""
    texto = texto.strip()
    return (texto + "…") if texto else ""


def _decodifica(txt):
    """Cabeçalho de e-mail vem codificado (=?UTF-8?B?...?=). Devolve legível."""
    s = _limpa(txt)
    if not s:
        return ""
    try:
        if "=?" in s:
            corte = s.rfind("=?")
            if "?=" not in s[corte:]:
                s = (s[:corte].strip() + " " + _remenda_pedaco(s[corte:])).strip()
    except Exception:
        pass
    if not s:
        return ""
    try:
        s = str(make_header(decode_header(s)))
    except Exception:
        pass
    return _limpa(s)


def _data_bonita(bruto):
    """'Wed, 27 Aug 2026 10:12' → '27/08/2026 10:12'. Não inventa nada."""
    b = _limpa(bruto)
    if not b:
        return ""
    try:
        m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{4})"
                      r"(?:\s+(\d{1,2}):(\d{2}))?", b)
        if m:
            dia, mes, ano = int(m.group(1)), _MESES.get(m.group(2).lower()), int(m.group(3))
            if mes and 1 <= dia <= 31:
                saida = "%02d/%02d/%04d" % (dia, mes, ano)
                if m.group(4):
                    saida += " %02d:%s" % (int(m.group(4)), m.group(5))
                return saida
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})", b)
        if m:
            return "%s/%s/%s %s:%s" % (m.group(3), m.group(2), m.group(1),
                                       m.group(4), m.group(5))
    except Exception:
        pass
    return ""


def _remetente(bruto):
    """'Fulano <a@b.com>' → ('Fulano', 'a@b.com'). Aguenta vir cortado."""
    b = _limpa(bruto)
    nome, endereco = "", ""
    try:
        nome, endereco = parseaddr(b)
    except Exception:
        pass
    nome = _decodifica(nome)
    endereco = _limpa(endereco)
    if "@" not in endereco:          # sem arroba não é endereço, é texto cortado
        endereco = ""
    if not endereco:
        m = re.search(r"[^\s<>,;\"]+@[^\s<>,;\"]+", b)
        endereco = m.group(0) if m else ""
    if not nome:
        nome = _decodifica(b.split("<")[0]) or endereco.split("@")[0] or b
    nome = nome.strip(' "\'')
    return nome[:80], endereco[:120]


def _itens_da_lista(saida):
    """Lê a saída de `gmail.py buscar` / `nao-lidos`.

    Cada linha vem assim:  ● <id> | <data> | <de> | <assunto>
    (o ● é 'não lido'; o assunto pode conter '|', por isso o corte é limitado)."""
    itens = []
    for linha in (saida or "").splitlines():
        linha = linha.rstrip("\r\n")
        crua = linha.strip()
        if not crua or crua.startswith("("):
            continue
        # E-mail SEM assunto termina a linha em " |": sem o espaço final o corte
        # não acha o 4º pedaço e o e-mail sumiria da lista, calado. O espaço a
        # mais some no _decodifica() de qualquer jeito.
        partes = (linha + " ").split(" | ", 3)
        if len(partes) < 4:
            continue
        cabeca = partes[0]
        nao_lido = "●" in cabeca
        ident = cabeca.replace("●", "").strip()
        if not re.fullmatch(r"[0-9A-Za-z_-]{1,80}", ident):
            continue
        nome, endereco = _remetente(partes[2])
        assunto = _decodifica(partes[3]) or "(sem assunto)"
        itens.append({
            "id": ident,
            "de": nome or "(remetente desconhecido)",
            "email": endereco,
            "assunto": assunto[:160],
            "quando": _data_bonita(partes[1]),
            "naolido": nao_lido,
        })
    return itens


def _html_pra_texto(bruto):
    """Corpo que só veio em HTML: vira texto legível (nada é executado)."""
    t = bruto or ""
    try:
        t = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", t)
        t = re.sub(r"(?i)<br\s*/?>", "\n", t)
        t = re.sub(r"(?i)<li[^>]*>", "\n• ", t)
        t = re.sub(r"(?i)</(p|div|tr|li|h[1-6]|table|ul|ol)>", "\n", t)
        t = re.sub(r"(?s)<[^>]+>", " ", t)
        t = html.unescape(t)
        t = t.replace("\xa0", " ")
        t = re.sub(r"[ \t]+", " ", t)
        t = "\n".join(l.strip() for l in t.splitlines())
        t = re.sub(r"\n{3,}", "\n\n", t)
    except Exception:
        return bruto or ""
    return t.strip()


def _parece_html(txt):
    try:
        return len(re.findall(r"(?i)<(html|body|div|table|p|br|span|img|a)\b", txt)) >= 3
    except Exception:
        return False


def _mensagem_lida(saida):
    """Lê a saída de `gmail.py ler <id>`: cabeçalhos, linha de traços, corpo."""
    linhas = (saida or "").splitlines()
    cab, corpo_de = {}, None
    for i, l in enumerate(linhas):
        s = l.strip()
        if s and set(s) == {"-"}:
            corpo_de = i + 1
            break
        m = re.match(r"^(Date|From|To|Cc|Subject|Anexos):\s*(.*)$", l)
        if m:
            cab[m.group(1)] = m.group(2)
    corpo = "\n".join(linhas[corpo_de:]) if corpo_de is not None else "\n".join(linhas)

    # e-mail de propaganda vem com megabytes de HTML: corta ANTES de virar texto,
    # senão a tela fica mastigando o que ela nem vai mostrar.
    bruto_grande = len(corpo) > MAX_BRUTO
    if bruto_grande:
        corpo = corpo[:MAX_BRUTO]

    so_html = False
    primeira = corpo.lstrip().split("\n", 1)[0] if corpo.strip() else ""
    if primeira.startswith("(corpo só em HTML"):
        so_html = True
        corpo = corpo.lstrip()[len(primeira):]
    if so_html or _parece_html(corpo):
        corpo = _html_pra_texto(corpo)

    corpo = "".join(c for c in corpo if c in "\n\t" or ord(c) >= 32).strip()
    cortado = bruto_grande or len(corpo) > MAX_CORPO
    if len(corpo) > MAX_CORPO:
        corpo = corpo[:MAX_CORPO]

    nome, endereco = _remetente(cab.get("From", ""))
    anexos = [a.strip() for a in (cab.get("Anexos", "") or "").split(",") if a.strip()]
    return {
        "de": nome or "(remetente desconhecido)",
        "email": endereco,
        "para": _decodifica(cab.get("To", ""))[:200],
        "copia": _decodifica(cab.get("Cc", ""))[:200],
        "assunto": _decodifica(cab.get("Subject", "")) or "(sem assunto)",
        "quando": _data_bonita(cab.get("Date", "")),
        "anexos": [_decodifica(a)[:80] for a in anexos][:12],
        "corpo": corpo or "(este e-mail não tem texto — só imagem ou anexo)",
        "cortado": cortado,
    }


# ------------------------------------------------------------------------ tela

CSS = """
.em-barra{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.em-barra .btn{flex:0 0 auto}
.em-busca{display:flex;gap:8px;width:100%}
.em-busca .campo{flex:1 1 auto;min-width:0}
.lista .em-item{display:flex;gap:10px;align-items:flex-start;text-decoration:none}
.em-ponto{flex:0 0 8px;width:8px;height:8px;border-radius:50%;background:var(--marca);
          margin-top:7px}
.em-ponto.em-off{background:transparent}
.em-txt{flex:1 1 auto;min-width:0}
.em-l1{display:flex;gap:8px;align-items:baseline;justify-content:space-between}
.em-de{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.em-quando{flex:0 0 auto;color:var(--fraco);font-size:.75rem;white-space:nowrap}
.em-assunto{color:var(--fraco);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
            margin-top:2px}
.em-forte .em-assunto{color:var(--texto)}
.em-cab{display:flex;gap:10px;align-items:flex-start;justify-content:space-between;
        flex-wrap:wrap;margin-bottom:6px}
.em-titulo{font-size:1.05rem;font-weight:700;line-height:1.35;margin:0}
.em-meta{color:var(--fraco);font-size:.85rem;margin:2px 0 0;word-break:break-word}
.em-corpo{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6;margin-top:12px;
          padding-top:12px;border-top:1px solid var(--linha)}
.em-rodape{margin-top:14px}
"""

JS = """
(function(){
  var estado = {filtro:'todos', busca:'', carregando:false};

  function id(x){ return document.getElementById(x); }
  function novo(tag, cls, txt){
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt !== undefined && txt !== null) e.textContent = txt;
    return e;
  }
  function limpa(el){ while (el && el.firstChild) el.removeChild(el.firstChild); }

  function mostraAviso(msg){
    var caixa = id('em-aviso');
    limpa(caixa);
    if (!msg) return;
    var faixa = novo('div', 'aviso atencao');
    faixa.appendChild(novo('span', null, msg));
    var b = novo('button', 'btn', 'Tentar de novo');
    b.style.marginLeft = '10px';
    b.onclick = function(){ carrega(); };
    faixa.appendChild(b);
    caixa.appendChild(faixa);
  }

  function kpis(dados){
    var caixa = id('em-kpis');
    limpa(caixa);
    var n = dados.nao_lidos, rotulo;
    if (estado.busca) rotulo = 'não lidos no resultado';
    else if (estado.filtro === 'naolidos') rotulo = 'não lidos na caixa de entrada';
    else rotulo = 'não lidos entre os recentes';
    var cheio = dados.cheio && estado.filtro === 'naolidos' && !estado.busca;
    var k1 = novo('div', 'kpi');
    k1.appendChild(novo('b', null, String(n) + (cheio ? '+' : '')));
    k1.appendChild(novo('span', null, rotulo));
    var k2 = novo('div', 'kpi');
    k2.appendChild(novo('b', null, String(dados.itens.length)));
    k2.appendChild(novo('span', null, dados.itens.length === 1 ? 'e-mail na lista' : 'e-mails na lista'));
    caixa.appendChild(k1);
    caixa.appendChild(k2);
  }

  function desenhaLista(itens){
    var caixa = id('em-lista');
    limpa(caixa);
    if (!itens.length){
      var v = novo('div', 'vazio');
      if (estado.busca) v.textContent = 'Nenhum e-mail encontrado pra "' + estado.busca + '".';
      else if (estado.filtro === 'naolidos') v.textContent = 'Nenhum e-mail não lido. Caixa de entrada em dia.';
      else v.textContent = 'Nenhum e-mail na caixa de entrada.';
      caixa.appendChild(v);
      return;
    }
    var lista = novo('div', 'lista');
    itens.forEach(function(m){
      var a = novo('a', 'item em-item' + (m.naolido ? ' em-forte' : ''));
      a.href = '#' + m.id;
      var ponto = novo('span', 'em-ponto' + (m.naolido ? '' : ' em-off'));
      var txt = novo('div', 'em-txt');
      var l1 = novo('div', 'em-l1');
      l1.appendChild(novo('span', 'em-de', m.de));
      l1.appendChild(novo('span', 'em-quando', m.quando || 'sem data'));
      txt.appendChild(l1);
      txt.appendChild(novo('div', 'em-assunto', m.assunto));
      a.appendChild(ponto);
      a.appendChild(txt);
      lista.appendChild(a);
    });
    caixa.appendChild(lista);
  }

  function carregando(msg){
    var caixa = id('em-lista');
    limpa(caixa);
    caixa.appendChild(novo('div', 'vazio', msg));
  }

  function carrega(){
    if (estado.carregando) return;
    estado.carregando = true;
    mostraAviso('');
    carregando('Buscando na sua conta… isso leva alguns segundos.');
    var url = '/api/emails/lista?filtro=' + encodeURIComponent(estado.filtro) +
              '&busca=' + encodeURIComponent(estado.busca);
    fetch(url, {headers:{'Accept':'application/json'}})
      .then(function(r){ return r.json(); })
      .then(function(d){
        estado.carregando = false;
        if (!d || !d.ok){
          limpa(id('em-kpis'));
          carregando('Sem lista pra mostrar agora.');
          mostraAviso((d && d.recado) || 'Não consegui falar com o Google agora.');
          return;
        }
        kpis(d);
        desenhaLista(d.itens);
      })
      .catch(function(){
        estado.carregando = false;
        carregando('Sem lista pra mostrar agora.');
        mostraAviso('A página não conseguiu falar com a máquina. Verifique a conexão e tente de novo.');
      });
  }

  function fechaLeitura(){
    id('em-leitura').style.display = 'none';
    id('em-painel').style.display = '';
    if (location.hash) history.replaceState(null, '', location.pathname);
  }

  function abre(msgId){
    var caixa = id('em-leitura');
    id('em-painel').style.display = 'none';
    caixa.style.display = '';
    limpa(caixa);
    var voltar = novo('button', 'btn', '← Voltar pra lista');
    voltar.onclick = fechaLeitura;
    caixa.appendChild(voltar);
    var corpo = novo('div', 'vazio', 'Abrindo o e-mail…');
    caixa.appendChild(corpo);
    window.scrollTo(0, 0);

    fetch('/api/emails/mensagem?id=' + encodeURIComponent(msgId), {headers:{'Accept':'application/json'}})
      .then(function(r){ return r.json(); })
      .then(function(d){
        limpa(caixa);
        caixa.appendChild(voltar);
        if (!d || !d.ok){
          var faixa = novo('div', 'aviso atencao', (d && d.recado) || 'Não consegui abrir este e-mail agora.');
          faixa.style.marginTop = '12px';
          caixa.appendChild(faixa);
          return;
        }
        var cab = novo('div', 'em-cab');
        cab.style.marginTop = '14px';
        var esq = novo('div');
        esq.style.minWidth = '0';
        esq.appendChild(novo('h2', 'em-titulo', d.assunto));
        var quem = d.de + ((d.email && d.email !== d.de) ? ' · ' + d.email : '');
        esq.appendChild(novo('p', 'em-meta', quem));
        if (d.para) esq.appendChild(novo('p', 'em-meta', 'Para: ' + d.para));
        if (d.copia) esq.appendChild(novo('p', 'em-meta', 'Cópia: ' + d.copia));
        cab.appendChild(esq);
        if (d.quando) cab.appendChild(novo('span', 'chip', d.quando));
        caixa.appendChild(cab);
        if (d.anexos && d.anexos.length){
          var an = novo('p', 'em-meta', 'Anexos: ' + d.anexos.join(', ') +
                        ' — os arquivos ficam no seu Gmail.');
          caixa.appendChild(an);
        }
        caixa.appendChild(novo('div', 'em-corpo', d.corpo));
        if (d.cortado){
          caixa.appendChild(novo('p', 'fraco',
            'Este e-mail é longo e foi cortado aqui. O texto inteiro está no seu Gmail.'));
        }
      })
      .catch(function(){
        limpa(caixa);
        caixa.appendChild(voltar);
        var f = novo('div', 'aviso atencao', 'A página não conseguiu falar com a máquina.');
        f.style.marginTop = '12px';
        caixa.appendChild(f);
      });
  }

  function pelaHash(){
    var h = (location.hash || '').replace('#', '');
    if (h && /^[0-9A-Za-z_-]{1,80}$/.test(h)) abre(h);
    else fechaLeitura();
  }

  function ligaBotoes(){
    var bt = document.querySelectorAll('[data-filtro]');
    for (var i = 0; i < bt.length; i++){
      (function(b){
        b.onclick = function(){
          estado.filtro = b.getAttribute('data-filtro');
          estado.busca = '';
          var cx = id('em-campo-busca'); if (cx) cx.value = '';
          for (var j = 0; j < bt.length; j++)
            bt[j].className = (bt[j] === b) ? 'btn primario' : 'btn';
          carrega();
        };
      })(bt[i]);
    }
    var form = id('em-form-busca');
    if (form) form.onsubmit = function(ev){
      ev.preventDefault();
      estado.busca = (id('em-campo-busca').value || '').trim();
      carrega();
    };
    var lim = id('em-limpar');
    if (lim) lim.onclick = function(){
      id('em-campo-busca').value = '';
      estado.busca = '';
      carrega();
    };
  }

  window.addEventListener('hashchange', pelaHash);
  ligaBotoes();
  carrega();
  pelaHash();
})();
"""


def _pagina():
    return """
<div class=cartao>
  <div class=kpis id=em-kpis>
    <div class=kpi><b>—</b><span>não lidos</span></div>
  </div>
  <div class=em-barra style="margin-top:12px">
    <button class="btn primario" data-filtro="todos">Recentes</button>
    <button class="btn" data-filtro="naolidos">Não lidos</button>
  </div>
  <form class=em-busca id=em-form-busca>
    <input class=campo id=em-campo-busca type=search
           placeholder="Procurar por remetente, palavra…" maxlength=120>
    <button class=btn type=submit>Procurar</button>
    <button class=btn type=button id=em-limpar>Limpar</button>
  </form>
</div>

<div id=em-aviso></div>

<div id=em-painel>
  <div class=cartao id=em-lista>
    <div class=vazio>Buscando na sua conta…</div>
  </div>
  <p class="fraco em-rodape">Esta tela é só leitura: aqui eu não envio, não respondo,
  não arquivo e não apago nada. Pra escrever um e-mail, me chame no chat — e ele só sai
  com o seu OK.</p>
</div>

<div class=cartao id=em-leitura style="display:none"></div>
"""


def registra(app, casca, exige_login):
    @app.get("/emails")
    def tela_emails():
        exige_login()
        # sem remendo de "e se o shell não aceitar css/js": a tela sem o js é uma
        # página que carrega pra sempre — parece viva e está morta.
        pagina = casca.shell(TITULO, _pagina(), "/emails", css=CSS, js=JS)
        return Response(pagina, mimetype="text/html")

    @app.get("/api/emails/lista")
    def api_emails_lista():
        exige_login()
        try:
            filtro = (request.args.get("filtro") or "todos").strip().lower()
            busca = _limpa((request.args.get("busca") or "").replace("\n", " "))[:120]

            if busca:
                # busca começando por "-" seria lida como opção pela ferramenta e
                # a pessoa levaria um "erro do Google" que nunca existiu.
                args = ["buscar", (" " + busca) if busca.startswith("-") else busca,
                        MAX_LISTA]
            elif filtro == "naolidos":
                args = ["nao-lidos", MAX_LISTA]
            else:
                args = ["buscar", "in:inbox", MAX_LISTA]

            ok, saida, recado = _roda(args, TIMEOUT_LISTA, casca)
            if not ok:
                return jsonify({"ok": False, "recado": recado})

            itens = _itens_da_lista(saida)
            uteis = [l for l in (saida or "").splitlines()
                     if l.strip() and not l.strip().startswith("(")]
            if uteis and not itens:
                # veio resposta e nenhuma linha virou e-mail: isso é defeito meu,
                # não caixa vazia. Dizer "nenhum e-mail" aqui seria mentira.
                return jsonify({"ok": False,
                                "recado": "O Google respondeu, mas eu não entendi a "
                                          "lista que veio. Me avise no chat que eu "
                                          "conserto."})
            return jsonify({
                "ok": True,
                "itens": itens,
                "nao_lidos": sum(1 for i in itens if i["naolido"]),
                "cheio": len(itens) >= MAX_LISTA,
            })
        except Exception:
            return jsonify({"ok": False,
                            "recado": "Deu um problema aqui na máquina ao montar a lista. "
                                      "Tente de novo; se insistir, me avise no chat."})

    @app.get("/api/emails/mensagem")
    def api_emails_mensagem():
        exige_login()
        try:
            ident = _limpa(request.args.get("id") or "")
            if not re.fullmatch(r"[0-9A-Za-z_-]{1,80}", ident):
                return jsonify({"ok": False,
                                "recado": "Este e-mail não foi encontrado."})
            ok, saida, recado = _roda(["ler", ident], TIMEOUT_MSG, casca)
            if not ok:
                return jsonify({"ok": False, "recado": recado})
            dados = _mensagem_lida(saida)
            dados["ok"] = True
            return jsonify(dados)
        except Exception:
            return jsonify({"ok": False,
                            "recado": "Deu um problema aqui na máquina ao abrir o e-mail."})
