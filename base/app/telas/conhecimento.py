# -*- coding: utf-8 -*-
"""Tela "Conhecimento" — o navegador da pasta de conhecimento do assistente.

Mostra, só pra leitura, a árvore de arquivos .md que o assistente escreve sobre a vida
do dono (a pasta que a pessoa escolheu, perguntada em `casca.dir_conhecimento()`).

O que ela faz:
  · anda pelas pastas, uma de cada vez, com caminho de volta;
  · abre arquivo de texto (.md renderizado, .csv em tabela, .json arrumado, .txt cru);
  · procura um trecho em todos os arquivos de texto, sem diferenciar maiúscula nem acento.

O que ela NUNCA faz: escrever, apagar, renomear, sair da pasta de conhecimento ou
mostrar arquivo que não seja texto.
"""

import csv
import html
import io
import json
import os
import re
import time
import unicodedata
from urllib.parse import quote

from flask import Response, request

CHAVE = "conhecimento"
TITULO = "Conhecimento"
ICONE = "livro"
GRUPO = "principal"
ORDEM = 30

# --- limites (a VPS é pequena; nada aqui pode virar um susto de memória) ------
EXT_TEXTO = (".md", ".txt", ".json", ".csv")
MAX_LEITURA = 400_000          # teto de leitura de um arquivo, em bytes
MAX_BUSCA_ARQUIVO = 2_000_000  # arquivo maior que isso a busca pula
MAX_RESULTADOS = 100           # teto de linhas encontradas na busca
MAX_ARQUIVOS_BUSCA = 4_000     # teto de arquivos visitados na busca
MAX_ITENS_LISTA = 500          # teto de linhas mostradas numa pasta
MAX_ITENS_RESUMO = 30_000      # teto da contagem do topo
MAX_LINHAS_CSV = 300           # teto de linhas mostradas de uma planilha
MAX_COLUNAS_CSV = 25

_SVG_PASTA = (
    '<svg viewBox="0 0 24 24" aria-hidden="true">'
    '<path d="M3 7.5A1.5 1.5 0 0 1 4.5 6h4l2 2.2h7A1.5 1.5 0 0 1 19 9.7v8.3'
    'a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 3 18z"/></svg>'
)
_SVG_ARQUIVO = (
    '<svg viewBox="0 0 24 24" aria-hidden="true">'
    '<path d="M6.5 3.5h7l4.5 4.5v12h-11.5z"/><path d="M13.5 3.5v4.5H18"/>'
    '<path d="M9 12.5h6"/><path d="M9 15.5h6"/></svg>'
)
_SVG_BUSCA = (
    '<svg viewBox="0 0 24 24" aria-hidden="true">'
    '<circle cx="11" cy="11" r="6"/><path d="M15.5 15.5 20 20"/></svg>'
)


# =============================================================================
# Ajudantes de texto e formato
# =============================================================================

def _sem_acento(txt):
    """Versão do texto sem acento e em minúscula, do mesmo TAMANHO do original.

    O tamanho igual é o que permite destacar o trecho achado na linha certa.
    """
    saida = []
    for ch in txt:
        try:
            decomposto = unicodedata.normalize("NFD", ch)
            base = decomposto[0] if decomposto else ch
        except Exception:
            base = ch
        minusculo = base.lower()
        saida.append(minusculo if len(minusculo) == 1 else base)
    return "".join(saida)


def _limpa_controle(txt):
    """Tira caracteres de controle que bagunçam a página (mantém quebra e tabulação)."""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", txt)


def _data(ts):
    try:
        return time.strftime("%d/%m/%Y", time.localtime(ts))
    except Exception:
        return "—"


def _data_hora(ts):
    try:
        return time.strftime("%d/%m/%Y às %H:%M", time.localtime(ts))
    except Exception:
        return "—"


def _tamanho(bytes_):
    try:
        b = float(bytes_)
    except Exception:
        return "—"
    if b < 1024:
        return "%d B" % int(b)
    if b < 1024 * 1024:
        return ("%.1f KB" % (b / 1024)).replace(".", ",")
    return ("%.1f MB" % (b / (1024 * 1024))).replace(".", ",")


def _numero(n):
    """1247 -> "1.247" (do jeito que se escreve em português)."""
    try:
        return "{:,}".format(int(n)).replace(",", ".")
    except Exception:
        return "0"


def _plural(n, singular, plural):
    return "%s %s" % (_numero(n), singular if n == 1 else plural)


# =============================================================================
# Caminhos — tudo que vem da URL passa por aqui
# =============================================================================

def _raiz(casca):
    """A pasta de conhecimento, já resolvida (sem link simbólico, sem '..')."""
    bruto = None
    # o contrato manda PERGUNTAR (a pessoa pode ter trocado a pasta no config);
    # o atalho `DIR_CONHECIMENTO` é foto do boot e serve só de plano B.
    try:
        pergunta = getattr(casca, "dir_conhecimento", None)
        if callable(pergunta):
            bruto = pergunta()
    except Exception:
        bruto = None
    if not bruto:
        try:
            bruto = getattr(casca, "DIR_CONHECIMENTO", None)
        except Exception:
            bruto = None
    if not bruto:
        bruto = os.path.join(os.path.expanduser("~"), "nexum")
    try:
        return os.path.realpath(os.path.expanduser(str(bruto)))
    except Exception:
        return os.path.join(os.path.expanduser("~"), "nexum")


