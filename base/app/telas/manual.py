#!/usr/bin/env python3
"""
Tela COMO USAR — kit nexum semente.

Texto puro, escrito pra quem nunca programou: como falar com o assistente, o que
dá pra fazer em cada lugar, o que as telas mostram, e o que fazer quando algo
der errado.

Não lê banco nem serviço. A única coisa que ela tenta ler é o nome do assistente
e o nome do dono na configuração — e, se não conseguir, usa palavras genéricas.
"""

import html

from flask import Response

CHAVE = "manual"
TITULO = "Como usar"
ICONE = "busca"
GRUPO = "casa"
ORDEM = 95


def disponivel(cfg):
    """O manual existe sempre."""
    return True


# ----------------------------------------------------------------- utilidades

def _login(exige_login):
    """Chama o porteiro da casca; devolve a resposta dele, se houver uma."""
    r = exige_login()
    if r is not None and hasattr(r, "status_code"):
        return r
    return None


def _limpa(valor):
    return str(valor or "").strip().strip('"').strip("'").strip()


def _cfg(casca):
    """A configuração desta casa. Falhou? dicionário vazio, e a vida segue."""
    try:
        pega = getattr(casca, "config", None)
        if callable(pega):
            valor = pega()
            if isinstance(valor, dict):
                return valor
    except Exception:
        pass
    return {}


def _nomes(cfg):
    """(nome do assistente, nome do dono) — vazio vira palavra genérica."""
    assistente = _limpa(cfg.get("NOME_ASSISTENTE")) or "seu assistente"
    dono = _limpa(cfg.get("NOME_DONO"))
    return assistente, dono


def _instaladas(app):
    """Quais telas existem MESMO nesta casa.

    O manual não pode ensinar caminho que não existe: tela que não foi instalada
    não registra rota nenhuma, então é a lista de rotas que diz a verdade.
    Na dúvida (não consegui olhar), devolvo vazio e o manual fala só do que é
    certo em qualquer instalação.
    """
    achadas = set()
    try:
        for regra in app.url_map.iter_rules():
            caminho = str(getattr(regra, "rule", ""))
            pedaco = caminho.strip("/").split("/")[0]
            if pedaco and pedaco != "api":
                achadas.add(pedaco)
    except Exception:
        return set()
    return achadas


# ----------------------------------------------------------------- a tela

CSS = """
.mn-intro{margin-bottom:14px}
.mn-cartao h2{margin:0 0 4px}
.mn-cartao h3{margin:16px 0 4px;font-size:1rem}
.mn-cartao p{margin:8px 0;line-height:1.55}
.mn-lista{margin:8px 0 0;padding:0;list-style:none}
.mn-lista li{padding:8px 0 8px 18px;position:relative;line-height:1.5;
             border-bottom:1px solid var(--linha)}
.mn-lista li:last-child{border-bottom:0}
.mn-lista li:before{content:"";position:absolute;left:2px;top:16px;width:6px;height:6px;
                    border-radius:50%;background:var(--marca)}
.mn-lista b{font-weight:600}
.mn-promessa{display:flex;gap:10px;align-items:flex-start;padding:10px 0;
             border-bottom:1px solid var(--linha)}
.mn-promessa:last-child{border-bottom:0}
.mn-promessa > .chip{flex:0 0 auto}
.mn-promessa > div{min-width:0}
.mn-promessa b{display:block;font-weight:600;margin-bottom:2px}
.mn-promessa span{color:var(--fraco);font-size:.92rem;line-height:1.45}
.mn-fecho{margin-top:14px}
"""


def _cartao(titulo, dentro):
    return '<div class="cartao mn-cartao"><h2>%s</h2>%s</div>' % (titulo, dentro)


def _itens(pares):
    linhas = []
    for forte, resto in pares:
        linhas.append('<li><b>%s</b> %s</li>' % (forte, resto))
    return '<ul class=mn-lista>%s</ul>' % "".join(linhas)


