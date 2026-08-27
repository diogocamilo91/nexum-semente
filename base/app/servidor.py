#!/usr/bin/env python3
"""
O MOTOR do app pessoal (kit NEXUM Semente).

Ele faz três coisas e mais nada:
  1. a porta (login por senha, sessão em cookie);
  2. descobre as telas sozinho — varre telas/*.py, importa cada uma e pergunta se
     ela está disponível nesta instalação. Módulo instalado amanhã aparece na
     gaveta amanhã, sem ninguém editar menu;
  3. serve o estático, o app de celular (PWA) e o pulso (/saude).

Configuração: ~/.config/semente/config.env   ·   Controle: ./appctl.sh
"""
import os
import re
import sys
import time
import json
import secrets
import importlib
import threading
import traceback
from pathlib import Path

from flask import (Flask, request, session, Response, redirect, send_file,
                   abort, jsonify)

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))          # pra 'import casca' e 'nucleo.*' funcionarem

import casca                            # noqa: E402

cfg = casca.config()

SENHA = cfg.get("CHAT_SENHA") or cfg.get("APP_SENHA") or ""
if not SENHA:
    sys.exit(f"ERRO: falta a senha do app em {casca.CONFIG_FILE} (chave CHAT_SENHA). "
             "O instalar.sh grava essa chave — rode ele primeiro.")
SEGREDO = cfg.get("CHAT_SEGREDO") or secrets.token_hex(32)
PORTA = int(cfg.get("CHAT_PORTA", "8800"))
DRENO = int(cfg.get("CHAT_DRENO", "120"))

app = Flask(__name__, static_folder=None)
app.secret_key = SEGREDO
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
app.permanent_session_lifetime = 60 * 60 * 24 * 365


def log(*a):
    print(time.strftime("%F %T"), *a, flush=True)


# ---------------------------------------------------------------- a porta
def logado() -> bool:
    return session.get("ok") is True


def exige_login():
    if not logado():
        abort(401)


_TENTATIVAS = {}


PAGINA_ENTRAR = """<!doctype html><html lang=pt-BR><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'>
<meta name=theme-color content='#171a1f'>
<script>(function(){try{var d=document.documentElement;
var t=localStorage.getItem('nx-tema');if(t==='claro'||t==='escuro')d.dataset.tema=t;}catch(e){}})()</script>
<link rel=stylesheet href='/estatico/estilo.css?v=__V__'>
<title>Entrar</title><style>
body{display:grid;place-items:center;min-height:100dvh}
form{width:min(92vw,330px);text-align:center}
.marca{width:56px;height:56px;border-radius:17px;background:var(--marca);color:#fff;
  display:grid;place-items:center;font-size:26px;font-weight:700;margin:0 auto 16px}
h1{font-size:19px;margin-bottom:18px}
.erro{color:var(--erro);font-size:14px;min-height:22px;margin-top:10px}
</style></head><body><form method=post action='/entrar'>
<div class=marca>__INICIAL__</div><h1>__ASSISTENTE__</h1>
<input class=campo type=password name=senha placeholder='sua senha' autofocus
 autocomplete='current-password'>
<div style='height:10px'></div>
<button class='btn primario' style='width:100%' type=submit>Entrar</button>
<div class=erro>__ERRO__</div></form></body></html>"""


def _pagina_entrar(erro=""):
    nome = casca.assistente()
    return (PAGINA_ENTRAR.replace("__ASSISTENTE__", nome)
            .replace("__INICIAL__", (nome or "A")[0].upper())
            .replace("__V__", casca.VERSAO).replace("__ERRO__", erro))


@app.post("/entrar")
def entrar():
    ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "?")).split(",")[0]
    n, ate = _TENTATIVAS.get(ip, (0, 0))
    if time.time() < ate:
        return Response(_pagina_entrar("espere um minuto"), mimetype="text/html")
    # Em bytes de propósito: comparando TEXTO, esta função recusa acento e
    # cedilha levantando erro — e uma senha com "ç" derrubava a porta com 500.
    if secrets.compare_digest(request.form.get("senha", "").encode("utf-8"),
                              str(SENHA).encode("utf-8")):
        session["ok"] = True
        session.permanent = True
        _TENTATIVAS.pop(ip, None)
        return redirect(request.args.get("de") or "/")
    n += 1
    _TENTATIVAS[ip] = (n, time.time() + 60 if n >= 5 else 0)
    return Response(_pagina_entrar("senha errada"), mimetype="text/html")


@app.get("/sair")
def sair():
    session.clear()
    return redirect("/")


@app.errorhandler(401)
def _sem_login(_e):
    if request.path.startswith("/api/"):
        return jsonify({"erro": "faça login"}), 401
    return Response(_pagina_entrar(), mimetype="text/html", status=401)


@app.errorhandler(404)
def _nao_achou(_e):
    if request.path.startswith("/api/"):
        return jsonify({"erro": "não existe"}), 404
    if not logado():
        return Response(_pagina_entrar(), mimetype="text/html", status=401)
    corpo = ("<div class=cartao><div class=vazio><span class=ico>🤷</span>"
             "<b>Essa tela não existe</b>Talvez ela ainda não tenha sido instalada."
             "<div style='margin-top:14px'><a class=btn href='/'>Voltar pro começo</a></div>"
             "</div></div>")
    return Response(casca.shell("Não achei", corpo), mimetype="text/html", status=404)


