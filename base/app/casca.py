#!/usr/bin/env python3
"""
A CASCA do app (kit NEXUM Semente).

Uma receita só, usada por TODAS as telas: a barra de cima (☰ · nome · ⚙️), a
gaveta lateral, o tema claro/escuro e o embrulho da página. Tela nenhuma desenha
menu — ela entrega o miolo e a casca faz o resto.

A gaveta é DADO, não código: o servidor descobre as telas sozinho (varre telas/*.py)
e monta o menu com as que estão disponíveis. Módulo instalado depois entra sozinho.
"""
import os
import html
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_FILE = Path.home() / ".config" / "semente" / "config.env"
VERSAO = "1"          # muda quando o CSS/JS muda (fura o cache do celular)

# caminhos que as telas usam (nada fixo no meio do código delas).
# A pasta de conhecimento é ESCOLHA da pessoa (DIR_CONHECIMENTO no config) — quem
# chumbar ~/nexum aqui faz a tela ler a pasta errada em quem escolheu outra.
DIR_DADOS = BASE / "dados"


# ---------------------------------------------------------------- config
_cfg_cache = {"mtime": None, "val": {}}


def config() -> dict:
    """O ~/.config/semente/config.env lido na hora (cache por data de mudança).
    Nunca devolve exceção: arquivo faltando = dicionário vazio."""
    try:
        mt = CONFIG_FILE.stat().st_mtime
    except OSError:
        return {}
    if _cfg_cache["mtime"] != mt:
        val = {}
        try:
            for linha in CONFIG_FILE.read_text().splitlines():
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                k, v = linha.split("=", 1)
                val.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except OSError:
            val = {}
        _cfg_cache.update(mtime=mt, val=val)
    return _cfg_cache["val"]


def dir_conhecimento() -> Path:
    """A pasta de conhecimento do assistente, do jeito que a pessoa escolheu."""
    return Path(os.path.expanduser(config().get("DIR_CONHECIMENTO") or "~/nexum"))


def dir_bin() -> Path:
    """Onde moram os scripts dos módulos (o padrão do kit é ~/semente-bin)."""
    return Path(os.path.expanduser(config().get("DIR_BIN") or "~/semente-bin"))


def assistente() -> str:
    return config().get("NOME_ASSISTENTE") or "Assistente"


def dono() -> str:
    return config().get("NOME_DONO") or ""


# ---------------------------------------------------------------- ícones
def _svg(d, extra=""):
    return ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' "
            f"stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'>{d}{extra}</svg>")


