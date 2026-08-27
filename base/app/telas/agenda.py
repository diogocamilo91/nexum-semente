#!/usr/bin/env python3
"""
Tela "Agenda" — os compromissos do dono, SÓ LEITURA.

Ela não fala com o Google direto: chama a ferramenta que o módulo Agenda já
instalou (`~/semente-bin/agenda.py`) como um programa à parte, com prazo pra
responder, e lê o texto que ele devolve.

O acesso é de leitura por desenho (a autorização dada ao Google é "ver
eventos"): esta tela não marca, não muda e não apaga compromisso nenhum.

Comandos usados (interface pública do módulo):
    agenda.py hoje          → os compromissos de hoje
    agenda.py proximos 7    → os 7 dias seguintes (não inclui hoje)

Formato que a ferramenta devolve:
    Quarta 27/08
      09:00–10:00  Reunião  [Trabalho] @ Sala 3
      dia todo  Feriado
      (sem compromissos)
"""

import os
import re
import sys
import datetime
import subprocess

from flask import Response, jsonify

CHAVE  = "agenda"
TITULO = "Agenda"
ICONE  = "calendario"
GRUPO  = "principal"
ORDEM  = 25

DIAS_ADIANTE   = 7
TIMEOUT_HOJE   = 45     # segundos
TIMEOUT_FRENTE = 75     # segundos

DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
               "Sexta-feira", "Sábado", "Domingo"]


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
    return os.path.join(_dir_bin(casca, cfg), "agenda.py")


def disponivel(cfg):
    """A tela só existe se o módulo da agenda foi instalado nesta máquina."""
    try:
        if str((cfg or {}).get("AGENDA_ATIVO", "")).strip().strip('"').lower() == "sim":
            return True
        return os.path.exists(_script(None, cfg))
    except Exception:
        return False


def _recado_do_erro(bruto):
    """Traduz a reclamação técnica da ferramenta pra uma frase de gente."""
    t = (bruto or "").lower()
    if "sem autorização" in t or "sem autorizacao" in t or "auth-url" in t:
        return ("O acesso à sua agenda do Google ainda não foi autorizado nesta "
                "máquina. Me peça no chat pra refazer a autorização.")
    if "credencial não encontrada" in t or "credencial nao encontrada" in t:
        return ("Falta a autorização do Google aqui na máquina. "
                "Me peça no chat pra ligar a agenda de novo.")
    if "invalid_grant" in t or "invalid_client" in t or "erro oauth" in t:
        return ("A autorização do Google venceu e precisa ser refeita. "
                "Me peça isso no chat que eu resolvo.")
    if "accessnotconfigured" in t:
        return ("O acesso à agenda não está liberado na sua conta do Google. "
                "Me peça no chat pra conferir isso.")
    # "401"/"403" soltos casavam dentro de um título de compromisso e davam o
    # motivo ERRADO — carimbo falso é pior do que carimbo nenhum.
    if any(m in t for m in ("erro api 401", "erro api 403", "erro 401", "erro 403",
                            "http error 401", "http error 403")):
        return ("O Google recusou o acesso agora. Se continuar, me peça no chat "
                "pra refazer a autorização.")
    return ("Não consegui falar com o Google agora. Tente de novo em instantes — "
            "se insistir, me avise no chat.")