def _dentro(raiz, alvo):
    return alvo == raiz or alvo.startswith(raiz + os.sep)


def _resolve(raiz, relativo):
    """Transforma o caminho que veio da URL em caminho real DENTRO da raiz.

    Devolve None se o caminho tenta sair da pasta de conhecimento.
    """
    rel = (relativo or "").strip()
    if "\x00" in rel:
        return None
    rel = rel.replace("\\", "/").lstrip("/")
    try:
        alvo = os.path.realpath(os.path.join(raiz, rel))
    except Exception:
        return None
    if not _dentro(raiz, alvo):
        return None
    return alvo


def _relativo(raiz, alvo):
    try:
        rel = os.path.relpath(alvo, raiz)
    except Exception:
        return ""
    return "" if rel == "." else rel.replace(os.sep, "/")


def _oculto(nome):
    return nome.startswith(".")


def _atalho_seguro(raiz, caminho):
    """Atalho (link) que aponta pra FORA da pasta de conhecimento não conta como conteúdo."""
    try:
        if not os.path.islink(caminho):
            return True
        return _dentro(raiz, os.path.realpath(caminho))
    except Exception:
        return False


def _e_texto(nome):
    return nome.lower().endswith(EXT_TEXTO)


# =============================================================================
# Leitura do disco (tudo defensivo: faltou, devolve vazio)
# =============================================================================

def _lista_pasta(raiz, caminho):
    """(pastas, arquivos, cortou, deu_erro) — cada item é (nome, tamanho, data).

    `deu_erro` separa "não consegui ler" de "está vazia": são coisas diferentes e
    a tela não pode contar uma pela outra.
    """
    pastas, arquivos = [], []
    try:
        nomes = os.listdir(caminho)
    except Exception:
        return [], [], False, True
    for nome in nomes:
        if _oculto(nome):
            continue
        cheio = os.path.join(caminho, nome)
        if not _atalho_seguro(raiz, cheio):
            continue
        try:
            st = os.stat(cheio)
        except Exception:
            continue
        if os.path.isdir(cheio):
            pastas.append((nome, None, st.st_mtime))
        elif os.path.isfile(cheio):
            arquivos.append((nome, st.st_size, st.st_mtime))
    pastas.sort(key=lambda t: _sem_acento(t[0]))
    arquivos.sort(key=lambda t: _sem_acento(t[0]))
    total = len(pastas) + len(arquivos)
    cortou = total > MAX_ITENS_LISTA
    if cortou:
        sobra = max(0, MAX_ITENS_LISTA - len(pastas))
        arquivos = arquivos[:sobra]
        pastas = pastas[:MAX_ITENS_LISTA]
    return pastas, arquivos, cortou, False


def _resumo(raiz):
    """(arquivos, pastas, última mudança, deu_erro, cortou) da árvore inteira.

    `os.walk` engole erro de leitura calado: sem o `onerror` abaixo, uma pasta que
    não abre viraria "0 arquivos" — que é mentira, não é resposta.
    """
    arquivos = pastas = 0
    ultima = 0.0
    cortou = False
    falhas = []
    try:
        for pai, dirs, arqs in os.walk(raiz, onerror=falhas.append):
            dirs[:] = [d for d in dirs
                       if not _oculto(d) and _atalho_seguro(raiz, os.path.join(pai, d))]
            pastas += len(dirs)
            for nome in arqs:
                if _oculto(nome) or not _atalho_seguro(raiz, os.path.join(pai, nome)):
                    continue
                arquivos += 1
                try:
                    mt = os.stat(os.path.join(pai, nome)).st_mtime
                    if mt > ultima:
                        ultima = mt
                except Exception:
                    pass
            if arquivos + pastas > MAX_ITENS_RESUMO:
                cortou = True
                break
    except Exception:
        return 0, 0, 0.0, True, False
    if falhas and not arquivos and not pastas:
        return 0, 0, 0.0, True, False
    return arquivos, pastas, ultima, False, cortou


def _le_texto(caminho):
    """(texto, cortou, erro). Nunca levanta exceção."""
    try:
        with open(caminho, "rb") as fh:
            bruto = fh.read(MAX_LEITURA + 1)
    except Exception:
        return "", False, "não consegui abrir este arquivo"
    cortou = len(bruto) > MAX_LEITURA
    bruto = bruto[:MAX_LEITURA]
    try:
        texto = bruto.decode("utf-8", "replace")
    except Exception:
        return "", cortou, "este arquivo não parece ser texto"
    return _limpa_controle(texto), cortou, ""