ICONES = {
    "conversa": _svg("<path d='M21 12a8 8 0 0 1-8 8H7l-4 3V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8z'/>"),
    "envelope": _svg("<rect x='2.5' y='5' width='19' height='14' rx='2.5'/><path d='M3 7l9 6 9-6'/>"),
    "calendario": _svg("<rect x='3' y='5' width='18' height='16' rx='2.5'/><path d='M3 10h18'/>"
                       "<path d='M8 3v4M16 3v4'/>"),
    "pasta": _svg("<path d='M3 7.5A2 2 0 0 1 5 5.5h4l2 2.5h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5"
                  "a2 2 0 0 1-2-2z'/>"),
    "jornal": _svg("<path d='M4 5h13v14H5a1 1 0 0 1-1-1z'/><path d='M17 8h3v9a2 2 0 0 1-3 1.7'/>"
                   "<path d='M7 9h7M7 12.5h7M7 16h4'/>"),
    "microfone": _svg("<rect x='9' y='3' width='6' height='11' rx='3'/>"
                      "<path d='M5.5 11a6.5 6.5 0 0 0 13 0'/><path d='M12 17.5V21'/>"),
    "livro": _svg("<path d='M4 4.5A1.5 1.5 0 0 1 5.5 3H19v15H5.5A1.5 1.5 0 0 0 4 19.5z'/>"
                  "<path d='M4 19.5A1.5 1.5 0 0 0 5.5 21H19'/><path d='M8 7.5h7'/>"),
    "pulso": _svg("<path d='M3 12h3.8l2-5 3 10 2.4-5H21'/>"),
    "engrenagem": _svg(
        "<circle cx='12' cy='12' r='3.1'/>"
        "<path d='M19.1 14.6a1.6 1.6 0 0 0 .3 1.8l.1.1a1.9 1.9 0 1 1-2.7 2.7l-.1-.1"
        "a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5v.2a1.9 1.9 0 1 1-3.8 0v-.1"
        "a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a1.9 1.9 0 1 1-2.7-2.7l.1-.1"
        "a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1h-.2a1.9 1.9 0 1 1 0-3.8h.1"
        "a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a1.9 1.9 0 1 1 2.7-2.7l.1.1"
        "a1.6 1.6 0 0 0 1.8.3h.1a1.6 1.6 0 0 0 1-1.5v-.2a1.9 1.9 0 1 1 3.8 0v.1"
        "a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a1.9 1.9 0 1 1 2.7 2.7l-.1.1"
        "a1.6 1.6 0 0 0-.3 1.8v.1a1.6 1.6 0 0 0 1.5 1h.2a1.9 1.9 0 1 1 0 3.8h-.1"
        "a1.6 1.6 0 0 0-1.5 1z'/>"),
    "controles": _svg("<path d='M4 7h10M18 7h2M4 12h4M12 12h8M4 17h8M16 17h4'/>"
                      "<circle cx='16' cy='7' r='2'/><circle cx='10' cy='12' r='2'/>"
                      "<circle cx='14' cy='17' r='2'/>"),
    "caixa": _svg("<rect x='3' y='6' width='18' height='14' rx='2'/><path d='M3 10h18'/>"),
    "chave": _svg("<circle cx='8' cy='14' r='4'/><path d='M11 11.5 20 3'/><path d='M17 6l2.5 2.5'/>"),
    "nuvem": _svg("<path d='M7 18.5A4 4 0 0 1 7.4 10.6a5.5 5.5 0 0 1 10.5 1.6 3.6 3.6 0 0 1-.9 6.3z'/>"),
    "grafico": _svg("<path d='M4 20V4'/><path d='M4 20h16'/><path d='M8 16v-4M12.5 16V8M17 16v-6'/>"),
    "casa": _svg("<path d='M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z'/>"),
    "busca": _svg("<circle cx='11' cy='11' r='6.5'/><path d='m16 16 4.5 4.5'/>"),
    "telefone": _svg("<path d='M6.5 3.5h3l1.5 4-2 1.5a12 12 0 0 0 6 6l1.5-2 4 1.5v3a2 2 0 0 1-2.2 2"
                     "C11.5 19 5 12.5 4.5 5.7A2 2 0 0 1 6.5 3.5z'/>"),
    "raio": _svg("<path d='M13 2 4.5 13.5H11L10 22l8.5-11.5H12z'/>"),
    "escudo": _svg("<path d='M12 3.2 20 6v5.5c0 4.6-3.2 7.9-8 9.3-4.8-1.4-8-4.7-8-9.3V6z'/>"),
}
_MENU = _svg("<path d='M4 7h16M4 12h16M4 17h16'/>", "")
_VOLTA = _svg("<path d='M15 5l-7 7 7 7'/>")

# a paleta dos quadradinhos da gaveta (cicla)
_PAL = ["#2563eb", "#0d9488", "#7c3aed", "#c2410c", "#0369a1", "#be185d", "#4d7c0f"]

_GRUPOS = [("principal", ""), ("ferramentas", "Ferramentas"), ("casa", "A casa")]


def _ico(nome, classe="gi", cor=None):
    svg = ICONES.get(nome) or ICONES["caixa"]
    estilo = f" style='background:{cor}'" if cor else ""
    return f"<span class='{classe}'{estilo}>{svg}</span>"


