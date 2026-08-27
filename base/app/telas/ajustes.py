#!/usr/bin/env python3
"""
Tela AJUSTES — kit nexum semente.

O que a pessoa faz aqui:
  · escolhe o tema (claro / escuro / seguir o celular) e o tamanho da letra;
  · troca a senha de entrada do app;
  · vê o nome do assistente, o nome dela e o que está ligado nesta casa;
  · sai da conta.

Só duas coisas tocam o disco:
  - LER a configuração (~/.config/semente/config.env);
  - GRAVAR a linha da senha nessa mesma configuração — reescrevendo o arquivo
    inteiro (todas as outras linhas e comentários ficam iguais), num arquivo
    temporário trocado de uma vez só (os.replace), com permissão 600.

Nenhum valor de segredo aparece na tela. Nunca.
"""

import os
import html
import time
import stat
import secrets
import tempfile

from flask import Response, request, jsonify, redirect

CHAVE = "ajustes"
TITULO = "Ajustes"
ICONE = "engrenagem"
GRUPO = "casa"
ORDEM = 90

MIN_SENHA = 8
CONFIG_PADRAO = os.path.join(os.path.expanduser("~"), ".config", "semente", "config.env")


def disponivel(cfg):
    """Ajustes existe sempre — é a tela de casa."""
    return True


# ----------------------------------------------------------------- utilidades

def _login(exige_login):
    """Chama o porteiro da casca e devolve a resposta dele, se ele devolver uma.

    Algumas cascas derrubam com 401 lá dentro; outras devolvem um redirecionamento.
    Este jeito funciona nos dois casos.
    """
    r = exige_login()
    if r is not None and hasattr(r, "status_code"):
        return r
    return None


def _igual(a, b):
    """Compara duas senhas sem entregar o tempo de resposta.

    Em texto, esta comparação recusa acento e cedilha levantando erro — e a
    pessoa que pusesse "senhã" na senha derrubava a tela. Em bytes, não.
    """
    try:
        return secrets.compare_digest(str(a).encode("utf-8"), str(b).encode("utf-8"))
    except Exception:
        return False


def _limpa(valor):
    return str(valor or "").strip().strip('"').strip("'").strip()


def _sim(valor):
    return _limpa(valor).lower() in ("sim", "s", "1", "true", "yes", "on", "ativo")


def _arquivo_config(casca):
    """Descobre onde mora a configuração, sem depender de um nome só."""
    for atributo in ("ARQ_CONFIG", "CONFIG_FILE", "ARQUIVO_CONFIG", "CONFIG", "DIR_CONFIG"):
        try:
            valor = getattr(casca, atributo, None)
        except Exception:
            valor = None
        if not valor:
            continue
        caminho = os.path.expanduser(str(valor))
        if atributo == "DIR_CONFIG" or os.path.isdir(caminho):
            caminho = os.path.join(caminho, "config.env")
        if caminho.endswith(".env"):
            return caminho
    do_ambiente = os.environ.get("SEMENTE_CONFIG", "").strip()
    if do_ambiente:
        return os.path.expanduser(do_ambiente)
    return CONFIG_PADRAO


def _le_arquivo_config(caminho):
    """Lê o config.env na mão (CHAVE=valor, # comenta). Nunca levanta erro."""
    dados = {}
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            for linha in f.read().splitlines():
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                chave, valor = linha.split("=", 1)
                dados.setdefault(chave.strip(), _limpa(valor))
    except Exception:
        return {}
    return dados


def _config(casca):
    """A configuração como dicionário — pela casca, e se ela falhar, pelo arquivo."""
    try:
        pega = getattr(casca, "config", None)
        if callable(pega):
            valor = pega()
            if isinstance(valor, dict) and valor:
                return dict(valor)
    except Exception:
        pass
    return _le_arquivo_config(_arquivo_config(casca))


