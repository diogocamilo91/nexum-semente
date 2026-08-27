# -*- coding: utf-8 -*-
"""
Tela "WhatsApp" — o espelho só-leitura das conversas, dentro do app.

⚠️ CONTRATO DO MÓDULO (não é pra afrouxar): este espelho SÓ LÊ. Nada nesta tela
envia mensagem, marca como lida, apaga ou altera qualquer coisa — e o conteúdo é
de TERCEIROS: fica na máquina, fora do backup, e não sai daqui.

A tela abre no RESUMO (quais conversas tiveram movimento, quantas mensagens em
cada uma, o período). O conteúdo das mensagens só aparece quando a pessoa abre uma
conversa específica. Anexo (foto, áudio, vídeo, documento) nunca é mostrado nem
baixado — o espelho só registra que chegou.

-------------------------------------------------------------------------------
O FORMATO QUE ESTA TELA ESPERA (o coletor é escrito na instalação, seguindo
`modulos/whatsapp/desenho.md`; é esse desenho que está implementado aqui):

  ~/semente-whatsapp/dados/mensagens.jsonl   uma mensagem por linha, em JSON,
      acrescentada no fim do arquivo, em ordem de chegada:
        {"ts": ..., "chat": "...", "chatNome": "...", "de": "...",
         "deNome": "...", "texto": "...", "tipo": "..."}
      · ts    — quando chegou. Aceito em segundos, em milissegundos ou em texto
                no padrão do calendário internacional (2026-01-31T14:03:00).
      · chat  — o identificador da conversa (grupo termina em "@g.us").
      · tipo  — "conversation"/"texto" ou o tipo da mídia ("imageMessage",
                "audioMessage", "imagem", "áudio"...). Mídia entra só como marca.
      Campos extras são ignorados; campos faltando não quebram nada.

  ~/semente-whatsapp/dados/chats.json        {"<id do chat>": "<nome>"}
  ~/semente-whatsapp/dados/contatos.json     {"<id da pessoa>": "<nome>"}
      Também aceito no formato {"<id>": {"name": "..."}} e como lista de objetos
      com "id"/"name".

  ~/semente-whatsapp/qr.png                  se existe E é RECENTE, a ligação está
                                             esperando ser lida no celular (sessão
                                             caiu). Arquivo velho é sobra do último
                                             pareamento: não é alarme.
  ~/semente-whatsapp/run.pid                 o número do processo do coletor —
                                             usado só pra dizer se ele está de pé.

Se o formato do coletor instalado for outro, é aqui que se ajusta a leitura
(funções _linha_mensagem e _le_mapa). Faltando qualquer arquivo, a tela não
quebra: mostra o estado vazio com a frase honesta do que está faltando.
"""

import json
import os
import re
import time
from collections import deque
from datetime import datetime

from flask import Response, jsonify, request

CHAVE = "zap"
TITULO = "WhatsApp"
ICONE = "telefone"
GRUPO = "ferramentas"
ORDEM = 60

_SIM = ("sim", "s", "1", "true", "yes", "on")
_PASTA_PADRAO = "~/semente-whatsapp"
_CHAT_OK = re.compile(r"^[A-Za-z0-9@._:\-]{3,120}$")
_TETO_LEITURA = 6 * 1024 * 1024      # lê no máximo o trecho final do espelho
_TETO_LINHAS = 200000                # e no máximo esta quantidade de linhas
_TETO_CONVERSAS = 80
_TETO_MENSAGENS = 200
_TETO_GENTE = 60                     # até onde eu conto gente diferente num grupo
_QR_VALIDO = 30 * 60                 # código de pareamento mais velho que isto já morreu

_TIPOS = {
    "conversation": "", "extendedtextmessage": "", "texto": "", "text": "",
    "imagemessage": "imagem", "imagem": "imagem", "image": "imagem",
    "videomessage": "vídeo", "video": "vídeo", "vídeo": "vídeo",
    "audiomessage": "áudio", "audio": "áudio", "áudio": "áudio",
    "pttmessage": "áudio", "ptt": "áudio",
    "documentmessage": "documento", "documento": "documento", "document": "documento",
    "stickermessage": "figurinha", "sticker": "figurinha", "figurinha": "figurinha",
    "contactmessage": "contato", "contato": "contato",
    "locationmessage": "localização", "localizacao": "localização",
    "reactionmessage": "reação", "reacao": "reação",
    "pollcreationmessage": "enquete", "enquete": "enquete",
}