# ---------------------------------------------------------------- gaveta
def gaveta(telas, ativo) -> str:
    """`telas` = lista de módulos de tela já filtrada pelo servidor (só as
    disponíveis), ordenada. Monta a gaveta em grupos."""
    n = [0]

    def link(t):
        cor = _PAL[n[0] % len(_PAL)]
        n[0] += 1
        on = " class=on" if getattr(t, "HREF", "/" + t.CHAVE) == ativo else ""
        href = getattr(t, "HREF", "/" + t.CHAVE)
        return (f"<a href='{href}'{on}>{_ico(t.ICONE, 'gi', cor)}"
                f"<span>{html.escape(t.TITULO)}</span></a>")

    partes = []
    for chave, rotulo in _GRUPOS:
        do_grupo = [t for t in telas if getattr(t, "GRUPO", "ferramentas") == chave]
        if not do_grupo:
            continue
        if rotulo:
            partes.append(f"<div class=ggrupo>{rotulo}</div>")
        partes.extend(link(t) for t in do_grupo)

    inicial = html.escape((assistente() or "A")[0].upper())
    return (
        "<div class=gaveta id=gaveta>"
        "<div class=gfundo data-fecha></div>"
        "<nav class=gpainel>"
        f"<div class=gmarca><span class=pt>{inicial}</span>{html.escape(assistente())}</div>"
        + "".join(partes) +
        "<div class=gpe><a href='/sair'>Sair</a></div>"
        "</nav></div>")


# ---------------------------------------------------------------- a página
def shell(titulo, corpo, ativo="", css="", js="", telas=None, voltar=None) -> str:
    """A página inteira na cara do app. `corpo` já vem como HTML pronto."""
    telas = telas if telas is not None else _TELAS_ATUAIS[0]
    esq = (f"<a class=ibtn href='{voltar}' aria-label='voltar'>{_VOLTA}</a>" if voltar
           else f"<button class=ibtn id=abregaveta aria-label='menu'>{_MENU}</button>")
    return (
        "<!doctype html><html lang=pt-BR><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'>"
        "<meta name=theme-color content='#171a1f'>"
        # tema aplicado ANTES de pintar: sem piscar claro->escuro ao abrir
        "<script>(function(){try{var d=document.documentElement;"
        "var t=localStorage.getItem('nx-tema');if(t==='claro'||t==='escuro')d.dataset.tema=t;"
        "var f=localStorage.getItem('nx-fonte');if(f==='2')d.dataset.fs=f;"
        "var e=d.dataset.tema==='escuro'||(d.dataset.tema!=='claro'&&"
        "matchMedia('(prefers-color-scheme:dark)').matches);"
        "var m=document.querySelector('meta[name=theme-color]');"
        "if(m)m.content=e?'#171a1f':'#ffffff';}catch(e){}})()</script>"
        "<link rel=manifest href='/manifest.webmanifest'>"
        "<link rel='apple-touch-icon' href='/icone.png'>"
        f"<link rel=stylesheet href='/estatico/estilo.css?v={VERSAO}'>"
        f"<title>{html.escape(titulo)} · {html.escape(assistente())}</title>"
        + (f"<style>{css}</style>" if css else "") +
        "</head><body>"
        f"<header class=appbar>{esq}"
        f"<div class=titulo>{html.escape(titulo)}</div>"
        f"<a class=ibtn href='/ajustes' aria-label='ajustes'>{ICONES['controles']}</a>"
        "</header>"
        + gaveta(telas, ativo) +
        f"<main class=area>{corpo}</main>"
        f"<script src='/estatico/app.js?v={VERSAO}'></script>"
        + (f"<script>{js}</script>" if js else "") +
        "</body></html>")


def pagina_crua(titulo, corpo, ativo="", css="", js="", telas=None) -> str:
    """Igual ao shell(), mas SEM a caixa `.area` — pra tela que manda no espaço
    todo (o chat). O miolo vira o body inteiro, embaixo da barra."""
    inteiro = shell(titulo, "@@MIOLO@@", ativo, css, js, telas)
    return inteiro.replace('<main class=area>@@MIOLO@@</main>', corpo)


# o servidor guarda aqui a lista de telas viva, pra tela nenhuma precisar passar
_TELAS_ATUAIS = [[]]


def define_telas(telas):
    _TELAS_ATUAIS[0] = telas


# atalho de leitura (o contrato promete `casca.DIR_CONHECIMENTO`); quem precisa do
# valor sempre fresco usa a função dir_conhecimento().
DIR_CONHECIMENTO = dir_conhecimento()
DIR_BIN = dir_bin()