def _esquece_cache(casca):
    """Depois de gravar, pede pra casca reler a configuração (se ela guardar cópia)."""
    try:
        pega = getattr(casca, "config", None)
        limpa = getattr(pega, "cache_clear", None)
        if callable(limpa):
            limpa()
    except Exception:
        pass


def _grava_senha(caminho, nova):
    """Reescreve o config.env inteiro trocando (ou acrescentando) CHAT_SENHA.

    Devolve (True, "") ou (False, "motivo em português").
    Escrita atômica: grava num arquivo temporário do MESMO diretório e troca
    com os.replace — se faltar energia no meio, o arquivo antigo continua inteiro.
    """
    # "strict" de propósito: aqui a leitura vira REESCRITA do arquivo inteiro.
    # Com tolerância, um byte estranho em outra linha seria trocado por um
    # símbolo de erro e eu apagaria calado um ajuste que não é meu.
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            original = f.read()
    except FileNotFoundError:
        return False, "não achei os ajustes desta casa."
    except Exception:
        return False, "não consegui abrir os ajustes desta casa."

    quebra_final = original.endswith("\n") or original == ""
    linhas = original.split("\n")
    if quebra_final and linhas and linhas[-1] == "":
        linhas = linhas[:-1]

    # Entre aspas simples de propósito: este arquivo também é carregado como
    # script do sistema pelas rotinas do kit. Sem as aspas, um espaço ou um
    # cifrão dentro da senha viraria COMANDO na hora de carregar.
    nova_linha = "CHAT_SENHA='" + nova + "'"
    trocou = False
    saida = []
    for linha in linhas:
        so_chave = linha.split("=", 1)[0].strip() if "=" in linha else ""
        if not linha.lstrip().startswith("#") and so_chave == "CHAT_SENHA" and not trocou:
            saida.append(nova_linha)
            trocou = True
        elif not linha.lstrip().startswith("#") and so_chave == "CHAT_SENHA":
            continue  # linha repetida da mesma chave: some (a primeira já valeu)
        else:
            saida.append(linha)
    if not trocou:
        saida.append(nova_linha)

    conteudo = "\n".join(saida) + "\n"

    pasta = os.path.dirname(os.path.abspath(caminho)) or "."
    temporario = None
    try:
        fd, temporario = tempfile.mkstemp(prefix=".config.env.", dir=pasta)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(conteudo)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporario, stat.S_IRUSR | stat.S_IWUSR)  # 600
        os.replace(temporario, caminho)
        temporario = None
        try:
            os.chmod(caminho, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass
    except Exception:
        if temporario:
            try:
                os.unlink(temporario)
            except Exception:
                pass
        return False, "não consegui guardar a senha nova nesta máquina."
    return True, ""


def _senha_viva(antiga, nova):
    """Avisa o motor do app, que está de pé, que a senha mudou.

    O motor lê a senha uma vez, quando liga. Sem este empurrão, a senha nova só
    valeria no próximo religamento — e a tela estaria mentindo pra pessoa,
    justo depois de tirar ela de dentro de casa.
    Devolve True se a troca pegou em algum lugar.
    """
    import sys
    pegou = False
    if not antiga:
        return False
    for modulo in list(sys.modules.values()):
        if modulo is None:
            continue
        try:
            valor = getattr(modulo, "SENHA", None)
        except Exception:
            continue
        if isinstance(valor, str) and valor == antiga:
            try:
                setattr(modulo, "SENHA", nova)
                pegou = True
            except Exception:
                pass
    return pegou


def _critica_senha(atual, nova, repetida, guardada):
    """As regras da senha nova, em português de gente."""
    if not guardada:
        return ("Não consegui conferir a sua senha atual aqui, então não vou mexer em nada. "
                "Me chame na conversa que eu resolvo.")
    if not atual or not _igual(atual, guardada):
        return "A senha atual não confere."
    if nova != repetida:
        return "As duas senhas novas não são iguais."
    if len(nova) < MIN_SENHA:
        return "A senha nova precisa ter pelo menos %d caracteres." % MIN_SENHA
    if nova.strip() != nova:
        return "A senha não pode começar nem terminar com espaço."
    if any(c in nova for c in "\r\n"):
        return "A senha não pode ter quebra de linha."
    if "'" in nova:
        return "Não use o sinal ' na senha — escolha outro."
    if any(ord(c) < 32 or ord(c) == 127 for c in nova):
        return "Use só letras, números e sinais comuns na senha."
    if nova == guardada:
        return "Essa já é a sua senha de agora — escolha outra."
    return ""


def _modulos(cfg):
    """O que está ligado nesta casa. Só liga/desliga — nunca o valor de um segredo."""
    return [
        ("Telegram", "falar comigo pelo celular", bool(_limpa(cfg.get("TELEGRAM_BOT_TOKEN")))),
        ("WhatsApp", "eu leio suas conversas (nunca respondo por você)", _sim(cfg.get("WHATSAPP_ATIVO"))),
        ("E-mail", "ler e preparar respostas", _sim(cfg.get("GMAIL_ATIVO"))),
        ("Agenda", "seus compromissos", _sim(cfg.get("AGENDA_ATIVO"))),
        ("Arquivos e documentos", "as pastas e documentos do Google",
         _sim(cfg.get("DRIVE_ATIVO")) or _sim(cfg.get("DRIVE_DOCS_ATIVO"))),
        ("Notícias", "o resumo do que saiu no dia", _sim(cfg.get("NEWS_ATIVO"))),
        ("Estudos", "o que você está aprendendo", _sim(cfg.get("APRENDIZADO_ATIVO"))),
        ("Gravações", "reuniões viram texto", _sim(cfg.get("GRAVACOES_ATIVO"))),
        ("Pesquisa na internet", "eu procuro coisas na web", _sim(cfg.get("PESQUISA_WEB"))),
        ("Cópia de segurança", "seu material copiado de hora em hora",
         bool(_limpa(cfg.get("REPO_GITHUB_BACKUP")))),
    ]


def _rota_de_sair(app):
    """Usa a porta de saída da casca, se existir; senão, a minha."""
    try:
        candidatas = ("/sair", "/sair/", "/logout", "/logout/", "/desconectar")
        for regra in app.url_map.iter_rules():
            caminho = str(getattr(regra, "rule", "")).lower()
            metodos = set(getattr(regra, "methods", ()) or ())
            if caminho in candidatas and "GET" in metodos:
                return str(regra.rule)
    except Exception:
        pass
    return "/ajustes/sair"


# ----------------------------------------------------------------- a tela

CSS = """
.aj-grupo{margin:14px 0 0}
.aj-grupo:first-of-type{margin-top:6px}
.aj-rot{display:block;font-size:.82rem;color:var(--fraco);margin:0 0 7px;text-transform:uppercase;letter-spacing:.04em}
.aj-ops{display:flex;flex-wrap:wrap;gap:8px}
.aj-ops .btn{flex:1 1 auto;min-width:96px;text-align:center}
.aj-info{display:flex;justify-content:space-between;align-items:baseline;gap:12px;
         padding:10px 0;border-bottom:1px solid var(--linha)}
.aj-info:last-child{border-bottom:0}
.aj-info b{font-weight:600;min-width:0;overflow-wrap:anywhere}
.aj-info span{color:var(--fraco);font-size:.9rem;flex:0 0 auto}
.aj-mod{display:flex;justify-content:space-between;align-items:center;gap:12px;
        padding:11px 0;border-bottom:1px solid var(--linha)}
.aj-mod:last-child{border-bottom:0}
.aj-mod div{min-width:0}
.aj-mod .chip{flex:0 0 auto}
.aj-mod b{display:block;font-weight:600}
.aj-mod small{display:block;color:var(--fraco);font-size:.84rem;margin-top:2px}
.aj-form{display:flex;flex-direction:column;gap:10px;margin-top:12px}
.aj-form label{font-size:.88rem;color:var(--fraco)}
.aj-form .campo{width:100%}
.aj-sair{display:block;width:100%;text-align:center;margin-top:4px}
.aj-nota{margin-top:10px}
"""

JS = """
(function(){
  var PADRAO = {tema:'auto', fonte:'1'};
  function lido(k){ try{ return localStorage.getItem('nx-'+k) || PADRAO[k]; }catch(e){ return PADRAO[k]; } }
  function pinta(){
    var bs = document.querySelectorAll('.aj-ops .btn');
    for (var i=0;i<bs.length;i++){
      var b = bs[i], k = b.getAttribute('data-k'), v = b.getAttribute('data-v');
      if (lido(k) === v) b.classList.add('primario'); else b.classList.remove('primario');
    }
  }
  /* a casca tem as duas funcoes certas, e cada uma pede O VALOR.
     Chamar sem o valor grava lixo e nao muda nada — ja aconteceu. */
  function aplica(k, v){
    var f = (k === 'tema') ? window.nxTema : window.nxFonte;
    if (typeof f === 'function'){ f(v); return true; }
    return false;
  }
  function naMao(k, v){
    try{
      if (v === PADRAO[k]) localStorage.removeItem('nx-'+k);
      else localStorage.setItem('nx-'+k, v);
    }catch(e){}
  }
  var ops = document.querySelectorAll('.aj-ops .btn');
  for (var i=0;i<ops.length;i++){
    ops[i].addEventListener('click', function(){
      var k = this.getAttribute('data-k'), v = this.getAttribute('data-v');
      if (aplica(k, v)){ pinta(); return; }
      naMao(k, v);            /* casca sem as funcoes: grava e recarrega */
      location.reload();
    });
  }
  pinta();

  var form = document.getElementById('aj-senha');
  if (form){
    var recado = document.getElementById('aj-recado');
    var botao  = document.getElementById('aj-enviar');
    function fala(texto, tipo){
      recado.className = 'aviso ' + tipo;
      recado.textContent = texto;
      recado.style.display = 'block';
    }
    form.addEventListener('submit', function(ev){
      ev.preventDefault();
      var atual = document.getElementById('aj-atual').value;
      var nova  = document.getElementById('aj-nova').value;
      var nova2 = document.getElementById('aj-nova2').value;
      if (!atual || !nova || !nova2){ fala('Preencha os três campos.', 'atencao'); return; }
      if (nova !== nova2){ fala('As duas senhas novas não são iguais.', 'atencao'); return; }
      if (nova.length < __MIN__){ fala('A senha nova precisa ter pelo menos __MIN__ caracteres.', 'atencao'); return; }
      botao.disabled = true;
      fala('Guardando...', 'atencao');
      fetch('/api/ajustes/senha', {
        method:'POST', headers:{'Content-Type':'application/json'},
        credentials:'same-origin',
        body: JSON.stringify({atual:atual, nova:nova, nova2:nova2})
      }).then(function(r){ return r.json(); }).then(function(d){
        if (d && d.ok){
          fala(d.msg || 'Senha trocada.', 'ok');
          var campos = form.querySelectorAll('input');
          for (var j=0;j<campos.length;j++){ campos[j].value=''; campos[j].disabled=true; }
          if (d.recarrega !== false) setTimeout(function(){ location.href = '/'; }, 2600);
        } else {
          botao.disabled = false;
          fala((d && d.erro) || 'Não consegui trocar a senha agora.', 'erro');
        }
      }).catch(function(){
        botao.disabled = false;
        fala('Não consegui falar com a máquina agora. Tente de novo.', 'erro');
      });
    });
  }
})();
"""


def _bloco_aparencia():
    def op(chave, valor, rotulo):
        return ('<button type=button class="btn" data-k="%s" data-v="%s">%s</button>'
                % (chave, valor, rotulo))
    return (
        '<div class=cartao>'
        '<h2>Aparência</h2>'
        '<p class=fraco>Vale só neste aparelho — no celular e no computador você pode '
        'escolher diferente.</p>'
        '<div class=aj-grupo><span class=aj-rot>Cores</span><div class=aj-ops>'
        + op("tema", "claro", "Claro")
        + op("tema", "escuro", "Escuro")
        + op("tema", "auto", "Seguir o celular")
        + '</div></div>'
        '<div class=aj-grupo><span class=aj-rot>Tamanho da letra</span><div class=aj-ops>'
        + op("fonte", "1", "Normal")
        + op("fonte", "2", "Grande")
        + '</div></div>'
        '</div>'
    )


def _bloco_identidade(cfg, leu_config):
    assistente = html.escape(_limpa(cfg.get("NOME_ASSISTENTE")))
    dono = html.escape(_limpa(cfg.get("NOME_DONO")))
    if not leu_config:
        return ('<div class=cartao><h2>Quem mora aqui</h2>'
                '<div class=vazio>Não consegui ler as configurações desta casa agora. '
                'Nada foi alterado — me conte isso na conversa que eu vejo o que houve.</div>'
                '</div>')
    if not assistente and not dono:
        return ('<div class=cartao><h2>Quem mora aqui</h2>'
                '<div class=vazio>Ainda não tem nome guardado por aqui. '
                'Me diga na conversa como você quer me chamar.</div></div>')
    linhas = []
    if assistente:
        linhas.append('<div class=aj-info><b>%s</b><span>seu assistente</span></div>' % assistente)
    if dono:
        linhas.append('<div class=aj-info><b>%s</b><span>dono da casa</span></div>' % dono)
    return ('<div class=cartao><h2>Quem mora aqui</h2>' + "".join(linhas) +
            '<p class="fraco aj-nota">Quer que eu mude de nome ou o jeito de falar? '
            'É só me pedir na conversa.</p></div>')


def _bloco_modulos(cfg, leu_config):
    if not leu_config:
        return ('<div class=cartao><h2>O que está ligado</h2>'
                '<div class=vazio>Não consegui ver o que está ligado agora.</div></div>')
    linhas = []
    for nome, explica, ligado in _modulos(cfg):
        chip = '<span class="chip ok">ligado</span>' if ligado else '<span class=chip>desligado</span>'
        linhas.append('<div class=aj-mod><div><b>%s</b><small>%s</small></div>%s</div>'
                      % (html.escape(nome), html.escape(explica), chip))
    return ('<div class=cartao><h2>O que está ligado</h2>' + "".join(linhas) +
            '<p class="fraco aj-nota">Aqui aparece só o que está ligado ou desligado — '
            'nenhuma senha ou chave sua é mostrada nesta tela, nunca. '
            'Pra ligar ou desligar algo, me peça na conversa.</p></div>')


def _bloco_senha(tem_senha):
    if not tem_senha:
        return ('<div class=cartao><h2>Senha de entrada</h2>'
                '<div class=vazio>Não achei a senha guardada nesta máquina, então não vou '
                'mexer nela por aqui. Me peça na conversa que eu acerto com segurança.</div>'
                '</div>')
    return (
        '<div class=cartao>'
        '<h2>Senha de entrada</h2>'
        '<p class=fraco>É a senha que você digita pra abrir este aplicativo. '
        'Pelo menos %d caracteres.</p>' % MIN_SENHA +
        '<div class="aviso atencao" id=aj-recado style="display:none"></div>'
        '<form class=aj-form id=aj-senha autocomplete=off>'
        '<label for=aj-atual>Senha de agora</label>'
        '<input class=campo type=password id=aj-atual autocomplete=current-password>'
        '<label for=aj-nova>Senha nova</label>'
        '<input class=campo type=password id=aj-nova autocomplete=new-password>'
        '<label for=aj-nova2>Repita a senha nova</label>'
        '<input class=campo type=password id=aj-nova2 autocomplete=new-password>'
        '<button class="btn primario" id=aj-enviar type=submit>Trocar a senha</button>'
        '</form>'
        '<p class="fraco aj-nota">Depois de trocar, você entra de novo neste aparelho. '
        'Os aparelhos onde já estava aberto continuam abertos — se quiser fechar todos, '
        'me peça na conversa.</p>'
        '</div>'
    )


def _bloco_sair(destino):
    return ('<div class=cartao>'
            '<h2>Sair</h2>'
            '<p class=fraco>Fecha a sua entrada neste aparelho. Nada é apagado.</p>'
            '<a class="btn perigo aj-sair" href="%s">Sair da minha conta</a>'
            '</div>' % html.escape(destino, quote=True))


def registra(app, casca, exige_login):

    @app.get("/ajustes")
    def tela_ajustes():
        parada = _login(exige_login)
        if parada is not None:
            return parada
        try:
            cfg = _config(casca)
        except Exception:
            cfg = {}
        leu_config = bool(cfg)
        tem_senha = bool(_limpa(cfg.get("CHAT_SENHA")))
        try:
            destino = _rota_de_sair(app)
        except Exception:
            destino = "/ajustes/sair"

        corpo = (_bloco_aparencia()
                 + _bloco_identidade(cfg, leu_config)
                 + _bloco_modulos(cfg, leu_config)
                 + _bloco_senha(tem_senha)
                 + _bloco_sair(destino))
        js = JS.replace("__MIN__", str(MIN_SENHA))
        try:
            pagina = casca.shell("Ajustes", corpo, "/ajustes", css=CSS, js=js)
        except TypeError:
            pagina = casca.shell("Ajustes", corpo, "/ajustes")
        return Response(pagina, mimetype="text/html")

    @app.post("/api/ajustes/senha")
    def api_ajustes_senha():
        parada = _login(exige_login)
        if parada is not None:
            return parada
        try:
            dados = request.get_json(silent=True) or {}
        except Exception:
            dados = {}
        atual = str(dados.get("atual") or "")
        nova = str(dados.get("nova") or "")
        nova2 = str(dados.get("nova2") or "")

        try:
            caminho = _arquivo_config(casca)
            guardado = _limpa(_le_arquivo_config(caminho).get("CHAT_SENHA"))
        except Exception:
            return jsonify(ok=False, erro="Não consegui abrir as configurações desta casa. "
                                          "Nada foi alterado."), 200

        erro = _critica_senha(atual, nova, nova2, guardado)
        if erro:
            if erro.startswith("A senha atual"):
                time.sleep(0.7)   # respiro contra tentativa em série
            return jsonify(ok=False, erro=erro), 200

        certo, motivo = _grava_senha(caminho, nova)
        if not certo:
            return jsonify(ok=False, erro="Não deu pra trocar: " + motivo +
                                          " A senha de antes continua valendo."), 200

        _esquece_cache(casca)
        valendo = _senha_viva(guardado, nova)
        if not valendo:
            # Guardei, mas quem confere a entrada ainda está com a senha velha na
            # cabeça. Fechar a porta agora deixaria a pessoa do lado de fora com
            # uma senha que ainda não vale. Então digo a verdade e não deslogo.
            return jsonify(ok=True, recarrega=False,
                           msg="Guardei a senha nova, mas ela só passa a valer quando eu "
                               "religar o aplicativo. Até lá, continue usando a de antes — "
                               "me chame na conversa que eu religo agora."), 200
        try:
            from flask import session
            session.clear()
        except Exception:
            pass
        return jsonify(ok=True, recarrega=True,
                       msg="Senha trocada. Agora entre de novo com a senha nova."), 200

    @app.get("/ajustes/sair")
    def ajustes_sair():
        parada = _login(exige_login)
        if parada is not None:
            return parada
        try:
            from flask import session
            session.clear()
        except Exception:
            pass
        return redirect("/")