# --------------------------------------------------------------------------
# disponibilidade
# --------------------------------------------------------------------------

def _pasta(cfg):
    try:
        alvo = (cfg or {}).get("WHATSAPP_DIR") or _PASTA_PADRAO
    except Exception:
        alvo = _PASTA_PADRAO
    try:
        return os.path.expanduser(str(alvo).strip().strip('"').strip("'"))
    except Exception:
        return os.path.expanduser(_PASTA_PADRAO)


def disponivel(cfg):
    """Só existe se o dono ligou o módulo E a casa do espelho está na máquina."""
    try:
        cfg = cfg or {}
        valor = str(cfg.get("WHATSAPP_ATIVO", "")).strip().strip('"').strip("'").lower()
        return valor in _SIM and os.path.isdir(_pasta(cfg))
    except Exception:
        return False


# --------------------------------------------------------------------------
# leitura do espelho (nunca escreve, nunca apaga)
# --------------------------------------------------------------------------

def _config(casca):
    try:
        return casca.config() or {}
    except Exception:
        return {}


def _caminhos(casca):
    base = _pasta(_config(casca))
    return {
        "base": base,
        "dados": os.path.join(base, "dados"),
        "mensagens": os.path.join(base, "dados", "mensagens.jsonl"),
        "chats": os.path.join(base, "dados", "chats.json"),
        "contatos": os.path.join(base, "dados", "contatos.json"),
        "qr": os.path.join(base, "qr.png"),
        "pid": os.path.join(base, "run.pid"),
    }


def _le_mapa(caminho):
    """id -> nome, aceitando os formatos mais comuns. Nunca levanta erro."""
    mapa = {}
    try:
        if not os.path.exists(caminho) or os.path.getsize(caminho) > 8 * 1024 * 1024:
            return mapa
        with open(caminho, "r", encoding="utf-8", errors="replace") as fh:
            dado = json.load(fh)
    except Exception:
        return mapa
    def _nome(v):
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, dict):
            for chave in ("name", "nome", "subject", "pushName", "notify", "verifiedName"):
                if isinstance(v.get(chave), str) and v.get(chave).strip():
                    return v[chave].strip()
        return ""
    try:
        if isinstance(dado, dict):
            for ident, valor in dado.items():
                nome = _nome(valor)
                if nome:
                    mapa[str(ident)] = nome
        elif isinstance(dado, list):
            for item in dado:
                if isinstance(item, dict):
                    ident = item.get("id") or item.get("jid") or item.get("chat")
                    nome = _nome(item)
                    if ident and nome:
                        mapa[str(ident)] = nome
    except Exception:
        pass
    return mapa


def _marca(valor):
    """Devolve o instante em segundos, ou None se não der pra saber."""
    if valor is None or valor == "":
        return None
    try:
        if isinstance(valor, bool):
            return None
        if isinstance(valor, (int, float)):
            n = float(valor)
        elif isinstance(valor, str):
            limpo = valor.strip()
            if re.fullmatch(r"\d{9,16}", limpo):
                n = float(limpo)
            else:
                try:
                    d = datetime.fromisoformat(limpo.replace("Z", "+00:00"))
                except Exception:
                    return None
                return d.timestamp()
        else:
            return None
    except Exception:
        return None
    if n > 1e14:      # microssegundos
        n = n / 1000000.0
    elif n > 1e11:    # milissegundos
        n = n / 1000.0
    if n < 946684800 or n > time.time() + 86400 * 3:   # antes de 2000 ou muito no futuro
        return None
    return n


def _telefone(bruto):
    digitos = re.sub(r"\D", "", bruto or "")
    if len(digitos) == 13 and digitos.startswith("55"):
        return "+55 (%s) %s-%s" % (digitos[2:4], digitos[4:9], digitos[9:])
    if len(digitos) == 12 and digitos.startswith("55"):
        return "+55 (%s) %s-%s" % (digitos[2:4], digitos[4:8], digitos[8:])
    if digitos:
        return "+" + digitos
    return (bruto or "").strip()


def _apelido(ident):
    """Sem nome guardado: mostra algo que a pessoa reconheça."""
    ident = str(ident or "").strip()
    if not ident:
        return "Conversa sem nome"
    if ident == "status@broadcast":
        return "Status (recados)"
    if ident.endswith("@g.us"):
        return "Grupo sem nome"
    if ident.endswith("@broadcast"):
        return "Lista de transmissão"
    return _telefone(ident.split("@")[0].split(":")[0]) or ident