def _corpo(assistente, dono, tem, por_mensagem):
    a = html.escape(assistente)
    saudacao = ("Oi, %s! " % html.escape(dono)) if dono else ""

    intro = ('<div class="cartao mn-cartao mn-intro">'
             '<h2>Como usar esta casa</h2>'
             '<p>%sEsta página é o seu manual. Ela não muda nada, é só pra ler — '
             'volte aqui sempre que ficar na dúvida sobre onde clicar ou como me pedir '
             'alguma coisa.</p>'
             '<p class=fraco>Se ficar faltando alguma explicação, me peça na conversa: '
             'eu escrevo aqui do jeito que fizer sentido pra você.</p>'
             '</div>' % saudacao)

    dica_app = ('<p class=fraco>Dica: você pode instalar esta tela como aplicativo no '
                'celular (no menu do navegador, "adicionar à tela de início"). Fica com '
                'ícone igual aos outros aplicativos.</p>')
    if por_mensagem:
        portas = _cartao(
            "Os dois lugares onde a gente conversa",
            '<p>Você fala comigo por dois caminhos. Os dois são eu — a mesma memória, '
            'o mesmo jeito. Muda só o momento em que cada um serve melhor.</p>'
            '<h3>No celular, por mensagem</h3>'
            '<p>É o bolso: recado rápido, um áudio na rua, uma foto de um papel, uma dúvida '
            'de dez segundos. Cada assunto vive na sua própria conversa, então dá pra ter '
            'um assunto de trabalho e outro de casa sem misturar.</p>'
            '<h3>Aqui, na tela de conversa</h3>'
            '<p>É a mesa de trabalho: assunto comprido, documento pra ler junto, print pra '
            'eu olhar, resposta longa pra você ler com calma. É o melhor lugar quando a '
            'coisa vai demorar mais que um minuto.</p>' + dica_app)
    else:
        portas = _cartao(
            "Onde a gente conversa",
            '<p>Por enquanto a gente se fala por aqui mesmo, na tela de conversa: assunto '
            'comprido, documento pra ler junto, print pra eu olhar, resposta longa pra '
            'você ler com calma.</p>'
            '<p>Se você quiser também falar comigo por mensagem no celular, é só me pedir '
            'na conversa que eu monto isso.</p>' + dica_app)

    chat = _cartao(
        "O que dá pra fazer na conversa",
        _itens([
            ("Escrever.", "Fale comigo como falaria com uma pessoa. Não precisa de "
                          "palavra técnica nem de comando: frase normal serve."),
            ("Mandar áudio.", "Aperte o microfone e fale. Eu escuto, entendo e "
                              "respondo — vale muito quando você está dirigindo ou "
                              "com pressa."),
            ("Mandar foto.", "Foto de um papel, de uma etiqueta, de uma conta, de um "
                             "aviso. Eu leio o que está escrito na imagem."),
            ("Colar um print.", "Copiou a imagem na tela do computador? Cole direto "
                                "aqui dentro da conversa que ela sobe sozinha."),
            ("Anexar um arquivo.", "Um documento, uma planilha, um PDF. Eu abro e "
                                   "trabalho em cima dele."),
            ("Arquivar a conversa.", "Terminou o assunto? Arquive. Ele sai da sua "
                                     "frente e continua guardado, do jeitinho que ficou."),
            ("Mandar parar.", "Se eu estiver demorando demais ou indo pro caminho "
                              "errado, é só dizer pra parar — eu paro na hora, sem "
                              "estragar nada."),
        ]) +
        '<p class=fraco>Se a resposta ficar comprida demais ou técnica demais, diga '
        '"me explica mais simples". Isso não me ofende — me ajuda.</p>')

    conhecimento = "" if not tem("conhecimento") else _cartao(
        "A tela de Conhecimento",
        '<p>É a minha memória sobre você, escrita em português e aberta pra você ler. '
        'Cada assunto vira uma página: seu trabalho, suas preferências, decisões que a '
        'gente já tomou, o que você me ensinou.</p>'
        '<p>Serve pra três coisas: <b>procurar</b> algo que você já me contou e não '
        'lembra mais, <b>conferir</b> se eu entendi certo, e <b>corrigir</b> quando eu '
        'entendi errado. Achou uma bobagem escrita lá? Me diga na conversa — eu conserto '
        'e a página fica certa dali em diante.</p>'
        '<p class=fraco>Nada aí é segredo pra você: é tudo seu, guardado na sua máquina.</p>')

    casa = "" if not tem("casa") else _cartao(
        "A tela da Casa",
        '<p>É o painel de saúde: mostra se está tudo de pé, o que roda sozinho todo dia '
        'e há quanto tempo cada coisa funcionou pela última vez.</p>'
        '<p>Você não precisa acompanhar isso — se algo cair, <b>eu te aviso</b>. A tela '
        'existe pra quando você quiser olhar com os próprios olhos, ou quando eu te '
        'disser "dá uma olhada ali".</p>')

    excluir = _cartao(
        "Excluir aqui é esconder",
        '<p>Quando você apaga uma conversa, uma anotação ou um item de lista nesta casa, '
        'a coisa <b>sai da sua vista, mas não some</b>. Ela fica guardada, marcada como '
        'escondida.</p>'
        '<p>É de propósito: assim você limpa a tela sem medo de perder algo importante. '
        'Mudou de ideia daqui a um mês? Me peça pra procurar o que você escondeu — eu '
        'acho e trago de volta.</p>')

    promessas = _cartao(
        "As minhas três promessas",
        '<div class=mn-promessa><span class="chip ok">1</span><div>'
        '<b>Nunca apago nada.</b>'
        '<span>Eu movo, arquivo, escondo, reorganizo — apagar, não. O que é seu fica.</span>'
        '</div></div>'
        '<div class=mn-promessa><span class="chip ok">2</span><div>'
        '<b>Nada sai daqui sem o seu ok.</b>'
        '<span>Nenhum e-mail, nenhuma mensagem, nenhuma resposta pra outra pessoa é '
        'enviada sem você ler o texto antes e dizer "pode mandar".</span>'
        '</div></div>'
        '<div class=mn-promessa><span class="chip ok">3</span><div>'
        '<b>Os seus dados ficam aqui.</b>'
        '<span>O que é seu fica guardado nesta máquina, que é sua — não vira produto '
        'de ninguém nem é vendido pra ninguém. O que você me escreve passa pelo serviço '
        'que me faz pensar, no instante em que eu respondo; fora isso, nada sai daqui.</span>'
        '</div></div>'
        '<p class="fraco mn-fecho">Essas três não mudam nunca — nem se você me pedir num '
        'dia de pressa.</p>')

    erro = _cartao(
        "Quando alguma coisa der errado",
        '<p>Uma tela em branco, um botão que não responde, uma mensagem esquisita com '
        'um monte de palavra em inglês: nada disso é culpa sua e nada disso quebra a '
        'sua casa.</p>'
        '<p><b>Me cole o erro na conversa que eu conserto.</b> Se for mais fácil, tire '
        'um print e mande a imagem — pra mim serve igual. Diga também o que você estava '
        'fazendo na hora; isso encurta metade do caminho.</p>'
        '<p>E se eu é que estiver estranho — respondendo devagar, sumido, repetindo '
        'coisa —, me pergunte direto: "está tudo bem por aí?". Eu olho a máquina e te '
        'conto o que achei.</p>'
        '<p class=fraco>Quer mudar meu jeito de responder, ligar algo que ficou de fora '
        'ou mudar o horário de alguma coisa? É só pedir. Esta casa é sua; eu só moro '
        'aqui.</p>')

    assinatura = ('<div class="cartao mn-cartao"><p class=fraco>Manual do %s — '
                  'atualizado sempre que a gente muda alguma coisa por aqui.</p></div>' % a)

    return intro + portas + chat + conhecimento + casa + excluir + promessas + erro + assinatura


def registra(app, casca, exige_login):

    @app.get("/manual")
    def tela_manual():
        parada = _login(exige_login)
        if parada is not None:
            return parada
        try:
            cfg = _cfg(casca)
            assistente, dono = _nomes(cfg)
        except Exception:
            cfg, assistente, dono = {}, "seu assistente", ""
        try:
            existe = _instaladas(app)
            # sem lista de rotas eu não invento: conto do que é certo em toda casa
            tem = (lambda chave: chave in existe) if existe else (lambda chave: False)
            por_mensagem = bool(_limpa(cfg.get("TELEGRAM_BOT_TOKEN")))
            corpo = _corpo(assistente, dono, tem, por_mensagem)
        except Exception:
            corpo = ('<div class=cartao><h2>Como usar</h2>'
                     '<div class=vazio>Não consegui montar o manual agora. '
                     'Me avise na conversa que eu arrumo.</div></div>')
        try:
            pagina = casca.shell("Como usar", corpo, "/manual", css=CSS, js="")
        except TypeError:
            pagina = casca.shell("Como usar", corpo, "/manual")
        return Response(pagina, mimetype="text/html")