def _busca(raiz, termo):
    """Procura o trecho em todos os arquivos de texto.

    Devolve (achados, cortou, arquivos_vistos). Cada achado é
    (caminho relativo, número da linha, linha).
    """
    alvo = _sem_acento(termo)
    achados = []
    vistos = 0
    cortou = False
    if not alvo:
        return achados, False, 0
    try:
        for pai, dirs, arqs in os.walk(raiz):
            dirs[:] = sorted([d for d in dirs
                              if not _oculto(d) and _atalho_seguro(raiz, os.path.join(pai, d))],
                             key=_sem_acento)
            for nome in sorted(arqs, key=_sem_acento):
                if _oculto(nome) or not _e_texto(nome):
                    continue
                if not _atalho_seguro(raiz, os.path.join(pai, nome)):
                    continue
                if vistos >= MAX_ARQUIVOS_BUSCA:
                    cortou = True
                    return achados, cortou, vistos
                cheio = os.path.join(pai, nome)
                try:
                    if os.path.getsize(cheio) > MAX_BUSCA_ARQUIVO:
                        continue
                except Exception:
                    continue
                vistos += 1
                rel = _relativo(raiz, cheio)
                try:
                    with open(cheio, "r", encoding="utf-8", errors="replace") as fh:
                        for numero, linha in enumerate(fh, 1):
                            linha = _limpa_controle(linha.rstrip("\n"))
                            if not linha.strip():
                                continue
                            if alvo in _sem_acento(linha[:4000]):
                                achados.append((rel, numero, linha[:4000]))
                                if len(achados) >= MAX_RESULTADOS:
                                    return achados, True, vistos
                except Exception:
                    continue
    except Exception:
        pass
    return achados, cortou, vistos


# =============================================================================
# Conversor de Markdown — o texto é ESCAPADO ANTES de virar HTML
# =============================================================================

def _link(destino, rotulo, dir_rel):
    """Monta um link seguro. Endereço estranho vira texto simples."""
    d = (destino or "").strip()
    if not d:
        return rotulo or ""
    try:
        cru = html.unescape(d)
    except Exception:
        cru = d
    baixo = cru.lower()
    texto = rotulo if rotulo else d
    if baixo.startswith(("http://", "https://", "mailto:")):
        return '<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (d, texto)
    if baixo.startswith("#"):
        return texto
    primeiro = baixo.split("/")[0]
    if ":" in primeiro:            # javascript:, data:, file: ... — não vira link
        return texto
    # caminho relativo: aponta pra dentro da própria pasta de conhecimento
    try:
        limpo = cru.split("#")[0].split("?")[0]
        alvo = os.path.normpath(os.path.join(dir_rel or "", limpo)).replace(os.sep, "/")
    except Exception:
        return texto
    if not alvo or alvo == "." or alvo.startswith(".."):
        return texto
    chave = "a" if _e_texto(alvo) else "p"
    return '<a href="/conhecimento?%s=%s">%s</a>' % (chave, quote(alvo), texto)


# endereço de link: aceita UM par de parênteses dentro (Wikipédia usa muito).
# sem isso, "…/Foo_(bar)" era cortado no meio e sobrava um ")" solto na frase.
_ALVO_LINK = r"((?:[^()\s]|\([^()\s]*\))+)"
_RE_IMAGEM = r"!\[([^\]]*)\]\(\s*" + _ALVO_LINK + r"[^)]*\)"
_RE_LINK = r"\[([^\]]*)\]\(\s*" + _ALVO_LINK + r"[^)]*\)"


def _inline(txt, dir_rel=""):
    """Negrito, itálico, código, riscado e link — dentro de uma linha já escapada."""
    if not txt:
        return ""
    guardados = []

    def _guarda(m):
        guardados.append(m.group(1))
        return "\x01%d\x01" % (len(guardados) - 1)

    try:
        txt = re.sub(r"`([^`]+)`", _guarda, txt)
        txt = re.sub(_RE_IMAGEM,
                     lambda m: _link(m.group(2), m.group(1) or m.group(2), dir_rel), txt)
        txt = re.sub(_RE_LINK,
                     lambda m: _link(m.group(2), m.group(1), dir_rel), txt)
        txt = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", txt)
        txt = re.sub(r"(?<!\w)__([^_]+)__(?!\w)", r"<strong>\1</strong>", txt)
        txt = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", txt)
        txt = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", txt)
    except Exception:
        pass
    for i, guardado in enumerate(guardados):
        txt = txt.replace("\x01%d\x01" % i, "<code class=ck-cod-i>%s</code>" % guardado)
    return txt


def _celulas(linha):
    corpo = linha.strip()
    if corpo.startswith("|"):
        corpo = corpo[1:]
    if corpo.endswith("|"):
        corpo = corpo[:-1]
    return [c.strip() for c in corpo.split("|")][:MAX_COLUNAS_CSV]