def _nome_de(ident, dado, mapas):
    if isinstance(dado, str) and dado.strip():
        return dado.strip()
    for mapa in mapas:
        achado = mapa.get(str(ident))
        if achado:
            return achado
    return _apelido(ident)


def _tipo_amigavel(bruto, texto):
    chave = str(bruto or "").strip().lower()
    if chave in _TIPOS:
        return _TIPOS[chave]
    if chave.endswith("message"):
        chave = chave[:-7]
        if chave in _TIPOS:
            return _TIPOS[chave]
    marca = (texto or "").strip().lower()
    if marca.startswith("[") and marca.endswith("]") and len(marca) <= 20:
        return marca.strip("[]")
    return ""


def _linha_mensagem(bruto):
    """Uma linha do espelho -> dicionário simples. Devolve None se não servir."""
    try:
        dado = json.loads(bruto)
    except Exception:
        return None
    if not isinstance(dado, dict):
        return None
    chat = dado.get("chat") or dado.get("chatId") or dado.get("jid") or dado.get("remoteJid")
    if not chat:
        return None
    texto = dado.get("texto")
    if not isinstance(texto, str):
        texto = dado.get("text") if isinstance(dado.get("text"), str) else ""
    return {
        "chat": str(chat),
        "chatNome": dado.get("chatNome") or dado.get("chatName") or "",
        "de": str(dado.get("de") or dado.get("from") or dado.get("participant") or ""),
        "deNome": dado.get("deNome") or dado.get("pushName") or "",
        "texto": texto or "",
        "tipo": dado.get("tipo") or dado.get("type") or "",
        "eu": bool(dado.get("fromMe") or dado.get("eu") or dado.get("deMim")),
        "ts": _marca(dado.get("ts") if dado.get("ts") is not None
                     else (dado.get("timestamp") if dado.get("timestamp") is not None
                           else dado.get("data"))),
    }


def _varre(caminho, desde, alvo=None):
    """Uma passada só no espelho: soma o resumo e (se pedido) guarda a conversa.

    Lê apenas o trecho final do arquivo (o espelho só cresce), pra não pesar
    numa máquina pequena. Devolve tudo pronto, sem levantar erro.
    """
    resumo = {}
    ultimas = deque(maxlen=_TETO_MENSAGENS)
    dados = {"total": 0, "sem_data": 0, "truncado": False, "ultima": None, "linhas": 0}
    try:
        tamanho = os.path.getsize(caminho)
    except Exception:
        return resumo, ultimas, dados
    inicio = 0
    if tamanho > _TETO_LEITURA:
        inicio = tamanho - _TETO_LEITURA
        dados["truncado"] = True
    try:
        with open(caminho, "rb") as fh:
            if inicio:
                fh.seek(inicio)
                fh.readline()          # descarta a linha cortada ao meio
            for cru in fh:
                dados["linhas"] += 1
                if dados["linhas"] > _TETO_LINHAS:
                    dados["truncado"] = True
                    break
                linha = cru.decode("utf-8", "replace").strip()
                if not linha or linha[0] != "{":
                    continue
                msg = _linha_mensagem(linha)
                if not msg:
                    continue
                marca = msg["ts"]
                if marca is not None:
                    if dados["ultima"] is None or marca > dados["ultima"]:
                        dados["ultima"] = marca
                if desde:
                    if marca is None:
                        dados["sem_data"] += 1
                        continue
                    if marca < desde:
                        continue
                elif marca is None:
                    dados["sem_data"] += 1
                dados["total"] += 1
                ficha = resumo.get(msg["chat"])
                if ficha is None:
                    ficha = {"n": 0, "nome": "", "primeiro": None, "ultimo": None,
                             "gente": set(), "mais_gente": False}
                    resumo[msg["chat"]] = ficha
                ficha["n"] += 1
                if msg["chatNome"]:
                    ficha["nome"] = msg["chatNome"]
                if msg["de"]:
                    if len(ficha["gente"]) < _TETO_GENTE:
                        ficha["gente"].add(msg["de"])
                    elif msg["de"] not in ficha["gente"]:
                        ficha["mais_gente"] = True
                if marca is not None:
                    if ficha["primeiro"] is None or marca < ficha["primeiro"]:
                        ficha["primeiro"] = marca
                    if ficha["ultimo"] is None or marca > ficha["ultimo"]:
                        ficha["ultimo"] = marca
                if alvo and msg["chat"] == alvo:
                    ultimas.append(msg)
    except Exception:
        pass
    return resumo, ultimas, dados


