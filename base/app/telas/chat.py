"""
TELA: o chat — a conversa com o assistente.

A tela mora aqui; o motor (turno, streaming, memória, fila, reconciliador) mora em
nucleo/chat_motor.py e não sabe que existe navegador.
"""
import os
import re
import time
import json
import uuid
import queue
import mimetypes
from pathlib import Path

from flask import request, jsonify, Response, send_file, abort

from nucleo import chat_motor as m

CHAVE, TITULO, ICONE, GRUPO, ORDEM = "chat", "Conversa", "conversa", "principal", 10
HREF = "/chat"

BASE = Path(__file__).resolve().parent


def disponivel(cfg):
    return True         # o chat é a casa: sempre existe


def _sse(evento, dados):
    return f"event: {evento}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n"


def _conversa_json(r):
    return {"id": r["id"], "titulo": r["titulo"], "arquivado": bool(r["arquivado"]),
            "mexido_em": r["mexido_em"]}


def registra(app, casca, exige_login):
    m.comeca()

    # ---------------------------------------------------------------- a tela
    @app.get("/chat")
    def tela_chat():
        exige_login()
        html = (BASE / "chat.html").read_text()
        return Response(casca.pagina_crua("Conversa", html, "/chat"),
                        mimetype="text/html")

    # ---------------------------------------------------------------- conversas
    @app.get("/api/chat/conversas")
    def chat_conversas():
        exige_login()
        quais = request.args.get("quais", "ativas")
        onde = {"arquivadas": "excluido=0 AND arquivado=1",
                "lixeira": "excluido=1"}.get(quais, "excluido=0 AND arquivado=0")
        linhas = m.con().execute(
            f"SELECT * FROM topicos WHERE {onde} ORDER BY mexido_ts DESC LIMIT 200").fetchall()
        with m.LOCK:
            ocupados = [t for t in m.EMVOO if m.EMVOO.get(t)]
        return jsonify({"conversas": [_conversa_json(r) for r in linhas],
                        "respondendo": ocupados})

    @app.post("/api/chat/conversas")
    def chat_nova():
        exige_login()
        c = m.con()
        cur = c.execute("INSERT INTO topicos (titulo,criado_em,mexido_em,mexido_ts) "
                        "VALUES ('Nova conversa',?,?,?)",
                        (m.agora_iso(), m.agora_iso(), time.time()))
        c.commit()
        return jsonify({"id": cur.lastrowid})

    @app.get("/api/chat/conversas/<int:tid>")
    def chat_le(tid):
        exige_login()
        top = m.con().execute("SELECT * FROM topicos WHERE id=?", (tid,)).fetchone()
        if not top:
            abort(404)
        msgs = m.con().execute(
            "SELECT * FROM mensagens WHERE topico_id=? ORDER BY id", (tid,)).fetchall()
        return jsonify({
            "conversa": _conversa_json(top),
            "mensagens": [{
                "id": x["id"], "papel": x["papel"],
                "texto": x["transcricao"] or x["texto"] or "",
                "pensei": x["pensei"] or "",
                "arquivo": x["arquivo"], "arquivo_nome": x["arquivo_nome"],
                "arquivo_tipo": x["arquivo_tipo"], "quando": x["quando"],
            } for x in msgs]})

    @app.post("/api/chat/conversas/<int:tid>/titulo")
    def chat_renomeia(tid):
        exige_login()
        titulo = ((request.json or {}).get("titulo") or "").strip()[:80]
        if titulo:
            m.con().execute("UPDATE topicos SET titulo=? WHERE id=?", (titulo, tid))
            m.con().commit()
        return jsonify({"ok": True})

    @app.post("/api/chat/conversas/<int:tid>/arquivar")
    def chat_arquiva(tid):
        exige_login()
        v = 1 if (request.json or {}).get("arquivado", True) else 0
        m.con().execute("UPDATE topicos SET arquivado=? WHERE id=?", (v, tid))
        m.con().commit()
        return jsonify({"ok": True})

    @app.post("/api/chat/conversas/<int:tid>/excluir")
    def chat_exclui(tid):
        """Excluir aqui é ESCONDER, nunca apagar: a conversa sai da lista e continua
        no banco. Way of life da casa — nada se deleta, tudo se move."""
        exige_login()
        v = 0 if (request.json or {}).get("voltar") else 1
        m.con().execute("UPDATE topicos SET excluido=?, arquivado=0 WHERE id=?", (v, tid))
        m.con().commit()
        return jsonify({"ok": True})

    @app.post("/api/chat/conversas/<int:tid>/parar")
    def chat_para(tid):
        exige_login()
        return jsonify({"ok": m.para_agora(tid)})

    # ---------------------------------------------------------------- mandar
    @app.post("/api/chat/conversas/<int:tid>/mensagem")
    def chat_manda(tid):
        exige_login()
        if not m.con().execute("SELECT 1 FROM topicos WHERE id=?", (tid,)).fetchone():
            abort(404)
        texto = (request.form.get("texto") or "").strip()
        arq = request.files.get("arquivo")

        nome_disco = nome_orig = tipo = transcricao = None
        if arq and arq.filename:
            # nome GERADO, nunca o que veio do navegador (travessia de diretório)
            ext = re.sub(r"[^A-Za-z0-9.]", "", os.path.splitext(arq.filename)[1][:10])
            nome_disco = f"{uuid.uuid4().hex}{ext}"
            nome_orig = os.path.basename(arq.filename)[:120]
            tipo = (arq.mimetype or mimetypes.guess_type(nome_orig)[0]
                    or "application/octet-stream")
            arq.save(m.caminho_anexo(nome_disco))
            if tipo.startswith("audio/") or ext.lower() in (".ogg", ".webm", ".m4a",
                                                            ".mp3", ".wav"):
                tipo = tipo if tipo.startswith("audio/") else "audio/webm"
                transcricao = m.transcreve(m.caminho_anexo(nome_disco)) or None

        if not texto and not nome_disco:
            return jsonify({"erro": "mensagem vazia"}), 400

        # freio por palavra: só se a mensagem INTEIRA for a palavra (≤26 caracteres).
        # "parar de mandar e-mail pro fulano" é conteúdo, não freio.
        limpo = re.sub(r"[^a-zA-Zà-úÀ-Ú! ]", "", texto).strip().lower()
        if texto and len(texto) <= 26 and limpo in m.PARADA_PALAVRAS and not nome_disco:
            m.grava_msg(tid, "user", texto)
            m.para_agora(tid)
            return jsonify({"ok": True, "parou": True})

        mid = m.grava_msg(tid, "user", texto, arquivo=nome_disco, arquivo_nome=nome_orig,
                          arquivo_tipo=tipo, transcricao=transcricao)
        m.hub.publish(tid, "nova", {"id": mid})
        m.talvez_interrompe(tid)
        m.agenda_lote(tid)
        return jsonify({"ok": True, "id": mid, "transcricao": transcricao or ""})

    # ---------------------------------------------------------------- streaming
    @app.get("/api/chat/conversas/<int:tid>/stream")
    def chat_stream(tid):
        exige_login()

        def gen():
            q = m.hub.subscribe(tid)
            try:
                yield ": ping\n\n"                 # solta os headers na hora
                with m.LOCK:
                    f = dict(m.FASE.get(tid) or {})
                    parc = m.PARCIAL.get(tid, "")
                if f:
                    # SNAPSHOT: quem chegou agora recebe em que pé está o turno
                    yield _sse("status", {"texto": f["texto"],
                                          "desde": int((time.time() - f["t0"]) * 1000)})
                    if parc:
                        yield _sse("parcial", {"texto": parc, "n": len(parc)})
                else:
                    yield _sse("fim", {})          # limpa indicador fantasma
                while True:
                    try:
                        evento, dados = q.get(timeout=15)
                    except queue.Empty:
                        yield ": ping\n\n"         # proxy e celular derrubam ocioso
                        continue
                    yield _sse(evento, dados)
            finally:
                m.hub.unsubscribe(tid, q)

        return Response(gen(), mimetype="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",             # sem isto o proxy segura o buffer
            "Connection": "keep-alive"})

    # ---------------------------------------------------------------- anexos
    @app.get("/api/chat/anexo/<nome>")
    def chat_anexo(nome):
        exige_login()
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", nome):
            abort(404)
        caminho = m.ANEXOS / nome
        if not caminho.exists():
            abort(404)
        r = m.con().execute("SELECT arquivo_nome,arquivo_tipo FROM mensagens WHERE arquivo=?",
                            (nome,)).fetchone()
        tipo = (r["arquivo_tipo"] if r else None) or "application/octet-stream"
        if tipo.startswith(("image/", "audio/", "video/")):
            # inline e com Range: sem isso o player do celular não navega no áudio
            return send_file(caminho, mimetype=tipo, conditional=True)
        return send_file(caminho, mimetype=tipo, as_attachment=True,
                         download_name=(r["arquivo_nome"] if r else nome), conditional=True)
