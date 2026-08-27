# -*- coding: utf-8 -*-
"""
Tela "Arquivos" — o Google Drive do dono, dentro do app. SÓ LEITURA.

O que ela faz: lista o conteúdo de uma pasta do Drive (nome, tipo, tamanho, data),
navega entrando nas pastas, busca por nome no Drive inteiro e, ao abrir um documento
do Google, mostra o texto dele aqui mesmo.

O que ela NÃO faz (de propósito, e não é pra mudar): não sobe arquivo, não apaga,
não renomeia, não move, não compartilha. Nada nesta tela escreve no Drive nem no
disco da máquina.

De onde vem o dado: das ferramentas do módulo Drive/Docs, em ~/semente-bin/
  drive.py listar <pastaId|raiz>       -> "📁 <id> | <nome>[ (12.3 MB)] | 2026-01-31T14:03"
  drive.py buscar "<trecho>" <n>       -> mesmo formato
  drive.py info   <arquivoId>          -> JSON (nome, tipo, tamanho, pasta-mãe, link)
  gdoc.py  ler    <docId>              -> "# título" + o texto do documento
Se o módulo não estiver instalado ou a autorização do Google não existir, a tela
não quebra: mostra o estado vazio com a frase honesta do que está faltando.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from flask import Response, jsonify, request

CHAVE = "arquivos"
TITULO = "Arquivos"
ICONE = "nuvem"
GRUPO = "principal"
ORDEM = 28

_SIM = ("sim", "s", "1", "true", "yes", "on")
_ID_OK = re.compile(r"^[A-Za-z0-9_\-]{6,200}$")
_TAM_FIM = re.compile(r"\s\((\d+(?:[.,]\d+)?) MB\)$")


# --------------------------------------------------------------------------
# disponibilidade
# --------------------------------------------------------------------------

def disponivel(cfg):
    """A tela existe se o módulo do Drive foi instalado nesta máquina."""
    try:
        cfg = cfg or {}
        for chave in ("DRIVE_ATIVO", "DRIVE_DOCS_ATIVO"):
            valor = str(cfg.get(chave, "")).strip().strip('"').strip("'").lower()
            if valor in _SIM:
                return True
        # sem a chave no config, vale a ferramenta existir na pasta que a pessoa
        # escolheu (DIR_BIN) — nunca chumbar o caminho padrão.
        pasta = str(cfg.get("DIR_BIN") or "~/semente-bin").strip().strip('"').strip("'")
        return os.path.exists(os.path.join(os.path.expanduser(pasta), "drive.py"))
    except Exception:
        return False


# --------------------------------------------------------------------------
# conversa com as ferramentas do Drive (sempre defensiva)
# --------------------------------------------------------------------------

def _dir_bin(casca):
    try:
        alvo = getattr(casca, "DIR_BIN", None) or "~/semente-bin"
    except Exception:
        alvo = "~/semente-bin"
    try:
        return os.path.expanduser(str(alvo))
    except Exception:
        return os.path.expanduser("~/semente-bin")


def _traduz_erro(texto):
    """Erro técnico da ferramenta -> frase que uma pessoa leiga entende."""
    t = (texto or "").lower()
    if "sem autoriza" in t or "credencial n" in t:
        return ("A ligação com o Google ainda não foi feita nesta máquina. "
                "Me peça pra ligar o Google Drive.")
    if "invalid_grant" in t or "erro oauth" in t:
        return ("A autorização do Google venceu. Me peça pra refazer a ligação "
                "com o Google Drive.")
    if "erro api 401" in t or "erro api 403" in t:
        return ("O Google recusou o acesso a este item — pode ser permissão do "
                "arquivo ou autorização vencida.")
    if "erro api 404" in t:
        return "Não achei este item no Drive. Ele pode ter sido movido ou renomeado."
    if "erro api 429" in t:
        return "O Google pediu pra esperar um pouco. Tente de novo em alguns minutos."
    if re.search(r"erro (api|download) 5\d\d", t):
        return "O Google respondeu com erro do lado dele. Tente de novo em alguns minutos."
    if ("urlopen error" in t or "urlerror" in t or "timed out" in t
            or "name or service" in t or "temporary failure" in t):
        return "Não consegui falar com o Google agora — parece falta de internet na máquina."
    return "Não consegui ler o Google Drive agora."


def _limpa_detalhe(linha):
    """Tira do detalhe o que NUNCA pode aparecer na tela: segredo e caminho da
    máquina. A ferramenta imprime o erro cru do Google, e esse erro cru já veio
    com `client_secret` dentro — sem esta faxina, o segredo ia pro navegador."""
    limpo = linha
    # 1) qualquer par "chave: valor" com cara de segredo vira reticências
    limpo = re.sub(
        r"(?i)\"?\b(client_secret|refresh_token|access_token|id_token|token|"
        r"secret|senha|password|passwd|api[_-]?key|authorization|bearer)\b\"?"
        r"\s*[:=]\s*\"?[^\s\",;}]+",
        "\\1: …", limpo)
    limpo = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+", "bearer …", limpo)
    # 2) sequência longa com cara de credencial, mesmo sem rótulo
    limpo = re.sub(r"\b(?=[A-Za-z0-9._\-]*\d)[A-Za-z0-9._\-]{40,}\b", "…", limpo)
    # 3) caminho de dentro da máquina (a pessoa não precisa ver, e é dado nosso)
    limpo = re.sub(r"(/[A-Za-z0-9._\-]+){2,}/?", "…", limpo)
    return limpo


def _detalhe(texto):
    """A última linha do erro cru — serve só pra pessoa me colar quando pedir ajuda.
    Passa pela faxina: segredo e caminho de máquina não vão pra tela."""
    ultima = ""
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith(("Traceback", "File \"")):
            ultima = linha
    try:
        ultima = _limpa_detalhe(ultima)
    except Exception:
        return ""
    return ultima[:180]


def _roda(casca, script, args, segundos=60):
    """Roda uma ferramenta do Drive. Devolve (ok, saida, mensagem, detalhe)."""
    caminho = os.path.join(_dir_bin(casca), script)
    if not os.path.exists(caminho):
        return (False, "",
                "As ferramentas do Google Drive não estão instaladas nesta máquina.", "")
    try:
        proc = subprocess.run(
            [sys.executable, caminho] + [str(a) for a in args],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=segundos)
    except subprocess.TimeoutExpired:
        return (False, "",
                "O Google está demorando demais pra responder. Tente de novo em instantes.", "")
    except Exception:
        return (False, "", "Não consegui consultar o Google Drive agora.", "")
    saida = proc.stdout or ""
    erro = proc.stderr or ""
    if proc.returncode != 0:
        return (False, saida, _traduz_erro(erro + " " + saida), _detalhe(erro or saida))
    return (True, saida, "", "")


# --------------------------------------------------------------------------
# formatação (tudo em PT-BR)
# --------------------------------------------------------------------------

def _num_br(valor, casas=1):
    try:
        return ("%.*f" % (casas, float(valor))).replace(".", ",")
    except Exception:
        return ""


def _tamanho_mb(mb):
    try:
        mb = float(mb)
    except Exception:
        return ""
    if mb <= 0:
        return "menos de 0,1 MB"
    if mb < 0.1:
        return "menos de 0,1 MB"
    if mb >= 1024:
        return _num_br(mb / 1024, 1) + " GB"
    return _num_br(mb, 1) + " MB"


def _tamanho_bytes(valor):
    try:
        n = float(valor)
    except Exception:
        return ""
    if n < 1024:
        return "%d bytes" % int(n)
    if n < 1024 * 1024:
        return _num_br(n / 1024, 1) + " KB"
    if n < 1024 * 1024 * 1024:
        return _num_br(n / (1024 * 1024), 1) + " MB"
    return _num_br(n / (1024 * 1024 * 1024), 2) + " GB"


def _data_br(iso):
    """2026-01-31T14:03(...) -> 31/01/2026 14:03, na hora da máquina."""
    texto = (iso or "").strip()
    if not texto:
        return ""
    try:
        limpo = texto.replace("Z", "+00:00")
        if len(limpo) == 16:
            marca = datetime.strptime(limpo, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
        else:
            marca = datetime.fromisoformat(limpo)
            if marca.tzinfo is None:
                marca = marca.replace(tzinfo=timezone.utc)
        return marca.astimezone().strftime("%d/%m/%Y %H:%M")
    except Exception:
        try:
            return datetime.strptime(texto[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            return ""


_POR_EXTENSAO = {
    "pdf": ("PDF", "📕"),
    "doc": ("Documento do Word", "📄"), "docx": ("Documento do Word", "📄"),
    "odt": ("Documento", "📄"), "rtf": ("Documento", "📄"),
    "txt": ("Texto", "📄"), "md": ("Texto", "📄"), "log": ("Texto", "📄"),
    "xls": ("Planilha do Excel", "📊"), "xlsx": ("Planilha do Excel", "📊"),
    "csv": ("Planilha", "📊"), "ods": ("Planilha", "📊"),
    "ppt": ("Apresentação", "📽️"), "pptx": ("Apresentação", "📽️"),
    "odp": ("Apresentação", "📽️"),
    "jpg": ("Imagem", "🖼️"), "jpeg": ("Imagem", "🖼️"), "png": ("Imagem", "🖼️"),
    "gif": ("Imagem", "🖼️"), "webp": ("Imagem", "🖼️"), "heic": ("Imagem", "🖼️"),
    "bmp": ("Imagem", "🖼️"), "svg": ("Imagem", "🖼️"), "tif": ("Imagem", "🖼️"),
    "tiff": ("Imagem", "🖼️"),
    "mp4": ("Vídeo", "🎬"), "mov": ("Vídeo", "🎬"), "avi": ("Vídeo", "🎬"),
    "mkv": ("Vídeo", "🎬"), "webm": ("Vídeo", "🎬"), "m4v": ("Vídeo", "🎬"),
    "mp3": ("Áudio", "🎵"), "m4a": ("Áudio", "🎵"), "ogg": ("Áudio", "🎵"),
    "opus": ("Áudio", "🎵"), "wav": ("Áudio", "🎵"), "aac": ("Áudio", "🎵"),
    "zip": ("Arquivo compactado", "🗜️"), "rar": ("Arquivo compactado", "🗜️"),
    "7z": ("Arquivo compactado", "🗜️"), "gz": ("Arquivo compactado", "🗜️"),
    "tar": ("Arquivo compactado", "🗜️"),
}

_POR_TIPO_GOOGLE = {
    "application/vnd.google-apps.folder": ("Pasta", "📁"),
    "application/vnd.google-apps.document": ("Documento do Google", "📝"),
    "application/vnd.google-apps.spreadsheet": ("Planilha do Google", "📊"),
    "application/vnd.google-apps.presentation": ("Apresentação do Google", "📽️"),
    "application/vnd.google-apps.form": ("Formulário do Google", "📋"),
    "application/vnd.google-apps.drawing": ("Desenho do Google", "🎨"),
    "application/vnd.google-apps.script": ("Script do Google", "📋"),
    "application/vnd.google-apps.shortcut": ("Atalho", "🔗"),
    "application/vnd.google-apps.map": ("Mapa do Google", "🗺️"),
    "application/pdf": ("PDF", "📕"),
}


def _link_seguro(valor):
    """Só deixa passar endereço de site. O botão 'Abrir no Google Drive' vira o
    `href` de um link na tela: endereço com `javascript:` dentro viraria código
    rodando no navegador da pessoa. Qualquer coisa fora de http/https some."""
    endereco = str(valor or "").strip()
    if not endereco:
        return ""
    if endereco[:8].lower() == "https://" or endereco[:7].lower() == "http://":
        return endereco[:800]
    return ""


def _tipo_por_nome(nome, tem_tamanho):
    """Sem consultar o Google: adivinha o tipo pelo fim do nome do arquivo."""
    pedaco = (nome or "").rsplit(".", 1)
    if len(pedaco) == 2 and 1 <= len(pedaco[1]) <= 5:
        achado = _POR_EXTENSAO.get(pedaco[1].strip().lower())
        if achado:
            return achado
    if not tem_tamanho:
        # No Drive, só os arquivos criados dentro do Google não têm tamanho.
        return ("Arquivo do Google", "📝")
    return ("Arquivo", "📄")


def _tipo_por_mime(mime, nome):
    mime = (mime or "").strip()
    achado = _POR_TIPO_GOOGLE.get(mime)
    if achado:
        return achado
    if mime.startswith("image/"):
        return ("Imagem", "🖼️")
    if mime.startswith("video/"):
        return ("Vídeo", "🎬")
    if mime.startswith("audio/"):
        return ("Áudio", "🎵")
    if mime.startswith("text/"):
        return ("Texto", "📄")
    return _tipo_por_nome(nome, True)


def _parse_lista(saida):
    """Lê a saída do drive.py e devolve a lista já pronta pra tela."""
    itens = []
    for linha in (saida or "").splitlines():
        crua = linha.rstrip()
        if not crua.strip() or crua.strip() == "(vazio)":
            continue
        cabeca, sep, resto = crua.partition(" | ")
        if not sep:
            continue
        meio, sep2, data = resto.rpartition(" | ")
        if not sep2:
            meio, data = resto, ""
        pasta = "📁" in cabeca
        ident = cabeca.replace("📁", "").strip()
        if not _ID_OK.match(ident):
            continue
        nome = meio
        tamanho = ""
        achado = _TAM_FIM.search(meio)
        if achado:
            nome = meio[:achado.start()]
            tamanho = _tamanho_mb(achado.group(1).replace(",", "."))
        nome = nome.strip() or "(sem nome)"
        if pasta:
            tipo, icone = "Pasta", "📁"
        else:
            tipo, icone = _tipo_por_nome(nome, bool(tamanho))
        itens.append({
            "id": ident, "nome": nome, "pasta": pasta, "tipo": tipo,
            "icone": icone, "tamanho": tamanho, "data": _data_br(data),
        })
    return itens


# --------------------------------------------------------------------------
# a tela
# --------------------------------------------------------------------------

_CSS = """
.arq-busca{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.arq-busca .campo{flex:1 1 170px;min-width:0}
.arq-trilha{display:flex;flex-wrap:wrap;gap:4px;align-items:center;margin-top:10px;
  font-size:13px;color:var(--fraco)}
.arq-trilha button{background:none;border:0;padding:2px 0;font:inherit;cursor:pointer;
  color:var(--marca)}
.arq-trilha b{font-weight:600;color:var(--texto)}
.arq-item{display:flex;gap:10px;align-items:center;cursor:pointer}
.arq-ic{flex:0 0 26px;text-align:center;font-size:19px;line-height:1.2}
.arq-meio{flex:1 1 auto;min-width:0}
.arq-nome{display:block;font-weight:600;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.arq-sub{display:block;margin-top:2px;font-size:12px;color:var(--fraco)}
.arq-seta{flex:0 0 auto;color:var(--fraco);font-size:18px}
.arq-chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px}
.arq-acoes{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.arq-texto{margin:0;white-space:pre-wrap;word-break:break-word;font-size:14px;
  line-height:1.55;max-height:60vh;overflow:auto}
.arq-cab{display:flex;gap:10px;align-items:flex-start;justify-content:space-between}
.arq-cab h2{margin:0;font-size:17px;word-break:break-word}
"""

_JS = """
(function(){
  var raiz = {id:'raiz', nome:'Meu Drive'};
  var trilha = [raiz];
  var buscando = '';
  function ele(id){ return document.getElementById(id); }
  function txt(tag, classe, valor){
    var n = document.createElement(tag);
    if(classe){ n.className = classe; }
    if(valor !== undefined && valor !== null){ n.textContent = valor; }
    return n;
  }
  function vazio(frase, detalhe){
    var d = txt('div','vazio', frase);
    if(detalhe){
      var p = txt('div','fraco', 'Detalhe técnico (se precisar, é só me mandar): ' + detalhe);
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

  function pintaTrilha(){
    var alvo = ele('arqTrilha');
    alvo.innerHTML = '';
    if(buscando){
      alvo.appendChild(txt('span', null, 'Resultados da busca por '));
      alvo.appendChild(txt('b', null, buscando));
      return;
    }
    trilha.forEach(function(passo, i){
      if(i > 0){ alvo.appendChild(txt('span', null, '›')); }
      if(i === trilha.length - 1){
        alvo.appendChild(txt('b', null, passo.nome));
      } else {
        var b = txt('button', null, passo.nome);
        b.type = 'button';
        b.onclick = function(){ trilha = trilha.slice(0, i+1); abrePasta(); };
        alvo.appendChild(b);
      }
    });
  }

  function pintaLista(d){
    var lista = ele('arqLista');
    lista.innerHTML = '';
    var pastas = 0, arquivos = 0;
    if(!d.ok){
      lista.appendChild(vazio(d.erro || 'Não consegui ler o Google Drive agora.', d.detalhe));
      marcador(null, null);   // não consegui contar: '—', nunca zero
      return;
    }
    var itens = d.itens || [];
    if(!itens.length){
      lista.appendChild(vazio(buscando
        ? 'Nenhum arquivo com esse nome.'
        : 'Esta pasta está vazia.'));
      marcador(0, 0);
      return;
    }
    var caixa = txt('div','lista');
    itens.forEach(function(f){
      if(f.pasta){ pastas++; } else { arquivos++; }
      var li = txt('div','item arq-item');
      li.appendChild(txt('span','arq-ic', f.icone));
      var meio = txt('div','arq-meio');
      meio.appendChild(txt('span','arq-nome', f.nome));
      var partes = [f.tipo];
      if(f.tamanho){ partes.push(f.tamanho); }
      if(f.data){ partes.push(f.data); }
      meio.appendChild(txt('span','arq-sub', partes.join(' · ')));
      li.appendChild(meio);
      li.appendChild(txt('span','arq-seta','›'));
      li.onclick = function(){
        if(f.pasta){
          buscando = '';
          ele('arqTermo').value = '';
          trilha.push({id:f.id, nome:f.nome});
          abrePasta();
        } else {
          abreArquivo(f);
        }
      };
      caixa.appendChild(li);
    });
    lista.appendChild(caixa);
    if(d.recado){
      lista.appendChild(txt('p','fraco', d.recado));
    }
    marcador(pastas, arquivos);
  }

  function marcador(pastas, arquivos){
    ele('arqKpiPastas').textContent = (pastas === null ? '—' : pastas);
    ele('arqKpiArquivos').textContent = (arquivos === null ? '—' : arquivos);
    ele('arqKpiPastasRot').textContent = buscando
      ? (pastas === 1 ? 'pasta encontrada' : 'pastas encontradas')
      : (pastas === 1 ? 'pasta aqui' : 'pastas aqui');
    ele('arqKpiArquivosRot').textContent = buscando
      ? (arquivos === 1 ? 'arquivo encontrado' : 'arquivos encontrados')
      : (arquivos === 1 ? 'arquivo aqui' : 'arquivos aqui');
  }

  function carregando(){
    marcador(null, null);
    ele('arqLista').innerHTML = '';
    ele('arqLista').appendChild(txt('div','vazio','Carregando…'));
  }

  function abrePasta(){
    fecharPainel();
    pintaTrilha();
    carregando();
    var atual = trilha[trilha.length - 1];
    pedir('/api/arquivos/listar?pasta=' + encodeURIComponent(atual.id)).then(pintaLista);
  }

  function fazBusca(){
    var termo = (ele('arqTermo').value || '').trim();
    if(!termo){ buscando = ''; abrePasta(); return; }
    buscando = termo;
    fecharPainel();
    pintaTrilha();
    carregando();
    pedir('/api/arquivos/listar?busca=' + encodeURIComponent(termo)).then(pintaLista);
  }

  function fecharPainel(){
    var p = ele('arqPainel');
    p.innerHTML = '';
    p.hidden = true;
  }

  function abreArquivo(f){
    var p = ele('arqPainel');
    p.hidden = false;
    p.innerHTML = '';
    p.appendChild(txt('div','fraco','Abrindo…'));
    try{ window.scrollTo({top:0, behavior:'smooth'}); }catch(e){ window.scrollTo(0,0); }
    pedir('/api/arquivos/item?id=' + encodeURIComponent(f.id)).then(function(d){
      p.innerHTML = '';
      var cartao = txt('div','cartao');
      var cab = txt('div','arq-cab');
      cab.appendChild(txt('h2', null, (d.nome || f.nome)));
      var fechar = txt('button','btn','Fechar');
      fechar.type = 'button';
      fechar.onclick = fecharPainel;
      cab.appendChild(fechar);
      cartao.appendChild(cab);

      if(!d.ok){
        cartao.appendChild(vazio(d.erro || 'Não consegui abrir este arquivo.', d.detalhe));
        p.appendChild(cartao);
        return;
      }
      var chips = txt('div','arq-chips');
      [d.tipo, d.tamanho, d.data ? ('modificado em ' + d.data) : ''].forEach(function(c){
        if(c){ chips.appendChild(txt('span','chip', c)); }
      });
      cartao.appendChild(chips);

      if(d.link){
        var acoes = txt('div','arq-acoes');
        var a = txt('a','btn','Abrir no Google Drive');
        a.href = d.link; a.target = '_blank'; a.rel = 'noopener noreferrer';
        acoes.appendChild(a);
        cartao.appendChild(acoes);
      }
      p.appendChild(cartao);

      if(d.documento){
        var doc = txt('div','cartao');
        doc.appendChild(txt('div','fraco','Lendo o documento…'));
        p.appendChild(doc);
        pedir('/api/arquivos/texto?id=' + encodeURIComponent(f.id)).then(function(t){
          doc.innerHTML = '';
          if(!t.ok){
            doc.appendChild(vazio(t.erro || 'Não consegui ler o texto deste documento.',
                                  t.detalhe));
            return;
          }
          if(!(t.texto || '').trim()){
            doc.appendChild(vazio('Este documento está em branco.'));
            return;
          }
          doc.appendChild(txt('div','fraco','O texto do documento:'));
          doc.appendChild(txt('pre','arq-texto', t.texto));
        });
      } else if(d.aviso){
        var nota = txt('div','cartao');
        nota.appendChild(txt('p','fraco', d.aviso));
        p.appendChild(nota);
      }
    });
  }

  var termo = ele('arqTermo');
  ele('arqBuscar').onclick = fazBusca;
  ele('arqAtualizar').onclick = function(){ buscando ? fazBusca() : abrePasta(); };
  termo.addEventListener('keydown', function(e){
    if(e.key === 'Enter'){ e.preventDefault(); fazBusca(); }
  });
  termo.addEventListener('input', function(){
    if(!termo.value.trim() && buscando){ buscando = ''; abrePasta(); }
  });
  abrePasta();
})();
"""

_CORPO = """
<div class=cartao>
  <div class=arq-busca>
    <input class=campo id=arqTermo type=search placeholder="Procurar pelo nome do arquivo"
           autocomplete=off>
    <button class="btn primario" id=arqBuscar type=button>Buscar</button>
    <button class=btn id=arqAtualizar type=button>Atualizar</button>
  </div>
  <div class=arq-trilha id=arqTrilha></div>
</div>

<div class=kpis>
  <div class=kpi><b id=arqKpiPastas>—</b><span id=arqKpiPastasRot>pastas aqui</span></div>
  <div class=kpi><b id=arqKpiArquivos>—</b><span id=arqKpiArquivosRot>arquivos aqui</span></div>
</div>

<div id=arqPainel hidden></div>

<div class=cartao id=arqLista>
  <div class=vazio>Carregando…</div>
</div>

<p class=fraco>Aqui eu só leio: nada é enviado, apagado ou renomeado no seu Drive.</p>
<noscript><div class="aviso atencao">Esta tela precisa de um navegador com JavaScript
ligado pra mostrar seus arquivos.</div></noscript>
"""


def registra(app, casca, exige_login):

    @app.get("/arquivos")
    def tela_arquivos():
        exige_login()
        return Response(
            casca.shell("Arquivos", _CORPO, "/arquivos", css=_CSS, js=_JS),
            mimetype="text/html")

    @app.get("/api/arquivos/listar")
    def api_arquivos_listar():
        exige_login()
        try:
            busca = (request.args.get("busca") or "").strip()[:80]
            pasta = (request.args.get("pasta") or "raiz").strip()
            if busca:
                ok, saida, msg, det = _roda(casca, "drive.py", ["buscar", busca, "40"], 60)
                teto = 40
            else:
                if pasta not in ("raiz", "root") and not _ID_OK.match(pasta):
                    return jsonify({"ok": False, "itens": [],
                                    "erro": "Não reconheci esta pasta.", "detalhe": ""})
                ok, saida, msg, det = _roda(casca, "drive.py", ["listar", pasta], 60)
                teto = 200
            if not ok:
                return jsonify({"ok": False, "itens": [], "erro": msg, "detalhe": det})
            itens = _parse_lista(saida)
            recado = ""
            if len(itens) >= teto:
                recado = ("Mostrando os %d primeiros. Se o que você procura não está aqui, "
                          "use a busca pelo nome." % teto)
            return jsonify({"ok": True, "itens": itens, "erro": "", "recado": recado})
        except Exception:
            return jsonify({"ok": False, "itens": [],
                            "erro": "Não consegui montar a lista de arquivos agora.",
                            "detalhe": ""})

    @app.get("/api/arquivos/item")
    def api_arquivos_item():
        exige_login()
        try:
            ident = (request.args.get("id") or "").strip()
            if not _ID_OK.match(ident):
                return jsonify({"ok": False, "erro": "Não reconheci este arquivo."})
            ok, saida, msg, det = _roda(casca, "drive.py", ["info", ident], 60)
            if not ok:
                return jsonify({"ok": False, "erro": msg, "detalhe": det})
            try:
                dado = json.loads(saida)
            except Exception:
                return jsonify({"ok": False,
                                "erro": "O Google respondeu de um jeito que eu não entendi."})
            nome = str(dado.get("name") or "(sem nome)")
            mime = str(dado.get("mimeType") or "")
            tipo, _icone = _tipo_por_mime(mime, nome)
            documento = mime == "application/vnd.google-apps.document"
            link = _link_seguro(dado.get("webViewLink"))
            aviso = ""
            if not documento:
                # sem link não existe botão nenhum na tela: não mandar a pessoa
                # apertar um botão que ela não vai encontrar.
                aviso = ("Este arquivo eu não abro aqui dentro — dá pra ver no Google "
                         "pelo botão acima." if link else
                         "Este arquivo eu não abro aqui dentro, e o Google não me deu "
                         "um endereço pra abrir.")
            return jsonify({
                "ok": True,
                "nome": nome,
                "tipo": tipo,
                "tamanho": _tamanho_bytes(dado.get("size")) if dado.get("size") else "",
                "data": _data_br(str(dado.get("modifiedTime") or "")),
                "link": link,
                "documento": documento,
                "aviso": aviso,
            })
        except Exception:
            return jsonify({"ok": False, "erro": "Não consegui abrir este arquivo agora."})

    @app.get("/api/arquivos/texto")
    def api_arquivos_texto():
        exige_login()
        try:
            ident = (request.args.get("id") or "").strip()
            if not _ID_OK.match(ident):
                return jsonify({"ok": False, "erro": "Não reconheci este documento."})
            ok, saida, msg, det = _roda(casca, "gdoc.py", ["ler", ident], 90)
            if not ok:
                return jsonify({"ok": False, "erro": msg, "detalhe": det})
            texto = saida or ""
            linhas = texto.split("\n")
            if linhas and linhas[0].startswith("# "):
                texto = "\n".join(linhas[1:]).lstrip("\n")
            if len(texto) > 60000:
                texto = (texto[:60000] +
                         "\n\n… (o documento continua — abra no Google pra ver o resto)")
            return jsonify({"ok": True, "texto": texto})
        except Exception:
            return jsonify({"ok": False,
                            "erro": "Não consegui ler o texto deste documento agora."})