def _coletor_de_pe(caminho_pid):
    """Só espia: lê o número do processo e vê se ele existe. Não mexe em nada."""
    try:
        with open(caminho_pid, "r", encoding="utf-8", errors="replace") as fh:
            pid = int((fh.read() or "").strip().split()[0])
        if pid <= 0:
            return None
        return os.path.isdir("/proc/%d" % pid)
    except Exception:
        return None


def _qr_esperando(caminho_qr):
    """O código de pareamento só vale se for RECENTE.

    O arquivo do código fica no disco depois do pareamento até alguém apagar —
    e um arquivo velho fazia a tela gritar 'a ligação caiu' pra sempre E, pior,
    calava o aviso de coletor fora do ar (o alarme de sessão pulava a checagem).
    Código de pareamento se renova a cada poucos segundos enquanto está
    esperando: velho = já foi usado, não é alarme."""
    try:
        if not os.path.exists(caminho_qr):
            return False
        return (time.time() - os.path.getmtime(caminho_qr)) < _QR_VALIDO
    except Exception:
        return False


# --------------------------------------------------------------------------
# formatação
# --------------------------------------------------------------------------

def _dia_br(marca):
    try:
        return datetime.fromtimestamp(marca).strftime("%d/%m/%Y")
    except Exception:
        return ""


def _hora_br(marca):
    try:
        return datetime.fromtimestamp(marca).strftime("%H:%M")
    except Exception:
        return ""


def _quando(marca):
    if not marca:
        return ""
    return (_dia_br(marca) + " às " + _hora_br(marca)).strip()