def _render_blocos(linhas, dir_rel, fundo=0):
    """Converte uma lista de linhas JÁ ESCAPADAS em HTML."""
    saida = []
    paragrafo = []
    pilha = []          # listas abertas: (tag, nível)
    i, n = 0, len(linhas)

    def fecha_paragrafo():
        if paragrafo:
            saida.append("<p>" + _inline(" ".join(paragrafo), dir_rel) + "</p>")
            del paragrafo[:]

    def abre_lista(tag, nivel):
        # lista mais funda entra DENTRO do item de cima (HTML válido)
        dentro_de_item = False
        if saida and saida[-1].endswith("</li>"):
            saida[-1] = saida[-1][:-5]
            dentro_de_item = True
        saida.append("<%s>" % tag)
        pilha.append((tag, nivel, dentro_de_item))

    def fecha_uma():
        tag, _nivel, dentro_de_item = pilha.pop()
        saida.append("</%s>" % tag)
        if dentro_de_item:
            saida.append("</li>")

    def fecha_listas(nivel=-1):
        while pilha and pilha[-1][1] > nivel:
            fecha_uma()

    while i < n:
        linha = linhas[i]
        corpo = linha.strip()

        # bloco de código
        if corpo.startswith("```") or corpo.startswith("~~~"):
            marca = corpo[:3]
            fecha_paragrafo()
            fecha_listas()
            i += 1
            bloco = []
            while i < n and not linhas[i].strip().startswith(marca):
                bloco.append(linhas[i])
                i += 1
            i += 1
            saida.append("<pre class=ck-cod><code>" + "\n".join(bloco) + "</code></pre>")
            continue

        # linha em branco
        if not corpo:
            fecha_paragrafo()
            fecha_listas()
            i += 1
            continue

        # título
        titulo = re.match(r"^(#{1,6})\s+(.*)$", corpo)
        if titulo:
            fecha_paragrafo()
            fecha_listas()
            nivel = min(len(titulo.group(1)) + 1, 5)
            texto = titulo.group(2).rstrip("#").strip()
            saida.append("<h%d>%s</h%d>" % (nivel, _inline(texto, dir_rel), nivel))
            i += 1
            continue

        # linha divisória
        if re.match(r"^([-*_])\s*(\1\s*){2,}$", corpo):
            fecha_paragrafo()
            fecha_listas()
            saida.append("<hr>")
            i += 1
            continue

        # citação (o ">" já veio escapado como &gt;)
        if corpo.startswith("&gt;"):
            fecha_paragrafo()
            fecha_listas()
            bloco = []
            while i < n and linhas[i].strip().startswith("&gt;"):
                bloco.append(re.sub(r"^\s*&gt;\s?", "", linhas[i]))
                i += 1
            if fundo < 3:
                miolo = _render_blocos(bloco, dir_rel, fundo + 1)
            else:
                # chegou no fundo: mostra o texto mesmo assim — sumir com ele é pior
                miolo = "".join("<p>%s</p>" % _inline(l.strip(), dir_rel)
                                for l in bloco if l.strip())
            saida.append("<blockquote class=ck-cit>" + miolo + "</blockquote>")
            continue

        # tabela simples
        if corpo.startswith("|") and i + 1 < n:
            separador = linhas[i + 1].strip()
            if "|" in separador and re.match(r"^\|?[\s:|-]*-[\s:|-]*\|?$", separador):
                fecha_paragrafo()
                fecha_listas()
                cabecalho = _celulas(corpo)
                i += 2
                corpos = []
                while i < n and linhas[i].strip().startswith("|"):
                    corpos.append(_celulas(linhas[i]))
                    i += 1
                pedacos = ["<div class=ck-rol><table class=tabela><thead><tr>"]
                for c in cabecalho:
                    pedacos.append("<th>" + _inline(c, dir_rel) + "</th>")
                pedacos.append("</tr></thead><tbody>")
                for linha_tab in corpos:
                    pedacos.append("<tr>")
                    for c in linha_tab:
                        pedacos.append("<td>" + _inline(c, dir_rel) + "</td>")
                    pedacos.append("</tr>")
                pedacos.append("</tbody></table></div>")
                saida.append("".join(pedacos))
                continue

        # item de lista
        item = re.match(r"^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$", linha)
        if item:
            fecha_paragrafo()
            recuo = len(item.group(1).replace("\t", "  "))
            nivel = min(recuo // 2, 3)
            tag = "ul" if item.group(2) in ("-", "*", "+") else "ol"
            fecha_listas(nivel)
            if not pilha or pilha[-1][1] < nivel:
                abre_lista(tag, nivel)
            elif pilha[-1][0] != tag:
                fecha_uma()
                abre_lista(tag, nivel)
            texto = item.group(3)
            marcado = re.match(r"^\[( |x|X)\]\s+(.*)$", texto)
            if marcado:
                caixa = "☑ " if marcado.group(1).lower() == "x" else "☐ "
                texto = caixa + marcado.group(2)
            saida.append("<li>" + _inline(texto, dir_rel) + "</li>")
            i += 1
            continue

        # parágrafo comum
        fecha_listas()
        paragrafo.append(corpo)
        i += 1

    fecha_paragrafo()
    fecha_listas()
    return "".join(saida)


def _parece_ficha(linhas):
    """O bloco no topo é ficha de metadados (chave: valor) ou é conteúdo de verdade?"""
    for linha in linhas:
        corpo = linha.strip()
        if not corpo:
            continue
        return bool(re.match(r"^[\w.-]+\s*:", corpo))
    return False


def _markdown(texto, dir_rel=""):
    """Markdown → HTML legível. O conteúdo é escapado ANTES de qualquer conversão."""
    try:
        limpo = html.escape(texto.replace("\r\n", "\n").replace("\r", "\n"))
        linhas = limpo.split("\n")
        # cabeçalho de metadados no topo (--- ... ---): não é conteúdo, some
        if linhas and linhas[0].strip() == "---":
            for j in range(1, min(len(linhas), 40)):
                if linhas[j].strip() == "---":
                    # só corta se for MESMO ficha de metadados; senão eu estaria
                    # comendo conteúdo de um texto que começa com linha divisória
                    if _parece_ficha(linhas[1:j]):
                        linhas = linhas[j + 1:]
                    break
        return _render_blocos(linhas, dir_rel)
    except Exception:
        return "<pre class=ck-cod>" + html.escape(texto[:MAX_LEITURA]) + "</pre>"


def _destaca(linha, termo, largura=190):
    """Escapa a linha e marca o trecho procurado (sem acento, sem maiúscula)."""
    try:
        if not termo:
            return html.escape(linha[:largura])
        dobra_linha = _sem_acento(linha)
        dobra_termo = _sem_acento(termo)
        pos = dobra_linha.find(dobra_termo)
        if pos < 0:
            return html.escape(linha[:largura])
        inicio = max(0, pos - 55)
        fim = min(len(linha), inicio + largura)
        trecho = linha[inicio:fim]
        dobra_trecho = dobra_linha[inicio:fim]
        pedacos, j = [], 0
        while True:
            k = dobra_trecho.find(dobra_termo, j)
            if k < 0:
                pedacos.append(html.escape(trecho[j:]))
                break
            pedacos.append(html.escape(trecho[j:k]))
            pedacos.append("<mark class=ck-hit>" +
                           html.escape(trecho[k:k + len(dobra_termo)]) + "</mark>")
            j = k + len(dobra_termo)
        return ("…" if inicio > 0 else "") + "".join(pedacos) + ("…" if fim < len(linha) else "")
    except Exception:
        return html.escape(linha[:largura])


# =============================================================================
# Pedaços da página
# =============================================================================

def _cabecalho_busca(termo=""):
    return (
        '<form class="ck-busca" method="get" action="/conhecimento" role="search">'
        '<input class="campo" type="search" name="q" value="%s" '
        'placeholder="Procurar uma palavra em tudo" aria-label="Procurar">'
        '<button class="btn primario" type="submit">%s<span class=ck-so-largo>Procurar</span>'
        '</button></form>'
        % (html.escape(termo), '<span class="ck-ic ck-ic-btn">%s</span>' % _SVG_BUSCA)
    )


def _kpis(raiz):
    arquivos, pastas, ultima, erro, cortou = _resumo(raiz)
    if erro:
        # "0" aqui seria mentira: a resposta certa é "não sei".
        conta_arq = conta_pas = "—"
    else:
        mais = "+" if cortou else ""
        conta_arq = _numero(arquivos) + mais
        conta_pas = _numero(pastas) + mais
    quando = _data(ultima) if ultima else "—"
    return (
        '<div class=kpis>'
        '<div class=kpi><b>%s</b><span>arquivos</span></div>'
        '<div class=kpi><b>%s</b><span>pastas</span></div>'
        '<div class=kpi><b>%s</b><span>última mudança</span></div>'
        '</div>' % (conta_arq, conta_pas, quando)
    )


def _trilha(rel, e_arquivo=False):
    """Caminho de volta: Início / pasta / subpasta / arquivo."""
    partes = [p for p in (rel or "").split("/") if p]
    itens = ['<a href="/conhecimento">Início</a>']
    andado = ""
    for indice, parte in enumerate(partes):
        andado = (andado + "/" + parte) if andado else parte
        ultimo = indice == len(partes) - 1
        rotulo = html.escape(parte)
        if ultimo and e_arquivo:
            itens.append("<span>%s</span>" % rotulo)
        else:
            itens.append('<a href="/conhecimento?p=%s">%s</a>' % (quote(andado), rotulo))
    return '<nav class=ck-tri>' + '<span class=ck-sep>›</span>'.join(itens) + '</nav>'


def _linha_item(href, svg, classe_ic, nome, meta):
    return (
        '<a class=item href="%s" data-n="%s"><span class=ck-lin>'
        '<span class="ck-ic %s">%s</span>'
        '<span class=ck-nome>%s</span>'
        '<span class=ck-meta>%s</span>'
        '</span></a>' % (href, html.escape(_sem_acento(nome)), classe_ic, svg,
                         html.escape(nome), meta)
    )


def _corpo_pasta(raiz, caminho, rel, aviso=""):
    pastas, arquivos, cortou, erro = _lista_pasta(raiz, caminho)
    partes = [_kpis(raiz), '<div class=cartao>', _cabecalho_busca(), '</div>']
    if aviso:
        partes.append('<div class="aviso atencao">%s</div>' % aviso)
    partes.append('<div class=cartao>')
    partes.append(_trilha(rel))
    if erro:
        resumo = "não consegui ler esta pasta"
    else:
        resumo = "%s · %s" % (_plural(len(pastas), "pasta", "pastas"),
                              _plural(len(arquivos), "arquivo", "arquivos"))
    if rel:
        pai = rel.rsplit("/", 1)[0] if "/" in rel else ""
        volta = '<a class=btn href="/conhecimento?p=%s">← Voltar</a>' % quote(pai)
    else:
        volta = ""
    partes.append('<div class=ck-topo><span class=fraco>%s</span>%s</div>' % (resumo, volta))

    if not erro and len(pastas) + len(arquivos) > 10:
        partes.append('<input class="campo ck-filtro" id=ck-filtro type="search" '
                      'placeholder="Filtrar o que está nesta pasta" '
                      'aria-label="Filtrar esta pasta">')

    if erro:
        partes.append('<div class=vazio>Não consegui abrir esta pasta agora — pode ser que '
                      'ela esteja trancada pra leitura. Nada foi perdido: o que está lá '
                      'dentro continua guardado.</div>')
    elif not pastas and not arquivos:
        partes.append('<div class=vazio>Esta pasta está vazia por enquanto.</div>')
    else:
        partes.append('<div class=lista id=ck-lista>')
        for nome, _tam, mtime in pastas:
            alvo = (rel + "/" + nome) if rel else nome
            partes.append(_linha_item("/conhecimento?p=" + quote(alvo), _SVG_PASTA,
                                      "ck-pasta", nome, "pasta · " + _data(mtime)))
        for nome, tam, mtime in arquivos:
            alvo = (rel + "/" + nome) if rel else nome
            partes.append(_linha_item("/conhecimento?a=" + quote(alvo), _SVG_ARQUIVO,
                                      "ck-arq", nome,
                                      "%s · %s" % (_tamanho(tam), _data(mtime))))
        partes.append('</div>')
        partes.append('<div class=vazio id=ck-nada hidden>Nada com esse nome nesta pasta.</div>')
    if cortou:
        partes.append('<p class=fraco>Esta pasta tem muita coisa — mostrei as primeiras '
                      '%d linhas.</p>' % MAX_ITENS_LISTA)
    partes.append('</div>')
    return "".join(partes)


def _corpo_arquivo(raiz, caminho, rel):
    nome = rel.rsplit("/", 1)[-1]
    dir_rel = rel.rsplit("/", 1)[0] if "/" in rel else ""
    try:
        st = os.stat(caminho)
        meta = "%s · mudou em %s" % (_tamanho(st.st_size), _data_hora(st.st_mtime))
    except Exception:
        meta = "não consegui ver o tamanho deste arquivo"

    partes = ['<div class=cartao>', _trilha(rel, e_arquivo=True)]
    partes.append('<div class=ck-topo>'
                  '<h2 class=ck-titulo>%s</h2>'
                  '<a class=btn href="/conhecimento?p=%s">← Voltar pra pasta</a>'
                  '</div>' % (html.escape(nome), quote(dir_rel)))
    partes.append('<p class=fraco>%s</p>' % html.escape(meta))
    partes.append('</div>')

    if not _e_texto(nome):
        partes.append('<div class=cartao><div class=vazio>'
                      'Este arquivo não é de texto, então não dá pra mostrar aqui — '
                      'ele continua guardado, intacto.</div></div>')
        return "".join(partes)

    texto, cortou, erro = _le_texto(caminho)
    if erro:
        partes.append('<div class=cartao><div class=vazio>%s.</div></div>' % html.escape(erro))
        return "".join(partes)
    if not texto.strip():
        partes.append('<div class=cartao><div class=vazio>'
                      'Este arquivo está vazio.</div></div>')
        return "".join(partes)

    partes.append('<div class=cartao>')
    if cortou:
        partes.append('<div class="aviso atencao">O arquivo é grande — mostrei só '
                      'o começo dele.</div>')
    baixo = nome.lower()
    if baixo.endswith(".md"):
        partes.append('<div class=ck-doc>%s</div>' % _markdown(texto, dir_rel))
    elif baixo.endswith(".json"):
        try:
            arrumado = json.dumps(json.loads(texto), indent=2, ensure_ascii=False)
        except Exception:
            arrumado = texto
        partes.append('<pre class=ck-cod>%s</pre>' % html.escape(arrumado))
    elif baixo.endswith(".csv"):
        partes.append(_tabela_csv(texto))
    else:
        partes.append('<pre class=ck-cod>%s</pre>' % html.escape(texto))
    partes.append('</div>')
    return "".join(partes)


def _tabela_csv(texto):
    """Planilha em texto vira tabela. Deu errado, mostra do jeito que está."""
    try:
        amostra = texto[:4000]
        try:
            dialeto = csv.Sniffer().sniff(amostra, delimiters=",;\t|")
        except Exception:
            dialeto = csv.excel
        leitor = csv.reader(io.StringIO(texto), dialeto)
        linhas = []
        for numero, linha in enumerate(leitor):
            if numero > MAX_LINHAS_CSV:
                break
            linhas.append(linha[:MAX_COLUNAS_CSV])
        if not linhas:
            return '<div class=vazio>Esta planilha está vazia.</div>'
        pedacos = ['<div class=ck-rol><table class=tabela><thead><tr>']
        for celula in linhas[0]:
            pedacos.append('<th>%s</th>' % html.escape(celula))
        pedacos.append('</tr></thead><tbody>')
        for linha in linhas[1:MAX_LINHAS_CSV + 1]:
            pedacos.append('<tr>')
            for celula in linha:
                pedacos.append('<td>%s</td>' % html.escape(celula))
            pedacos.append('</tr>')
        pedacos.append('</tbody></table></div>')
        if len(linhas) > MAX_LINHAS_CSV:
            pedacos.append('<p class=fraco>Mostrei as primeiras %d linhas desta '
                           'planilha.</p>' % MAX_LINHAS_CSV)
        return "".join(pedacos)
    except Exception:
        return '<pre class=ck-cod>%s</pre>' % html.escape(texto[:MAX_LEITURA])


def _corpo_busca(raiz, termo):
    achados, cortou, vistos = _busca(raiz, termo)
    partes = [_kpis(raiz), '<div class=cartao>', _cabecalho_busca(termo), '</div>',
              '<div class=cartao>']
    partes.append('<div class=ck-topo><h2 class=ck-titulo>Resultado</h2>'
                  '<a class=btn href="/conhecimento">Limpar busca</a></div>')
    if not achados:
        partes.append('<div class=vazio>Não achei <b>%s</b> em nenhum arquivo — '
                      'procurei em %s.</div>'
                      % (html.escape(termo), _plural(vistos, "arquivo", "arquivos")))
        partes.append('</div>')
        return "".join(partes)

    partes.append('<p class=fraco>%s em %s, dentro de %s.</p>' % (
        _plural(len(achados), "linha encontrada", "linhas encontradas"),
        _plural(len(set(a[0] for a in achados)), "arquivo", "arquivos"),
        _plural(vistos, "arquivo lido", "arquivos lidos")))
    partes.append('<div class=lista>')
    for rel, numero, linha in achados:
        partes.append(
            '<a class=item href="/conhecimento?a=%s"><span class=ck-res>'
            '<span class=ck-res-topo>'
            '<span class="ck-ic ck-arq">%s</span>'
            '<span class=ck-nome>%s</span>'
            '<span class=ck-meta>linha %d</span></span>'
            '<span class=ck-trecho>%s</span></span></a>'
            % (quote(rel), _SVG_ARQUIVO, html.escape(rel), numero, _destaca(linha, termo)))
    partes.append('</div>')
    if cortou:
        partes.append('<div class="aviso atencao">Tem mais coisa: parei nas primeiras '
                      '%d linhas. Procure uma palavra mais específica pra afinar.</div>'
                      % MAX_RESULTADOS)
    partes.append('</div>')
    return "".join(partes)


def _corpo_sem_pasta(raiz):
    return (
        '<div class=cartao><div class=vazio>'
        'Ainda não existe a pasta de conhecimento — é nela que eu guardo, em arquivos de '
        'texto, o que vou aprendendo sobre você. Assim que eu escrever a primeira anotação, '
        'ela aparece aqui.'
        '</div></div>'
    )


# =============================================================================
# Estilo e comportamento
# =============================================================================

_CSS = """
.ck-topo{display:flex;gap:10px;align-items:center;justify-content:space-between;
  flex-wrap:wrap;margin:0 0 10px}
.ck-titulo{margin:0;font-size:18px;word-break:break-word}
.ck-busca{display:flex;gap:8px;width:100%}
.ck-busca .campo{flex:1;min-width:0}
.ck-busca .btn{flex:0 0 auto;display:inline-flex;align-items:center;gap:6px}
.ck-tri{display:flex;flex-wrap:wrap;align-items:center;gap:4px;font-size:13px;margin:0 0 10px}
.ck-tri a{color:var(--marca);text-decoration:none}
.ck-tri span{color:var(--fraco)}
.ck-sep{padding:0 2px}
.ck-filtro{width:100%;margin:0 0 10px}
/* `.lista .item` é display:flex e ganha do [hidden] do navegador: sem esta linha
   o filtro marcava tudo escondido e nada sumia da tela. */
.ck-lista .item[hidden]{display:none}
.ck-lin{display:flex;align-items:center;gap:10px;width:100%;min-width:0}
.ck-ic{display:inline-flex;flex:0 0 auto;width:22px;height:22px;
  align-items:center;justify-content:center;color:var(--fraco)}
.ck-ic svg{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:1.6;
  stroke-linecap:round;stroke-linejoin:round}
.ck-ic.ck-pasta{color:var(--marca)}
.ck-ic-btn{width:18px;height:18px}
.ck-ic-btn svg{width:16px;height:16px;stroke-width:2}
.ck-nome{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ck-meta{flex:0 0 auto;font-size:12px;color:var(--fraco);white-space:nowrap}
.ck-res{display:flex;flex-direction:column;gap:4px;width:100%;min-width:0}
.ck-res-topo{display:flex;align-items:center;gap:8px;min-width:0}
.ck-trecho{font-size:13px;color:var(--fraco);line-height:1.5;
  overflow-wrap:anywhere;padding-left:30px}
.ck-hit{background:var(--marca);color:var(--painel);border-radius:3px;padding:0 2px}
.ck-rol{width:100%;overflow-x:auto}
.ck-doc{line-height:1.65;overflow-wrap:anywhere}
.ck-doc h2,.ck-doc h3,.ck-doc h4,.ck-doc h5{line-height:1.3;margin:20px 0 8px}
.ck-doc h2{font-size:20px;border-bottom:1px solid var(--linha);padding-bottom:6px}
.ck-doc h3{font-size:17px}
.ck-doc h4,.ck-doc h5{font-size:15px;color:var(--fraco)}
.ck-doc>:first-child{margin-top:0}
.ck-doc p{margin:0 0 12px}
.ck-doc ul,.ck-doc ol{margin:0 0 12px;padding-left:22px}
.ck-doc li{margin:4px 0}
.ck-doc a{color:var(--marca)}
.ck-doc hr{border:0;border-top:1px solid var(--linha);margin:18px 0}
.ck-doc img{max-width:100%}
.ck-cit{margin:0 0 12px;padding:6px 0 6px 12px;border-left:3px solid var(--linha);
  color:var(--fraco)}
.ck-cit>:last-child{margin-bottom:0}
.ck-cod{background:var(--fundo);border:1px solid var(--linha);border-radius:8px;
  padding:10px 12px;overflow-x:auto;font-size:13px;line-height:1.5;margin:0 0 12px;
  white-space:pre-wrap;word-break:break-word}
.ck-cod-i{background:var(--fundo);border:1px solid var(--linha);border-radius:5px;
  padding:1px 5px;font-size:.92em}
.ck-doc table{margin:0 0 12px}
@media (max-width:420px){
  .ck-meta{font-size:11px}
  .ck-so-largo{display:none}
  .ck-trecho{padding-left:0}
}
"""

_JS = """
(function(){
  var campo=document.getElementById('ck-filtro');
  if(!campo)return;
  var lista=document.getElementById('ck-lista');
  var nada=document.getElementById('ck-nada');
  if(!lista)return;
  var itens=lista.querySelectorAll('.item');
  function limpa(t){
    try{return t.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();}
    catch(e){return t.toLowerCase();}
  }
  campo.addEventListener('input',function(){
    var alvo=limpa(campo.value.trim()),visiveis=0;
    for(var i=0;i<itens.length;i++){
      var nome=itens[i].getAttribute('data-n')||'';
      var mostra=(!alvo||nome.indexOf(alvo)>=0);
      itens[i].hidden=!mostra;
      if(mostra)visiveis++;
    }
    if(nada)nada.hidden=(visiveis>0);
  });
})();
"""


# =============================================================================
# O contrato
# =============================================================================

def disponivel(cfg):
    """A pasta de conhecimento é o coração da casa: esta tela existe sempre."""
    return True


def registra(app, casca, exige_login):

    def _pagina(corpo):
        try:
            return Response(casca.shell(TITULO, corpo, "/conhecimento", css=_CSS, js=_JS),
                            mimetype="text/html")
        except Exception:
            # se a casca reclamar de css/js, ainda assim entrega a tela
            return Response(casca.shell(TITULO, corpo, "/conhecimento"),
                            mimetype="text/html")

    @app.get("/conhecimento")
    def tela_conhecimento():
        exige_login()
        try:
            raiz = _raiz(casca)
            if not os.path.isdir(raiz):
                return _pagina(_corpo_sem_pasta(raiz))

            termo = (request.args.get("q") or "").strip()
            if termo:
                if len(termo) < 2:
                    corpo = _corpo_pasta(raiz, raiz, "",
                                         aviso="Escreva pelo menos duas letras pra eu procurar.")
                    return _pagina(corpo)
                return _pagina(_corpo_busca(raiz, termo[:120]))

            pedido_arquivo = request.args.get("a")
            if pedido_arquivo:
                alvo = _resolve(raiz, pedido_arquivo)
                if alvo is None or not os.path.isfile(alvo):
                    return _pagina(_corpo_pasta(
                        raiz, raiz, "",
                        aviso="Não achei esse arquivo — talvez ele tenha mudado de lugar. "
                              "Te trouxe pro começo."))
                return _pagina(_corpo_arquivo(raiz, alvo, _relativo(raiz, alvo)))

            pedido_pasta = request.args.get("p") or ""
            alvo = _resolve(raiz, pedido_pasta)
            if alvo is None or not os.path.isdir(alvo):
                if pedido_pasta:
                    return _pagina(_corpo_pasta(
                        raiz, raiz, "",
                        aviso="Não achei essa pasta. Te trouxe pro começo."))
                alvo = raiz
            return _pagina(_corpo_pasta(raiz, alvo, _relativo(raiz, alvo)))
        except Exception:
            return _pagina(
                '<div class=cartao><div class=vazio>'
                'Não consegui abrir o conhecimento agora. Nada foi perdido — '
                'os arquivos continuam guardados. Tente de novo daqui a pouco.'
                '</div></div>')