def _roda(args, timeout, casca=None):
    """Roda a ferramenta. Devolve (ok, saída, recado_pra_pessoa)."""
    script = _script(casca)
    try:
        if not os.path.exists(script):
            return False, "", ("A ferramenta da agenda ainda não está instalada nesta "
                               "máquina. Me peça no chat pra ligar a agenda.")
    except Exception:
        return False, "", "Não consegui abrir a ferramenta da agenda agora."

    python = sys.executable or "python3"
    try:
        p = subprocess.run([python, script] + [str(a) for a in args],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "", ("O Google está demorando demais pra responder. "
                           "Tente de novo daqui a pouco.")
    except Exception:
        return False, "", "Não consegui abrir a ferramenta da agenda agora."

    saida = p.stdout or ""
    if p.returncode != 0:
        return False, saida, _recado_do_erro(saida + " " + (p.stderr or ""))
    return True, saida, ""


# ---------------------------------------------------------------- lendo o texto

def _limpa(txt):
    txt = "".join(c for c in (txt or "") if c == "\n" or c == "\t" or ord(c) >= 32)
    return txt.strip()


def _resolve_ano(dia, mes, referencia):
    """A ferramenta imprime só DD/MM. O ano é o que fica mais perto da data
    esperada — assim a virada de ano não quebra a tela."""
    melhor = None
    for ano in (referencia.year - 1, referencia.year, referencia.year + 1):
        try:
            candidata = datetime.date(ano, mes, dia)
        except ValueError:
            continue
        distancia = abs((candidata - referencia).days)
        if melhor is None or distancia < melhor[0]:
            melhor = (distancia, candidata)
    return melhor[1] if melhor else referencia


def _evento(linha):
    """'09:00–10:00  Reunião  [Trabalho] @ Sala 3' → dicionário."""
    texto = _limpa(linha)
    if not texto or texto.startswith("("):
        return None

    hora, resto = "", texto
    m = re.match(r"^(dia todo|\d{1,2}:\d{2}(?:\s*[–\-]\s*\d{1,2}:\d{2})?)\s\s*(.*)$",
                 texto)
    if m:
        hora = re.sub(r"\s*[\u2013-]\s*", "\u2013", m.group(1)).strip()
        resto = m.group(2)

    agenda, local = "", ""
    corte = re.search(r"\s\s+(?=\[|@ )", resto)
    if corte:
        extras = resto[corte.end():]
        resto = resto[:corte.start()]
        m2 = re.match(r"^\[([^\]]*)\]\s*", extras)
        if m2:
            agenda = m2.group(1).strip()
            extras = extras[m2.end():]
        if extras.startswith("@"):
            local = extras[1:].strip()

    titulo = resto.strip() or "(sem título)"
    return {"hora": hora or "dia todo", "titulo": titulo[:160],
            "local": local[:160], "agenda": agenda[:60],
            "diatodo": (hora or "dia todo") == "dia todo"}


def _blocos(saida, primeira_data):
    """Quebra a saída em dias. `primeira_data` é a data esperada do 1º bloco."""
    dias, atual = [], None

    def abre_dia(data):
        bloco = {"data": data.strftime("%d/%m/%Y"),
                 "diasemana": DIAS_SEMANA[data.weekday()],
                 "iso": data.isoformat(),
                 "eventos": []}
        dias.append(bloco)
        return bloco

    for linha in (saida or "").splitlines():
        if not linha.strip():
            continue
        if linha[:1].isspace():                       # linha de compromisso
            if atual is None:
                # compromisso antes de qualquer cabeçalho de dia: engolir era
                # perder compromisso calado. Abre o dia esperado e guarda.
                atual = abre_dia(primeira_data)
            ev = _evento(linha)
            if ev:
                atual["eventos"].append(ev)
            continue
        # cabeçalho de dia: "Quarta 27/08"
        esperada = primeira_data + datetime.timedelta(days=len(dias))
        data = esperada
        m = re.search(r"(\d{1,2})/(\d{1,2})", linha)
        if m:
            try:
                data = _resolve_ano(int(m.group(1)), int(m.group(2)), esperada)
            except Exception:
                data = esperada
        atual = abre_dia(data)
    return dias


def _hoje_provavel():
    """Só pra chutar o ano do primeiro bloco — a data em si vem da ferramenta,
    que conhece o fuso configurado."""
    try:
        return datetime.date.today()
    except Exception:
        return datetime.date(1970, 1, 1)


# ------------------------------------------------------------------------ tela

CSS = """
.ag-hoje-cab{display:flex;gap:10px;align-items:baseline;justify-content:space-between;
             flex-wrap:wrap;margin:0 0 10px}
.ag-hoje-cab h2{margin:0;font-size:1.1rem}
.ag-dia{margin-top:18px}
.ag-dia:first-child{margin-top:0}
.ag-dia-cab{display:flex;gap:8px;align-items:baseline;justify-content:space-between;
            padding-bottom:6px;margin-bottom:6px;border-bottom:1px solid var(--linha)}
.ag-dia-nome{font-weight:600}
.ag-dia-data{color:var(--fraco);font-size:.8rem}
.ag-ev{display:flex;gap:12px;align-items:flex-start;padding:8px 0}
.ag-ev + .ag-ev{border-top:1px solid var(--linha)}
.ag-hora{flex:0 0 5.4rem;font-variant-numeric:tabular-nums;font-weight:600;
         font-size:.85rem;line-height:1.45;color:var(--marca)}
.ag-hora.ag-todo{color:var(--fraco);font-weight:500}
.ag-corpo{flex:1 1 auto;min-width:0}
.ag-titulo{line-height:1.35;overflow-wrap:anywhere}
.ag-local{color:var(--fraco);font-size:.82rem;margin-top:2px;overflow-wrap:anywhere}
.ag-etiqueta{margin-top:4px}
.ag-rodape{margin-top:14px}
"""

JS = """
(function(){
  function id(x){ return document.getElementById(x); }
  function novo(tag, cls, txt){
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt !== undefined && txt !== null) e.textContent = txt;
    return e;
  }
  function limpa(el){ while (el && el.firstChild) el.removeChild(el.firstChild); }

  function aviso(msg, tipo){
    var caixa = id('ag-aviso');
    limpa(caixa);
    if (!msg) return;
    var faixa = novo('div', 'aviso ' + (tipo || 'atencao'));
    faixa.appendChild(novo('span', null, msg));
    var b = novo('button', 'btn', 'Tentar de novo');
    b.style.marginLeft = '10px';
    b.onclick = carrega;
    faixa.appendChild(b);
    caixa.appendChild(faixa);
  }

  function evento(ev){
    var linha = novo('div', 'ag-ev');
    linha.appendChild(novo('div', 'ag-hora' + (ev.diatodo ? ' ag-todo' : ''),
                           ev.diatodo ? 'dia todo' : ev.hora));
    var corpo = novo('div', 'ag-corpo');
    corpo.appendChild(novo('div', 'ag-titulo', ev.titulo));
    if (ev.local) corpo.appendChild(novo('div', 'ag-local', ev.local));
    if (ev.agenda){
      var et = novo('div', 'ag-etiqueta');
      et.appendChild(novo('span', 'chip', ev.agenda));
      corpo.appendChild(et);
    }
    linha.appendChild(corpo);
    return linha;
  }

  function desenhaHoje(dia){
    var caixa = id('ag-hoje');
    limpa(caixa);
    var cab = novo('div', 'ag-hoje-cab');
    cab.appendChild(novo('h2', null, 'Hoje'));
    if (dia) cab.appendChild(novo('span', 'fraco', dia.diasemana + ', ' + dia.data));
    caixa.appendChild(cab);
    if (!dia){
      caixa.appendChild(novo('div', 'vazio',
        'Não consegui ler a resposta da sua agenda desta vez.'));
      return;
    }
    if (!dia.eventos.length){
      caixa.appendChild(novo('div', 'vazio', 'Nada marcado pra hoje.'));
      return;
    }
    dia.eventos.forEach(function(ev){ caixa.appendChild(evento(ev)); });
  }

  function desenhaProximos(dias, quantos){
    var caixa = id('ag-proximos');
    limpa(caixa);
    caixa.appendChild(novo('h2', null, 'Próximos ' + quantos + ' dias'));
    if (!dias){
      caixa.appendChild(novo('div', 'vazio',
        'Não consegui ver os próximos dias desta vez.'));
      return;
    }
    var comAlgo = dias.filter(function(d){ return d.eventos.length; });
    if (!comAlgo.length){
      caixa.appendChild(novo('div', 'vazio', 'Nada marcado pros próximos dias.'));
      return;
    }
    comAlgo.forEach(function(d){
      var bloco = novo('div', 'ag-dia');
      var cab = novo('div', 'ag-dia-cab');
      cab.appendChild(novo('span', 'ag-dia-nome', d.diasemana));
      cab.appendChild(novo('span', 'ag-dia-data', d.data));
      bloco.appendChild(cab);
      d.eventos.forEach(function(ev){ bloco.appendChild(evento(ev)); });
      caixa.appendChild(bloco);
    });
    if (comAlgo.length < dias.length)
      caixa.appendChild(novo('p', 'fraco', 'Os dias que não aparecem estão livres.'));
  }

  function kpis(hoje, dias, quantos){
    var caixa = id('ag-kpis');
    limpa(caixa);
    // "—" quando eu NÃO SEI. Pôr 0 no lugar de "não sei" é mentira na tela.
    var n1 = hoje ? String(hoje.eventos.length) : '—';
    var n2 = '—';
    if (dias){
      var soma = 0;
      dias.forEach(function(d){ soma += d.eventos.length; });
      n2 = String(soma);
    }
    var k1 = novo('div', 'kpi');
    k1.appendChild(novo('b', null, n1));
    k1.appendChild(novo('span', null, n1 === '1' ? 'compromisso hoje' : 'compromissos hoje'));
    var k2 = novo('div', 'kpi');
    k2.appendChild(novo('b', null, n2));
    k2.appendChild(novo('span', null, 'nos próximos ' + quantos + ' dias'));
    caixa.appendChild(k1);
    caixa.appendChild(k2);
  }

  function carregando(){
    limpa(id('ag-kpis'));
    var h = id('ag-hoje'); limpa(h);
    h.appendChild(novo('div', 'vazio', 'Consultando a sua agenda… isso leva alguns segundos.'));
    var pr = id('ag-proximos'); limpa(pr);
    pr.appendChild(novo('div', 'vazio', 'Consultando os próximos dias…'));
  }

  function carrega(){
    aviso('');
    carregando();
    fetch('/api/agenda/dados', {headers:{'Accept':'application/json'}})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d || !d.ok){
          limpa(id('ag-kpis'));
          var h = id('ag-hoje'); limpa(h);
          h.appendChild(novo('div', 'vazio', 'Sem agenda pra mostrar agora.'));
          limpa(id('ag-proximos'));
          aviso((d && d.recado) || 'Não consegui falar com o Google agora.');
          return;
        }
        var quantos = d.dias_adiante || 7;
        kpis(d.hoje, d.proximos, quantos);
        desenhaHoje(d.hoje);
        desenhaProximos(d.proximos, quantos);
        if (d.recado) aviso(d.recado);
      })
      .catch(function(){
        limpa(id('ag-kpis'));
        var h = id('ag-hoje'); limpa(h);
        h.appendChild(novo('div', 'vazio', 'Sem agenda pra mostrar agora.'));
        limpa(id('ag-proximos'));
        aviso('A página não conseguiu falar com a máquina. Verifique a conexão e tente de novo.');
      });
  }

  var bt = id('ag-atualizar');
  if (bt) bt.onclick = carrega;
  carrega();
})();
"""


def _pagina():
    return """
<div class=cartao>
  <div class=kpis id=ag-kpis>
    <div class=kpi><b>—</b><span>compromissos hoje</span></div>
  </div>
  <div style="margin-top:12px">
    <button class="btn" id=ag-atualizar>Atualizar</button>
  </div>
</div>

<div id=ag-aviso></div>

<div class=cartao id=ag-hoje>
  <div class=vazio>Consultando a sua agenda…</div>
</div>

<div class=cartao id=ag-proximos>
  <div class=vazio>Consultando os próximos dias…</div>
</div>

<p class="fraco ag-rodape">Esta tela é só leitura: eu vejo os seus compromissos, mas não
marco, não mudo e não apago nada na sua agenda.</p>
"""


def registra(app, casca, exige_login):
    @app.get("/agenda")
    def tela_agenda():
        exige_login()
        # sem remendo de "e se o shell não aceitar css/js": a tela sem o js é uma
        # página que carrega pra sempre — parece viva e está morta.
        pagina = casca.shell(TITULO, _pagina(), "/agenda", css=CSS, js=JS)
        return Response(pagina, mimetype="text/html")

    @app.get("/api/agenda/dados")
    def api_agenda_dados():
        exige_login()
        try:
            ok, saida, recado = _roda(["hoje"], TIMEOUT_HOJE, casca)
            if not ok:
                return jsonify({"ok": False, "recado": recado})

            hoje_blocos = _blocos(saida, _hoje_provavel())
            hoje = hoje_blocos[0] if hoje_blocos else None

            try:
                base = (datetime.date.fromisoformat(hoje["iso"]) if hoje
                        else _hoje_provavel())
            except Exception:
                base = _hoje_provavel()

            # None = "não sei"; lista vazia = "sei, e não tem nada". A tela
            # mostra "—" no primeiro caso e 0 no segundo.
            proximos, alerta = None, ""
            ok2, saida2, recado2 = _roda(["proximos", DIAS_ADIANTE],
                                         TIMEOUT_FRENTE, casca)
            if ok2:
                proximos = _blocos(saida2, base + datetime.timedelta(days=1))
            else:
                motivo = (recado2 or "").strip()
                motivo = (motivo[0].lower() + motivo[1:]) if motivo else \
                    "não consegui falar com o Google agora."
                alerta = "Consegui ver hoje, mas não os próximos dias: " + motivo

            return jsonify({"ok": True, "hoje": hoje, "proximos": proximos,
                            "dias_adiante": DIAS_ADIANTE, "recado": alerta})
        except Exception:
            return jsonify({"ok": False,
                            "recado": "Deu um problema aqui na máquina ao montar a "
                                      "agenda. Tente de novo; se insistir, me avise "
                                      "no chat."})