def _ha_quanto(marca):
    if not marca:
        return ""
    try:
        seg = time.time() - float(marca)
    except Exception:
        return ""
    if seg < 0:
        return "agora"
    if seg < 90:
        return "agora mesmo"
    if seg < 3600:
        minutos = int(seg // 60)
        return "há 1 minuto" if minutos == 1 else "há %d minutos" % minutos
    if seg < 86400:
        horas = int(seg // 3600)
        return "há 1 hora" if horas == 1 else "há %d horas" % horas
    dias = int(seg // 86400)
    return "ontem" if dias == 1 else "há %d dias" % dias


def _desde(dias):
    """dias=0 é 'tudo'; dias=1 é 'hoje' (da meia-noite pra cá)."""
    if not dias:
        return 0
    if dias == 1:
        agora = datetime.now()
        return datetime(agora.year, agora.month, agora.day).timestamp()
    return time.time() - (dias * 86400)


def _conta_msg(n):
    return "1 mensagem" if n == 1 else "%d mensagens" % n


def _rotulo_periodo(dias):
    return {0: "todo o espelho", 1: "hoje", 7: "últimos 7 dias",
            30: "últimos 30 dias"}.get(dias, "últimos %d dias" % dias)


# --------------------------------------------------------------------------
# a tela
# --------------------------------------------------------------------------

_CSS = """
.zap-per{display:flex;flex-wrap:wrap;gap:6px}
.zap-linha{display:flex;gap:10px;align-items:center;cursor:pointer}
.zap-ic{flex:0 0 26px;text-align:center;font-size:18px}
.zap-meio{flex:1 1 auto;min-width:0}
.zap-nome{display:block;font-weight:600;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.zap-sub{display:block;margin-top:2px;font-size:12px;color:var(--fraco)}
.zap-conta{flex:0 0 auto;text-align:right}
.zap-conta b{display:block;font-size:15px}
.zap-conta span{display:block;font-size:11px;color:var(--fraco)}
.zap-cab{display:flex;gap:10px;align-items:flex-start;justify-content:space-between}
.zap-cab h2{margin:0;font-size:17px;word-break:break-word}
.zap-msgs{display:flex;flex-direction:column;gap:12px;margin-top:12px;
  max-height:65vh;overflow:auto}
.zap-dia{align-self:center;font-size:11px;color:var(--fraco);
  border:1px solid var(--linha);border-radius:999px;padding:2px 10px}
.zap-msg{border-left:3px solid var(--linha);padding:2px 0 2px 10px}
.zap-msg.eu{border-left-color:var(--marca)}
.zap-quem{font-size:12px;font-weight:600}
.zap-hora{font-size:11px;color:var(--fraco);margin-left:6px}
.zap-txt{margin:3px 0 0;white-space:pre-wrap;word-break:break-word;font-size:14px;
  line-height:1.45}
"""

_JS = """
(function(){
  var dias = 7;
  var conversas = {};
  function ele(id){ return document.getElementById(id); }
  function txt(tag, classe, valor){
    var n = document.createElement(tag);
    if(classe){ n.className = classe; }
    if(valor !== undefined && valor !== null){ n.textContent = valor; }
    return n;
  }
  function vazio(frase, extra){
    var d = txt('div','vazio', frase);
    if(extra){
      var p = txt('div','fraco', extra);
      p.style.marginTop = '8px';
      p.style.fontSize = '12px';
      d.appendChild(p);
    }
    return d;
  }
  function pedir(url){
    return fetch(url, {credentials:'same-origin', headers:{'Accept':'application/json'}})
      .then(function(r){
        if(r.status === 401 || r.status === 403){
          return {ok:false, erro:'Sua sessão expirou. Atualize a página e entre de novo.'};
        }
        return r.json().catch(function(){
          return {ok:false, erro:'Recebi uma resposta que não entendi. Tente de novo.'};
        });
      })
      .catch(function(){
        return {ok:false, erro:'Não consegui falar com o aplicativo. Confira a conexão.'};
      });
  }

  function rotulo(){
    return ({1:'hoje', 7:'últimos 7 dias', 30:'últimos 30 dias',
             0:'todo o espelho'})[dias] || '';
  }
  function pintaPeriodo(){
    var caixa = ele('zapPeriodo');
    caixa.innerHTML = '';
    [[1,'Hoje'],[7,'7 dias'],[30,'30 dias'],[0,'Tudo']].forEach(function(op){
      var b = txt('button', 'btn' + (dias === op[0] ? ' primario' : ''), op[1]);
      b.type = 'button';
      b.onclick = function(){ dias = op[0]; carrega(); };
      caixa.appendChild(b);
    });
  }

  function pintaAviso(d){
    var caixa = ele('zapEstado');
    caixa.innerHTML = '';
    if(d.recado_sessao){
      caixa.appendChild(txt('div','aviso erro', d.recado_sessao));
    } else if(d.recado_parado){
      caixa.appendChild(txt('div','aviso atencao', d.recado_parado));
    }
  }

  function pintaResumo(d){
    var lista = ele('zapLista');
    lista.innerHTML = '';
    conversas = {};
    ele('zapPeriodoTexto').textContent = d.periodo || rotulo();
    if(!d.ok){
      ele('zapKpiConversas').textContent = '—';
      ele('zapKpiMensagens').textContent = '—';
      ele('zapUltima').textContent = '';
      pintaAviso(d);
      lista.appendChild(vazio(d.erro || 'Não consegui ler o espelho do WhatsApp agora.',
                              d.dica || ''));
      return;
    }
    pintaAviso(d);
    ele('zapKpiConversas').textContent = d.total_conversas;
    ele('zapKpiMensagens').textContent = d.total_mensagens;
    ele('zapKpiConversasRot').textContent = d.total_conversas === 1
      ? 'conversa com movimento' : 'conversas com movimento';
    ele('zapKpiMensagensRot').textContent = d.total_mensagens === 1
      ? 'mensagem no período' : 'mensagens no período';
    ele('zapUltima').textContent = d.ultima
      ? ('Mensagem mais recente no espelho: ' + d.ultima + ' (' + d.ultima_ha + ').')
      : 'Nenhuma mensagem no espelho ainda.';
    if(!d.conversas.length){
      lista.appendChild(vazio(d.vazio_frase || 'Nenhuma conversa teve movimento neste período.',
                              d.vazio_dica || ''));
      return;
    }
    var caixa = txt('div','lista');
    d.conversas.forEach(function(c){
      conversas[c.id] = c;
      var li = txt('div','item zap-linha');
      li.appendChild(txt('span','zap-ic', c.grupo ? '👥' : '💬'));
      var meio = txt('div','zap-meio');
      meio.appendChild(txt('span','zap-nome', c.nome));
      var partes = [];
      if(c.grupo && c.gente > 1){
        partes.push(c.gente_mais ? ('mais de ' + c.gente + ' pessoas')
                                 : (c.gente + ' pessoas'));
      }
      if(c.ultimo){ partes.push('último ' + c.ultimo_ha); }
      meio.appendChild(txt('span','zap-sub', partes.join(' · ')));
      li.appendChild(meio);
      var conta = txt('div','zap-conta');
      conta.appendChild(txt('b', null, c.n));
      conta.appendChild(txt('span', null, c.n === 1 ? 'mensagem' : 'mensagens'));
      li.appendChild(conta);
      li.onclick = function(){ abre(c.id); };
      caixa.appendChild(li);
    });
    lista.appendChild(caixa);
    if(d.recado){ lista.appendChild(txt('p','fraco', d.recado)); }
  }

  function fecha(){
    var p = ele('zapPainel');
    p.innerHTML = '';
    p.hidden = true;
  }

  function abre(id){
    var p = ele('zapPainel');
    p.hidden = false;
    p.innerHTML = '';
    var carregando = txt('div','cartao');
    carregando.appendChild(txt('div','fraco','Abrindo a conversa…'));
    p.appendChild(carregando);
    try{ window.scrollTo({top:0, behavior:'smooth'}); }catch(e){ window.scrollTo(0,0); }
    pedir('/api/zap/conversa?chat=' + encodeURIComponent(id) + '&dias=' + dias)
      .then(function(d){
        p.innerHTML = '';
        var cartao = txt('div','cartao');
        var cab = txt('div','zap-cab');
        var titulo = (conversas[id] && conversas[id].nome) || d.nome || 'Conversa';
        cab.appendChild(txt('h2', null, titulo));
        var b = txt('button','btn','Fechar');
        b.type = 'button';
        b.onclick = fecha;
        cab.appendChild(b);
        cartao.appendChild(cab);
        if(!d.ok){
          cartao.appendChild(vazio(d.erro || 'Não consegui abrir esta conversa.'));
          p.appendChild(cartao);
          return;
        }
        cartao.appendChild(txt('p','fraco', d.legenda || ''));
        if(!d.mensagens.length){
          cartao.appendChild(vazio('Nenhuma mensagem desta conversa no período.'));
          p.appendChild(cartao);
          return;
        }
        var caixa = txt('div','zap-msgs');
        var diaAtual = '';
        d.mensagens.forEach(function(m){
          if(m.dia && m.dia !== diaAtual){
            diaAtual = m.dia;
            caixa.appendChild(txt('div','zap-dia', m.dia));
          }
          var bloco = txt('div','zap-msg' + (m.eu ? ' eu' : ''));
          var topo = document.createElement('div');
          topo.appendChild(txt('span','zap-quem', m.quem));
          if(m.hora){ topo.appendChild(txt('span','zap-hora', m.hora)); }
          bloco.appendChild(topo);
          if(m.tipo){
            var c = txt('span','chip', m.tipo + ' (anexo não guardado)');
            c.style.marginTop = '4px';
            c.style.display = 'inline-block';
            bloco.appendChild(c);
          }
          if(m.texto){ bloco.appendChild(txt('p','zap-txt', m.texto)); }
          caixa.appendChild(bloco);
        });
        cartao.appendChild(caixa);
        p.appendChild(cartao);
      });
  }

  function carrega(){
    fecha();
    pintaPeriodo();
    ele('zapKpiConversas').textContent = '—';
    ele('zapKpiMensagens').textContent = '—';
    ele('zapPeriodoTexto').textContent = rotulo();
    var lista = ele('zapLista');
    lista.innerHTML = '';
    lista.appendChild(txt('div','vazio','Carregando…'));
    pedir('/api/zap/resumo?dias=' + dias).then(pintaResumo);
  }

  ele('zapAtualizar').onclick = carrega;
  carrega();
})();
"""

_CORPO = """
<div class="aviso atencao">
  Aqui dentro tem conversa de outras pessoas. Este é um espelho só de leitura:
  nada é respondido, apagado nem marcado como lido, nada sai desta máquina e nada
  entra na cópia de segurança. Abra uma conversa só quando precisar mesmo.
</div>

<div id=zapEstado></div>

<div class=cartao>
  <div class=zap-per id=zapPeriodo></div>
  <p class=fraco style="margin:10px 0 0">
    Período: <b id=zapPeriodoTexto>últimos 7 dias</b>.
    <span id=zapUltima></span>
  </p>
  <div style="margin-top:10px">
    <button class=btn id=zapAtualizar type=button>Atualizar</button>
  </div>
</div>

<div class=kpis>
  <div class=kpi><b id=zapKpiConversas>—</b>
    <span id=zapKpiConversasRot>conversas com movimento</span></div>
  <div class=kpi><b id=zapKpiMensagens>—</b>
    <span id=zapKpiMensagensRot>mensagens no período</span></div>
</div>

<div id=zapPainel hidden></div>

<div class=cartao id=zapLista>
  <div class=vazio>Carregando…</div>
</div>

<p class=fraco>Fotos, áudios, vídeos e documentos não são guardados: fica registrado
só que chegaram.</p>
<noscript><div class="aviso atencao">Esta tela precisa de um navegador com JavaScript
ligado pra mostrar o resumo.</div></noscript>
"""


def registra(app, casca, exige_login):

    @app.get("/zap")
    def tela_zap():
        exige_login()
        return Response(
            casca.shell("WhatsApp", _CORPO, "/zap", css=_CSS, js=_JS),
            mimetype="text/html")

    @app.get("/api/zap/resumo")
    def api_zap_resumo():
        exige_login()
        try:
            try:
                dias = int(request.args.get("dias", "7"))
            except Exception:
                dias = 7
            if dias not in (0, 1, 7, 30):
                dias = 7
            cam = _caminhos(casca)
            resposta = {
                "ok": True, "dias": dias, "periodo": _rotulo_periodo(dias),
                "conversas": [], "total_conversas": 0, "total_mensagens": 0,
                "ultima": "", "ultima_ha": "", "recado": "",
                "recado_sessao": "", "recado_parado": "",
                "vazio_frase": "", "vazio_dica": "",
            }

            if not os.path.isdir(cam["base"]):
                resposta.update({
                    "ok": False,
                    "erro": "O espelho do WhatsApp não está instalado nesta máquina.",
                    "dica": "Se você quer ligar isso, é só me pedir."})
                return jsonify(resposta)

            sessao_caiu = _qr_esperando(cam["qr"])
            if sessao_caiu:
                resposta["recado_sessao"] = (
                    "A ligação com o WhatsApp está esperando o celular: abra o WhatsApp, "
                    "vá em Aparelhos conectados e conecte de novo. Me avise que eu preparo "
                    "o código pra você ler.")

            # o coletor se olha SEMPRE, inclusive quando o espelho está vazio:
            # espelho vazio + coletor no chão é exatamente o caso em que a tela
            # não pode dizer "é normal, espere".
            de_pe = _coletor_de_pe(cam["pid"])
            if de_pe is False:
                resposta["recado_parado"] = (
                    "O coletor do WhatsApp não está de pé agora. Ele costuma "
                    "voltar sozinho em poucos minutos; se continuar assim, me avise.")

            if not os.path.exists(cam["mensagens"]) or os.path.getsize(cam["mensagens"]) == 0:
                resposta["ultima"] = ""
                resposta["vazio_frase"] = "Ainda não chegou nenhuma mensagem no espelho."
                resposta["vazio_dica"] = (
                    "Isso é normal logo depois de instalar: as mensagens só começam a "
                    "aparecer depois que o celular conecta."
                    if de_pe is not False else
                    "E o coletor está fora do ar agora — enquanto ele não voltar, "
                    "nada novo entra aqui.")
                return jsonify(resposta)

            desde = _desde(dias)
            resumo, _msgs, dados = _varre(cam["mensagens"], desde)
            mapas = [_le_mapa(cam["chats"]), _le_mapa(cam["contatos"])]

            linhas = []
            for ident, ficha in resumo.items():
                nome = _nome_de(ident, ficha["nome"], mapas)
                linhas.append({
                    "id": ident,
                    "nome": nome,
                    "grupo": ident.endswith("@g.us"),
                    "n": ficha["n"],
                    "gente": len(ficha["gente"]),
                    "gente_mais": bool(ficha.get("mais_gente")),
                    "primeiro": _quando(ficha["primeiro"]),
                    "ultimo": _quando(ficha["ultimo"]),
                    "ultimo_ha": _ha_quanto(ficha["ultimo"]),
                    "ordem": ficha["ultimo"] or 0,
                })
            linhas.sort(key=lambda c: (c["ordem"], c["n"]), reverse=True)
            sobrou = len(linhas) - _TETO_CONVERSAS
            if sobrou > 0:
                linhas = linhas[:_TETO_CONVERSAS]
            for linha in linhas:
                linha.pop("ordem", None)

            recados = []
            if sobrou > 0:
                recados.append("Mostrando as %d conversas com movimento mais recente "
                               "(outras %d ficaram de fora)." % (_TETO_CONVERSAS, sobrou))
            if dados["truncado"]:
                recados.append("O espelho está grande: li só o trecho mais recente dele.")
            if desde and dados["sem_data"]:
                recados.append("Fora desta contagem: %s sem data no espelho."
                               % _conta_msg(dados["sem_data"]))

            resposta.update({
                "conversas": linhas,
                "total_conversas": len(linhas) + max(sobrou, 0),
                "total_mensagens": dados["total"],
                "ultima": _quando(dados["ultima"]),
                "ultima_ha": _ha_quanto(dados["ultima"]),
                "recado": " ".join(recados),
            })

            if not linhas:
                resposta["vazio_frase"] = "Nenhuma conversa teve movimento neste período."
                resposta["vazio_dica"] = "Experimente um período maior, ali em cima."

            parado = ""
            if de_pe is False:
                parado = ("O coletor do WhatsApp não está de pé agora. Ele costuma "
                          "voltar sozinho em poucos minutos; se continuar assim, me avise.")
            elif (not sessao_caiu and dados["ultima"]
                    and (time.time() - dados["ultima"]) > 48 * 3600):
                parado = ("Faz mais de dois dias que não chega mensagem nova aqui. "
                          "Pode ser silêncio mesmo — ou a ligação com o celular caiu.")
            resposta["recado_parado"] = parado

            return jsonify(resposta)
        except Exception:
            return jsonify({"ok": False, "conversas": [], "periodo": "",
                            "erro": "Não consegui ler o espelho do WhatsApp agora.",
                            "dica": ""})

    @app.get("/api/zap/conversa")
    def api_zap_conversa():
        exige_login()
        try:
            alvo = (request.args.get("chat") or "").strip()
            if not _CHAT_OK.match(alvo):
                return jsonify({"ok": False, "mensagens": [],
                                "erro": "Não reconheci esta conversa."})
            try:
                dias = int(request.args.get("dias", "7"))
            except Exception:
                dias = 7
            if dias not in (0, 1, 7, 30):
                dias = 7
            cam = _caminhos(casca)
            if not os.path.exists(cam["mensagens"]):
                return jsonify({"ok": False, "mensagens": [],
                                "erro": "O espelho do WhatsApp está vazio."})

            desde = _desde(dias)
            resumo, ultimas, dados = _varre(cam["mensagens"], desde, alvo=alvo)
            mapas = [_le_mapa(cam["chats"]), _le_mapa(cam["contatos"])]
            ficha = resumo.get(alvo) or {"n": 0, "nome": ""}
            nome = _nome_de(alvo, ficha.get("nome"), mapas)

            saida = []
            for msg in ultimas:
                tipo = _tipo_amigavel(msg["tipo"], msg["texto"])
                texto = msg["texto"] or ""
                marcas = ("[" + tipo + "]", "[" + tipo.replace("á", "a") + "]")
                if tipo and texto.strip().lower() in marcas:
                    texto = ""
                if len(texto) > 4000:
                    texto = texto[:4000] + " …"
                saida.append({
                    "dia": _dia_br(msg["ts"]) if msg["ts"] else "",
                    "hora": _hora_br(msg["ts"]) if msg["ts"] else "",
                    "quem": "Você" if msg["eu"] else _nome_de(msg["de"], msg["deNome"], mapas),
                    "texto": texto,
                    "tipo": tipo,
                    "eu": msg["eu"],
                })

            total = ficha.get("n", 0)
            legenda = "%s · %s." % (_conta_msg(total), _rotulo_periodo(dias))
            if total > len(saida):
                legenda += " Mostrando as %d mais recentes." % len(saida)
            if dados["truncado"]:
                legenda += " O espelho está grande: li só o trecho mais recente dele."
            return jsonify({"ok": True, "nome": nome, "legenda": legenda,
                            "mensagens": saida})
        except Exception:
            return jsonify({"ok": False, "mensagens": [],
                            "erro": "Não consegui abrir esta conversa agora."})