@app.errorhandler(500)
def _deu_pau(e):
    log("ERRO 500:", traceback.format_exc()[-1500:])
    if request.path.startswith("/api/"):
        return jsonify({"erro": "deu problema aqui"}), 500
    corpo = ("<div class=cartao><div class=vazio><span class=ico>⚠️</span>"
             "<b>Deu um problema nesta tela</b>"
             "Me conte no chat o que você estava fazendo que eu conserto."
             "<div style='margin-top:14px'><a class=btn href='/'>Voltar pro começo</a></div>"
             "</div></div>")
    return Response(casca.shell("Deu problema", corpo), mimetype="text/html", status=500)


# ---------------------------------------------------------------- as telas
TELAS = []


def descobre_telas():
    """Varre telas/*.py, importa cada uma e guarda as disponíveis, na ordem.
    Tela que explode ao ser importada é PULADA com aviso no log — uma tela
    quebrada nunca derruba o app inteiro."""
    achadas = []
    pasta = BASE / "telas"
    for arq in sorted(pasta.glob("*.py")):
        if arq.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"telas.{arq.stem}")
            for campo in ("CHAVE", "TITULO", "ICONE", "GRUPO", "ORDEM"):
                if not hasattr(mod, campo):
                    raise AttributeError(f"falta {campo}")
            if not mod.disponivel(cfg):
                log(f"tela {arq.stem}: fora (o módulo dela não está instalado)")
                continue
            mod.registra(app, casca, exige_login)
            achadas.append(mod)
            log(f"tela {arq.stem}: dentro")
        except Exception as e:      # noqa: BLE001
            log(f"tela {arq.stem}: PULADA — {e}")
            log(traceback.format_exc()[-800:])
    rank = {"principal": 0, "ferramentas": 1, "casa": 2}
    achadas.sort(key=lambda m: (rank.get(getattr(m, "GRUPO", "ferramentas"), 1),
                                getattr(m, "ORDEM", 999), m.TITULO))
    TELAS[:] = achadas
    casca.define_telas(achadas)
    return achadas


@app.get("/")
def comeco():
    if not logado():
        return Response(_pagina_entrar(), mimetype="text/html")
    for t in TELAS:                      # a porta de entrada é a 1ª tela do menu
        return redirect(getattr(t, "HREF", "/" + t.CHAVE))
    corpo = ("<div class=cartao><div class=vazio><span class=ico>🌱</span>"
             "<b>Ainda não tem nenhuma tela instalada</b>"
             "Assim que um módulo entrar, ele aparece aqui sozinho.</div></div>")
    return Response(casca.shell("Começo", corpo), mimetype="text/html")


# ---------------------------------------------------------------- estático / PWA
@app.get("/estatico/<nome>")
def estatico(nome):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,60}", nome):
        abort(404)
    caminho = BASE / "estatico" / nome
    if not caminho.exists():
        abort(404)
    tipo = {"css": "text/css", "js": "application/javascript",
            "png": "image/png", "svg": "image/svg+xml"}.get(nome.rsplit(".", 1)[-1], "text/plain")
    return send_file(caminho, mimetype=tipo, max_age=3600)


@app.get("/manifest.webmanifest")
def manifest():
    nome = casca.assistente()
    return jsonify({
        "id": "/", "name": nome, "short_name": nome,
        "start_url": "/", "display": "standalone", "orientation": "portrait",
        "background_color": "#0e1013", "theme_color": "#171a1f",
        "icons": [
            {"src": "/estatico/icone-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icone.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/icone.png", "sizes": "512x512", "type": "image/png",
             "purpose": "maskable"},
        ],
    })


@app.get("/sw.js")
def sw():
    # de propósito NÃO guarda nada: service worker servindo arquivo velho é um dos
    # erros mais caros que existem (você conserta e o celular continua quebrado).
    return Response("self.addEventListener('fetch',function(){});",
                    mimetype="application/javascript")


@app.get("/icone.png")
def icone():
    p = BASE / "estatico" / "icone.png"
    if p.exists():
        return send_file(p, mimetype="image/png")
    abort(404)


@app.get("/saude")
def saude():
    """Pulso simples, SEM login: serve pro vigia de fora saber se o app está vivo.
    Não conta nada sensível — só que está de pé e quantos turnos estão rodando."""
    voando = 0
    try:
        from nucleo import chat_motor
        voando = chat_motor.em_voo()
    except Exception:
        pass
    return jsonify({"ok": True, "turnos_em_voo": voando, "telas": len(TELAS)})


# ---------------------------------------------------------------- desligar
def desliga(*_):
    """Dreno CURTO: recusa turno novo e espera os em voo. Esperar demais é igual a
    não esperar — o turno morre do mesmo jeito, só que com o app fora do ar."""
    try:
        from nucleo import chat_motor
        chat_motor.DESLIGANDO.set()
        fim = time.time() + DRENO
        while time.time() < fim and chat_motor.em_voo():
            time.sleep(1)
    except Exception:
        pass
    log("saindo")
    os._exit(0)


def main():
    import signal
    signal.signal(signal.SIGTERM, desliga)
    signal.signal(signal.SIGINT, desliga)
    telas = descobre_telas()
    log(f"app do {casca.assistente()} — porta {PORTA} · {len(telas)} tela(s): "
        + ", ".join(t.CHAVE for t in telas))
    app.run(host="127.0.0.1", port=PORTA, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
