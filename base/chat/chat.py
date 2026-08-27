#!/usr/bin/env python3
"""
CHAT WEB do assistente — kit NEXUM Semente.

O que e: um chat no navegador (celular + PC) que conversa com o Claude Code desta
maquina. Resposta saindo ao vivo, memoria por conversa, audio, imagem, anexo,
arquivar e excluir. Feito pra VPS pequena (2 nucleos / 2 GB de RAM).

A REGRA-MAE (todo o resto e consequencia dela):
    todo estado do turno tem que sobreviver a (1) a pessoa fechar a tela
    e (2) este servico reiniciar.
Por isso a "fase" e a "parcial" moram AQUI no servidor (nao no navegador), o
cronometro e ancorado na hora da mensagem GRAVADA NO BANCO, e existe um
reconciliador de orfaos no boot — com freio.

Configuracao: ~/.config/semente/config.env  (nada fixo no codigo)
Controle:     ./chatctl.sh {start|stop|restart|status|log}
"""

import os
import re
import sys
import json
import time
import uuid
import queue
import sqlite3
import secrets
import threading
import subprocess
import mimetypes
import shutil
from datetime import datetime
from pathlib import Path

from flask import (Flask, request, session, jsonify, Response, send_file,
                   redirect, abort)

BASE = Path(__file__).resolve().parent
DADOS = BASE / "dados"
ANEXOS = DADOS / "anexos"
DB = DADOS / "chat.db"
CONFIG_FILE = Path.home() / ".config" / "semente" / "config.env"

DADOS.mkdir(parents=True, exist_ok=True)
ANEXOS.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- configuracao
def load_config() -> dict:
    """Le a config unica do kit. Formato CHAVE=valor, # comenta."""
    cfg = {}
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return cfg


cfg = load_config()

SENHA = cfg.get("CHAT_SENHA", "")
if not SENHA:
    sys.exit(f"ERRO: CHAT_SENHA nao encontrada em {CONFIG_FILE}. "
             "O instalar.sh grava essa chave — rode ele primeiro.")
SEGREDO = cfg.get("CHAT_SEGREDO") or secrets.token_hex(32)
PORTA = int(cfg.get("CHAT_PORTA", "8800"))
ASSISTENTE = cfg.get("NOME_ASSISTENTE", "Assistente")
DONO = cfg.get("NOME_DONO", "")
WORKDIR = os.path.expanduser(cfg.get("DIR_CONHECIMENTO", "~/nexum"))
CLAUDE = (os.path.expanduser(cfg.get("CLAUDE_BIN", ""))
          or shutil.which("claude")
          or os.path.expanduser("~/.local/bin/claude"))

# transcritor de audio: reusa o Whisper que o modulo do Telegram ja instalou
# (o modelo tem ~460 MB — baixar duas vezes numa VPS de 2 GB seria desperdicio).
BOT_DIR = Path(os.path.expanduser(cfg.get("DIR_BOT", "~/semente-bot")))
TRANSCRIBE_PY = BOT_DIR / "transcribe.py"
TRANSCRIBE_VENV = BOT_DIR / "venv" / "bin" / "python"

MAX_TURNOS = int(cfg.get("CHAT_MAX_TURNOS", cfg.get("MAX_CONCORRENTES", "2")))
DEBOUNCE = float(cfg.get("CHAT_DEBOUNCE", "1.8"))   # s de silencio antes de rodar o lote
MUDO_MAX = int(cfg.get("CHAT_MUDO_MAX", "600"))     # s sem NENHUMA saida -> travou
TETO_TURNO = int(cfg.get("CHAT_TETO_TURNO", "3600"))  # s no total -> fusivel
RECONCILIA_IDADE = 30 * 60                          # s: turno mais velho que isso nao volta
RECONCILIA_TENTATIVAS = 2                           # o freio (erro nº 2 do cemiterio)
DRENO = int(cfg.get("CHAT_DRENO", "120"))           # s de dreno no desligamento

VERSAO = "1.0"

PARADA_PALAVRAS = {"parar", "para", "pare", "para!", "cancela", "cancelar",
                   "chega", "stop", "para tudo"}

TITLE_PROMPT = (
    "Voce vai dar nome a uma conversa. Com base na mensagem abaixo, escreva um TITULO "
    "curto (3 a 5 palavras), em portugues, sem aspas e sem ponto final, que resuma o "
    "assunto. Voce esta CEGO: nao abre link, nao le arquivo, nao ve anexo — se a "
    "mensagem for so um link ou um arquivo, invente um titulo pelo que da pra ler. "
    "Responda APENAS o titulo, mais nada.\n\nMensagem:\n"
)


def agora_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log(*a):
    print(datetime.now().strftime("%F %T"), *a, flush=True)


# ---------------------------------------------------------------- banco
_local = threading.local()


def con() -> sqlite3.Connection:
    c = getattr(_local, "con", None)
    if c is None:
        c = sqlite3.connect(DB, check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=30000")
        _local.con = c
    return c


def init_db():
    c = con()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS topicos (
      id INTEGER PRIMARY KEY,
      titulo TEXT NOT NULL DEFAULT 'Nova conversa',
      session_id TEXT,
      arquivado INTEGER NOT NULL DEFAULT 0,
      excluido  INTEGER NOT NULL DEFAULT 0,
      criado_em TEXT, mexido_em TEXT, mexido_ts REAL);
    CREATE TABLE IF NOT EXISTS mensagens (
      id INTEGER PRIMARY KEY,
      topico_id INTEGER NOT NULL REFERENCES topicos(id),
      papel TEXT NOT NULL,              -- 'user' | 'assistant' | 'sistema'
      texto TEXT, pensei TEXT,          -- resposta e rascunho: campos SEPARADOS
      arquivo TEXT, arquivo_nome TEXT, arquivo_tipo TEXT,
      transcricao TEXT,
      quando TEXT, ts REAL);
    CREATE INDEX IF NOT EXISTS ix_msg_top ON mensagens(topico_id, id);
    CREATE TABLE IF NOT EXISTS reconcile_log (
      topico_id INTEGER PRIMARY KEY, ult_msg_id INTEGER, tentativas INTEGER DEFAULT 0);
    """)
    c.commit()


def grava_msg(tid, papel, texto="", pensei="", arquivo=None,
              arquivo_nome=None, arquivo_tipo=None, transcricao=None) -> int:
    c = con()
    cur = c.execute(
        "INSERT INTO mensagens (topico_id,papel,texto,pensei,arquivo,arquivo_nome,"
        "arquivo_tipo,transcricao,quando,ts) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (tid, papel, texto, pensei, arquivo, arquivo_nome, arquivo_tipo,
         transcricao, agora_iso(), time.time()))
    c.execute("UPDATE topicos SET mexido_em=?, mexido_ts=? WHERE id=?",
              (agora_iso(), time.time(), tid))
    c.commit()
    return cur.lastrowid


def pendentes(tid):
    """As mensagens do DONO na cauda (sem resposta depois). E o lote do proximo turno."""
    linhas = con().execute(
        "SELECT * FROM mensagens WHERE topico_id=? ORDER BY id DESC LIMIT 40",
        (tid,)).fetchall()
    fila = []
    for m in linhas:
        if m["papel"] in ("assistant", "sistema"):
            break
        fila.append(m)
    return list(reversed(fila))


# ---------------------------------------------------------------- hub de eventos (SSE)
class Hub:
    """Um canal por conversa. Quem esta com a tela aberta assina; o turno publica."""

    def __init__(self):
        self.assinantes = {}
        self.lock = threading.Lock()

    def subscribe(self, tid):
        q = queue.Queue()
        with self.lock:
            self.assinantes.setdefault(tid, []).append(q)
        return q

    def unsubscribe(self, tid, q):
        with self.lock:
            if q in self.assinantes.get(tid, []):
                self.assinantes[tid].remove(q)

    def publish(self, tid, evento, dados):
        with self.lock:
            alvos = list(self.assinantes.get(tid, []))
        for q in alvos:
            q.put((evento, dados))


hub = Hub()

# --- o estado do turno, NO SERVIDOR (é o que faz o sair-e-voltar existir) ------
LOCK = threading.RLock()
FASE = {}      # tid -> {"texto": str, "t0": epoch}   a fase corrente e desde quando
PARCIAL = {}   # tid -> str                            tudo que ja foi streamado
EMVOO = {}     # tid -> Turno                          o turno rodando agora
PENDENTE = set()   # tids com mensagem esperando o turno atual acabar
PARTINDO = set()   # tids com turno ja admitido mas ainda nao rodando (trava da largada)
TIMERS = {}    # tid -> threading.Timer                o debounce
CORTE = set()  # tids cujo ultimo turno foi cortado antes de escrever
VAGAS = threading.Semaphore(MAX_TURNOS)
DESLIGANDO = threading.Event()

FASES_AMIGAVEIS = {
    "Read": "lendo um arquivo", "Write": "escrevendo um arquivo",
    "Edit": "editando um arquivo", "Bash": "rodando um comando",
    "Grep": "procurando", "Glob": "procurando arquivos",
    "WebFetch": "abrindo uma pagina", "WebSearch": "pesquisando na internet",
    "Task": "chamando um ajudante", "TodoWrite": "organizando as tarefas",
}


class Turno:
    def __init__(self, tid):
        self.tid = tid
        self.proc = None
        self.escreveu = False      # ja mandou texto pra tela? (trava do "interromper")
        self.parar = False         # a pessoa mandou parar
        self.interrompido = False  # chegou mensagem nova antes de escrever


def fase_set(tid, texto, t0=None):
    with LOCK:
        atual = FASE.get(tid)
        FASE[tid] = {"texto": texto, "t0": t0 or (atual or {}).get("t0") or time.time()}
        d = dict(FASE[tid])
    hub.publish(tid, "status", {"texto": d["texto"], "desde": int((time.time() - d["t0"]) * 1000)})


def fase_limpa(tid):
    with LOCK:
        FASE.pop(tid, None)
        PARCIAL.pop(tid, None)


def parcial_soma(tid, trecho) -> int:
    with LOCK:
        PARCIAL[tid] = PARCIAL.get(tid, "") + trecho
        return len(PARCIAL[tid])


# ---------------------------------------------------------------- o prompt do lote
def caminho_anexo(nome_disco) -> str:
    return str(ANEXOS / nome_disco)


def monta_prompt(tid, msgs, frio=False) -> str:
    """Monta o texto do turno a partir das mensagens do lote."""
    top = con().execute("SELECT titulo FROM topicos WHERE id=?", (tid,)).fetchone()
    titulo = top["titulo"] if top else "conversa"
    cab = [f"[origem: chat web · conversa \"{titulo}\" (#{tid})]"]
    if tid in CORTE:
        cab.append("[aviso: o turno anterior foi cortado antes de voce responder — "
                   "aquela fala do dono ficou sem resposta e nao entrou no seu historico]")
        CORTE.discard(tid)
    if frio:
        cab.append("[aviso: a memoria desta conversa se perdeu; voce esta recomecando "
                   "do zero neste assunto]")
    corpo = []
    for m in msgs:
        texto = (m["transcricao"] or m["texto"] or "").strip()
        if m["arquivo"]:
            cam = caminho_anexo(m["arquivo"])
            tipo = (m["arquivo_tipo"] or "")
            rotulo = m["arquivo_nome"] or m["arquivo"]
            if tipo.startswith("image/"):
                corpo.append(f"[o dono mandou uma IMAGEM: {cam} — ABRA essa imagem "
                             f"(sua ferramenta de leitura enxerga imagens) e trate como "
                             f"parte da mensagem]")
            elif tipo.startswith("audio/"):
                if (m["transcricao"] or "").strip():
                    corpo.append("[o dono mandou um AUDIO; a transcricao esta abaixo]")
                else:
                    corpo.append(f"[o dono mandou um AUDIO e a transcricao FALHOU. O "
                                 f"arquivo esta em {cam} — diga a ele que nao consegui "
                                 f"ouvir e peca pra repetir por escrito]")
            else:
                corpo.append(f"[o dono anexou o arquivo \"{rotulo}\": {cam} — abra se "
                             f"precisar]")
        if texto:
            corpo.append(texto)
    return "\n".join(cab) + "\n\n" + "\n\n".join(corpo).strip()


# ---------------------------------------------------------------- o turno (o coracao)
class RespostaVazia(Exception):
    pass


class ResumeMorreu(Exception):
    pass


def roda_claude(turno, prompt, sid):
    """Roda o claude uma vez. Devolve (resposta, pensei, novo_sid, houve_conteudo)."""
    tid = turno.tid
    cmd = [CLAUDE, "-p", prompt,
           "--output-format", "stream-json", "--verbose",
           "--permission-mode", "bypassPermissions"]
    if sid:
        cmd += ["--resume", sid]
    proc = subprocess.Popen(cmd, cwd=WORKDIR, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, bufsize=1)
    turno.proc = proc

    resposta, pensei, erro = [], [], []
    novo_sid, houve = sid, False
    ultimo = time.time()
    fim_absoluto = time.time() + TETO_TURNO
    morto = {"por": None}

    def le_erro():
        for l in proc.stderr:
            erro.append(l)

    threading.Thread(target=le_erro, daemon=True).start()

    def vigia():
        """Silencio NAO e prova de trabalho travado — mas silencio LONGO demais é."""
        while proc.poll() is None:
            time.sleep(5)
            if turno.parar:
                return
            if time.time() - ultimo > MUDO_MAX:
                morto["por"] = f"ficou {MUDO_MAX // 60} min sem dar nenhum sinal"
                proc.kill()
                return
            if time.time() > fim_absoluto:
                morto["por"] = f"passou de {TETO_TURNO // 3600}h"
                proc.kill()
                return

    threading.Thread(target=vigia, daemon=True).start()

    for linha in proc.stdout:
        ultimo = time.time()
        try:
            ev = json.loads(linha)
        except ValueError:
            continue
        if ev.get("session_id"):
            novo_sid = ev["session_id"]
        for bloco in (ev.get("message") or {}).get("content", []) or []:
            t = bloco.get("type")
            if t == "text":
                trecho = bloco.get("text") or ""
                if not trecho:
                    continue
                houve = True
                turno.escreveu = True
                resposta.append(trecho)
                n = parcial_soma(tid, trecho)
                hub.publish(tid, "delta", {"texto": trecho, "n": n})
            elif t == "thinking":
                houve = True
                pensei.append(bloco.get("thinking", ""))
                fase_set(tid, "pensando")
            elif t == "tool_use":
                houve = True
                nome = bloco.get("name") or ""
                fase_set(tid, FASES_AMIGAVEIS.get(nome, "trabalhando"))
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()

    if turno.parar or turno.interrompido:
        return "".join(resposta), "".join(pensei), novo_sid, houve
    if morto["por"]:
        raise RuntimeError(morto["por"])
    err = "".join(erro).strip()
    if proc.returncode != 0:
        if sid and re.search(r"resume|session|conversa|not found|no conversation",
                             err, re.I):
            raise ResumeMorreu(err[-300:])
        raise RuntimeError(err[-600:] or f"o claude saiu com codigo {proc.returncode}")
    if not houve:
        raise RespostaVazia()
    return "".join(resposta), "".join(pensei), novo_sid, houve


def executa_turno(tid):
    """Roda UM turno da conversa `tid`. Pensado pra rodar numa thread propria."""
    turno = Turno(tid)
    with LOCK:
        EMVOO[tid] = turno
        PARTINDO.discard(tid)
    msgs = pendentes(tid)
    if not msgs:
        with LOCK:
            EMVOO.pop(tid, None)
        return
    t0 = msgs[0]["ts"] or time.time()     # cronometro ancorado no BANCO (sobrevive a restart)
    fase_set(tid, "pensando", t0=t0)
    sid = (con().execute("SELECT session_id FROM topicos WHERE id=?",
                         (tid,)).fetchone() or {"session_id": None})["session_id"]
    try:
        prompt = monta_prompt(tid, msgs)
        try:
            resp, pensei, novo_sid, _ = roda_claude(turno, prompt, sid)
        except ResumeMorreu:
            # ponteiro pra recurso volatil: esqueca o ponteiro e recomece UMA vez
            log(f"#{tid}: a memoria da conversa expirou — recomecando a frio")
            con().execute("UPDATE topicos SET session_id=NULL WHERE id=?", (tid,))
            con().commit()
            resp, pensei, novo_sid, _ = roda_claude(
                turno, monta_prompt(tid, msgs, frio=True), None)
        except RespostaVazia:
            # "turno choco": saiu limpo e sem conteudo nenhum. Zero eventos => nada
            # foi escrito na tela => refazer nao duplica.
            log(f"#{tid}: turno voltou vazio — refazendo")
            try:
                resp, pensei, novo_sid, _ = roda_claude(turno, prompt, sid)
            except (RespostaVazia, ResumeMorreu):
                resp, pensei, novo_sid, _ = roda_claude(
                    turno, monta_prompt(tid, msgs, frio=True), None)

        if turno.parar:
            grava_msg(tid, "sistema", "⏹️ parado por voce")
        elif turno.interrompido:
            pass                                   # o proximo turno responde tudo junto
        else:
            grava_msg(tid, "assistant", resp.strip(), pensei.strip())
            if novo_sid:
                con().execute("UPDATE topicos SET session_id=? WHERE id=?", (novo_sid, tid))
                con().commit()
            con().execute("DELETE FROM reconcile_log WHERE topico_id=?", (tid,))
            con().commit()
            # o batizador roda FORA do turno: ele e outro claude, e segurar a vaga
            # do turno com ele faz a conversa aparecer "respondendo" depois de
            # pronta — e faz o deploy esperar por um enfeite.
            threading.Thread(target=batiza_se_precisar, args=(tid, msgs),
                             daemon=True).start()
    except Exception as e:                          # noqa: BLE001 — erro vira mensagem
        if not (turno.parar or turno.interrompido):
            log(f"#{tid}: turno falhou: {e}")
            grava_msg(tid, "sistema", f"⚠️ deu erro aqui: {str(e)[:600]}")
    finally:
        fase_limpa(tid)                             # SEMPRE, de no que der
        with LOCK:
            EMVOO.pop(tid, None)
            volta = tid in PENDENTE
            PENDENTE.discard(tid)
        hub.publish(tid, "fim", {})
        if volta and not DESLIGANDO.is_set():
            dispara(tid)


def _thread_turno(tid):
    VAGAS.acquire()
    try:
        executa_turno(tid)
    finally:
        VAGAS.release()
        with LOCK:
            PARTINDO.discard(tid)


def dispara(tid):
    """Comeca o turno da conversa, se nao houver um rodando (senao, enfileira)."""
    if DESLIGANDO.is_set():
        return
    with LOCK:
        # a vaga e marcada DENTRO do lock: dois disparos juntos nao viram dois turnos
        if tid in EMVOO or tid in PARTINDO:
            PENDENTE.add(tid)
            return
        PARTINDO.add(tid)
    threading.Thread(target=_thread_turno, args=(tid,), daemon=True).start()


def agenda_lote(tid):
    """Debounce: mensagens que chegam coladas viram UM turno so."""
    with LOCK:
        t = TIMERS.pop(tid, None)
        if t:
            t.cancel()
        novo = threading.Timer(DEBOUNCE, lambda: dispara(tid))
        novo.daemon = True
        TIMERS[tid] = novo
    novo.start()


def talvez_interrompe(tid):
    """Chegou mensagem nova com um turno rodando.

    Se ele AINDA NAO escreveu nada, mata e refaz vendo as duas mensagens juntas.
    Se ja comecou a escrever, deixa terminar — nunca se joga fora resposta que a
    pessoa ja esta lendo; a nova vira o proximo turno.
    """
    with LOCK:
        turno = EMVOO.get(tid)
        if not turno:
            return
        PENDENTE.add(tid)
        if turno.escreveu:
            return
        turno.interrompido = True
    try:
        if turno.proc:
            turno.proc.kill()
    except Exception:
        pass


def para_agora(tid):
    """A pessoa mandou parar: mata mesmo com a resposta saindo e esvazia a fila."""
    with LOCK:
        t = TIMERS.pop(tid, None)
        if t:
            t.cancel()
        PENDENTE.discard(tid)
        turno = EMVOO.get(tid)
        if turno:
            turno.parar = True
        CORTE.add(tid)      # o proximo turno precisa saber que houve corte
    if turno and turno.proc:
        try:
            turno.proc.kill()
        except Exception:
            pass
        return True
    fase_limpa(tid)
    hub.publish(tid, "fim", {})
    return False


# ---------------------------------------------------------------- titulo automatico
def batiza_se_precisar(tid, msgs):
    top = con().execute("SELECT titulo FROM topicos WHERE id=?", (tid,)).fetchone()
    if not top or top["titulo"] != "Nova conversa":
        return
    semente = ""
    for m in msgs:
        semente = (m["transcricao"] or m["texto"] or "").strip()
        if semente:
            break
    if not semente:
        return
    try:
        # roda em /tmp de proposito: assim NAO carrega o CLAUDE.md do assistente
        # (senao o batizador responde como se fosse o assistente inteiro).
        out = subprocess.run(
            [CLAUDE, "-p", TITLE_PROMPT + semente[:1000], "--output-format", "json",
             "--model", "haiku", "--permission-mode", "bypassPermissions"],
            cwd="/tmp", capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            return
        titulo = (json.loads(out.stdout).get("result") or "").strip()
        titulo = titulo.splitlines()[0].strip().strip('"\'').rstrip(".").strip()
        if titulo:
            con().execute("UPDATE topicos SET titulo=? WHERE id=?", (titulo[:80], tid))
            con().commit()
            hub.publish(tid, "titulo", {"titulo": titulo[:80]})
    except Exception as e:      # noqa: BLE001 — titulo e enfeite, nunca derruba o turno
        log(f"#{tid}: nao consegui dar titulo: {e}")


# ---------------------------------------------------------------- reconciliador
def reconciliar_orfaos():
    """No boot: mensagem que ficou sem resposta (o servico morreu no meio) volta.

    COM FREIO — sem ele isto vira bomba de tokens: cada restart re-dispara, o
    restart seguinte mata de novo, e a conversa fica presa em "respondendo…".
    """
    c = con()
    tops = c.execute("SELECT id FROM topicos WHERE excluido=0").fetchall()
    for t in tops:
        tid = t["id"]
        fila = pendentes(tid)
        if not fila:
            continue
        ult = fila[-1]["id"]
        idade = time.time() - (fila[0]["ts"] or 0)
        if idade > RECONCILIA_IDADE:
            continue                                    # velho demais: nao se responde so
        r = c.execute("SELECT tentativas FROM reconcile_log WHERE topico_id=? AND ult_msg_id=?",
                      (tid, ult)).fetchone()
        tentativas = r["tentativas"] if r else 0
        if tentativas >= RECONCILIA_TENTATIVAS:
            grava_msg(tid, "sistema",
                      "⏸️ este turno foi interrompido umas vezes seguidas — me manda de novo")
            hub.publish(tid, "fim", {})                 # limpa indicador preso
            continue
        c.execute("INSERT INTO reconcile_log (topico_id,ult_msg_id,tentativas) VALUES (?,?,1) "
                  "ON CONFLICT(topico_id) DO UPDATE SET ult_msg_id=excluded.ult_msg_id, "
                  "tentativas=CASE WHEN reconcile_log.ult_msg_id=excluded.ult_msg_id "
                  "THEN reconcile_log.tentativas+1 ELSE 1 END",
                  (tid, ult))
        c.commit()
        log(f"#{tid}: retomando turno que ficou pendente")
        dispara(tid)


# ---------------------------------------------------------------- audio -> texto
def transcreve(caminho) -> str:
    """Audio vira texto pelo Whisper que o modulo do Telegram ja instalou."""
    if not (TRANSCRIBE_PY.exists() and TRANSCRIBE_VENV.exists()):
        return ""
    try:
        out = subprocess.run([str(TRANSCRIBE_VENV), str(TRANSCRIBE_PY), caminho],
                             capture_output=True, text=True, timeout=300)
        if out.returncode != 0:
            log("transcricao falhou:", out.stderr.strip()[-300:])
            return ""
        return out.stdout.strip()
    except Exception as e:      # noqa: BLE001
        log("transcricao falhou:", e)
        return ""


# ---------------------------------------------------------------- web
app = Flask(__name__, static_folder=None)
app.secret_key = SEGREDO
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024      # 64 MB por anexo

TENTATIVAS_LOGIN = {}      # ip -> [n, ate_quando]


def logado() -> bool:
    return session.get("ok") is True


def exige_login():
    if not logado():
        abort(401)


PAGINA_LOGIN = """<!doctype html><html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Entrar</title><style>
:root{color-scheme:dark}
body{margin:0;height:100dvh;display:grid;place-items:center;background:#0e1013;
     color:#e8eaed;font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
form{width:min(92vw,320px);display:grid;gap:12px;text-align:center}
h1{font-size:20px;margin:0 0 8px;font-weight:600}
input,button{font:inherit;padding:12px 14px;border-radius:12px;border:1px solid #2a2f37}
input{background:#171a1f;color:#e8eaed}
button{background:#3b82f6;color:#fff;border:0;font-weight:600;cursor:pointer}
.erro{color:#f87171;font-size:14px;min-height:20px}
</style></head><body><form method="post" action="/entrar">
<h1>__ASSISTENTE__</h1>
<input type="password" name="senha" placeholder="senha" autofocus autocomplete="current-password">
<button type="submit">Entrar</button><div class="erro">__ERRO__</div>
</form></body></html>"""


@app.get("/")
def home():
    if not logado():
        return Response(PAGINA_LOGIN.replace("__ASSISTENTE__", ASSISTENTE)
                        .replace("__ERRO__", ""), mimetype="text/html")
    html = (BASE / "tela.html").read_text()
    html = html.replace("{{ASSISTENTE}}", ASSISTENTE).replace("{{VERSAO}}", VERSAO)
    return Response(html, mimetype="text/html")


@app.post("/entrar")
def entrar():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0]
    n, ate = TENTATIVAS_LOGIN.get(ip, (0, 0))
    if time.time() < ate:
        return Response(PAGINA_LOGIN.replace("__ASSISTENTE__", ASSISTENTE)
                        .replace("__ERRO__", "espere um minuto"), mimetype="text/html")
    if secrets.compare_digest(request.form.get("senha", ""), SENHA):
        session["ok"] = True
        session.permanent = True
        TENTATIVAS_LOGIN.pop(ip, None)
        return redirect("/")
    n += 1
    TENTATIVAS_LOGIN[ip] = (n, time.time() + 60 if n >= 5 else 0)
    return Response(PAGINA_LOGIN.replace("__ASSISTENTE__", ASSISTENTE)
                    .replace("__ERRO__", "senha errada"), mimetype="text/html")


@app.get("/sair")
def sair():
    session.clear()
    return redirect("/")


@app.get("/saude")
def saude():
    with LOCK:
        voando = len([t for t in EMVOO.values() if t])
    return jsonify({"ok": True, "turnos_em_voo": voando, "versao": VERSAO})


# --- conversas ---------------------------------------------------------------
def _conversa_json(r):
    return {"id": r["id"], "titulo": r["titulo"], "arquivado": bool(r["arquivado"]),
            "mexido_em": r["mexido_em"]}


@app.get("/api/conversas")
def lista_conversas():
    exige_login()
    quais = request.args.get("quais", "ativas")
    if quais == "arquivadas":
        onde = "excluido=0 AND arquivado=1"
    elif quais == "lixeira":
        onde = "excluido=1"
    else:
        onde = "excluido=0 AND arquivado=0"
    linhas = con().execute(
        f"SELECT * FROM topicos WHERE {onde} ORDER BY mexido_ts DESC LIMIT 200").fetchall()
    with LOCK:
        ocupados = [t for t in EMVOO if EMVOO.get(t)]
    return jsonify({"conversas": [_conversa_json(r) for r in linhas],
                    "respondendo": ocupados})


@app.post("/api/conversas")
def nova_conversa():
    exige_login()
    c = con()
    cur = c.execute("INSERT INTO topicos (titulo,criado_em,mexido_em,mexido_ts) "
                    "VALUES ('Nova conversa',?,?,?)",
                    (agora_iso(), agora_iso(), time.time()))
    c.commit()
    return jsonify({"id": cur.lastrowid})


@app.get("/api/conversas/<int:tid>")
def le_conversa(tid):
    exige_login()
    top = con().execute("SELECT * FROM topicos WHERE id=?", (tid,)).fetchone()
    if not top:
        abort(404)
    msgs = con().execute(
        "SELECT * FROM mensagens WHERE topico_id=? ORDER BY id", (tid,)).fetchall()
    return jsonify({
        "conversa": _conversa_json(top),
        "mensagens": [{
            "id": m["id"], "papel": m["papel"],
            "texto": m["transcricao"] or m["texto"] or "",
            "pensei": m["pensei"] or "",
            "arquivo": m["arquivo"], "arquivo_nome": m["arquivo_nome"],
            "arquivo_tipo": m["arquivo_tipo"], "quando": m["quando"],
        } for m in msgs]})


@app.post("/api/conversas/<int:tid>/titulo")
def renomeia(tid):
    exige_login()
    titulo = (request.json or {}).get("titulo", "").strip()[:80]
    if titulo:
        con().execute("UPDATE topicos SET titulo=? WHERE id=?", (titulo, tid))
        con().commit()
    return jsonify({"ok": True})


@app.post("/api/conversas/<int:tid>/arquivar")
def arquiva(tid):
    exige_login()
    v = 1 if (request.json or {}).get("arquivado", True) else 0
    con().execute("UPDATE topicos SET arquivado=? WHERE id=?", (v, tid))
    con().commit()
    return jsonify({"ok": True})


@app.post("/api/conversas/<int:tid>/excluir")
def exclui(tid):
    """Excluir aqui e ESCONDER, nunca apagar: a conversa sai da lista e continua
    no banco. Way of life do kit — nada se deleta, tudo se move."""
    exige_login()
    v = 0 if (request.json or {}).get("voltar") else 1
    con().execute("UPDATE topicos SET excluido=?, arquivado=0 WHERE id=?", (v, tid))
    con().commit()
    return jsonify({"ok": True})


@app.post("/api/conversas/<int:tid>/parar")
def parar(tid):
    exige_login()
    return jsonify({"ok": para_agora(tid)})


# --- mandar mensagem ---------------------------------------------------------
@app.post("/api/conversas/<int:tid>/mensagem")
def manda(tid):
    exige_login()
    if not con().execute("SELECT 1 FROM topicos WHERE id=?", (tid,)).fetchone():
        abort(404)
    texto = (request.form.get("texto") or "").strip()
    arq = request.files.get("arquivo")

    nome_disco = nome_orig = tipo = None
    transcricao = None
    if arq and arq.filename:
        # nome GERADO, nunca o que veio do navegador (travessia de diretorio).
        ext = os.path.splitext(arq.filename)[1][:10]
        ext = re.sub(r"[^A-Za-z0-9.]", "", ext)
        nome_disco = f"{uuid.uuid4().hex}{ext}"
        nome_orig = os.path.basename(arq.filename)[:120]
        tipo = arq.mimetype or mimetypes.guess_type(nome_orig)[0] or "application/octet-stream"
        arq.save(caminho_anexo(nome_disco))
        if tipo.startswith("audio/") or ext.lower() in (".ogg", ".webm", ".m4a", ".mp3", ".wav"):
            tipo = tipo if tipo.startswith("audio/") else "audio/webm"
            transcricao = transcreve(caminho_anexo(nome_disco)) or None

    if not texto and not nome_disco:
        return jsonify({"erro": "mensagem vazia"}), 400

    # freio por palavra: SO se a mensagem inteira for a palavra (<=26 caracteres).
    # "parar de mandar e-mail pro fulano" e conteudo, nao freio.
    limpo = re.sub(r"[^a-zA-Zà-úÀ-Ú! ]", "", texto).strip().lower()
    if texto and len(texto) <= 26 and limpo in PARADA_PALAVRAS and not nome_disco:
        grava_msg(tid, "user", texto)
        para_agora(tid)
        return jsonify({"ok": True, "parou": True})

    mid = grava_msg(tid, "user", texto, arquivo=nome_disco, arquivo_nome=nome_orig,
                    arquivo_tipo=tipo, transcricao=transcricao)
    hub.publish(tid, "nova", {"id": mid})
    talvez_interrompe(tid)
    agenda_lote(tid)
    return jsonify({"ok": True, "id": mid, "transcricao": transcricao or ""})


# --- o streaming (SSE) -------------------------------------------------------
@app.get("/api/conversas/<int:tid>/stream")
def stream(tid):
    exige_login()

    def gen():
        q = hub.subscribe(tid)
        try:
            yield ": ping\n\n"                      # solta os headers na hora
            with LOCK:
                f = dict(FASE.get(tid) or {})
                parc = PARCIAL.get(tid, "")
            if f:
                # SNAPSHOT: quem chegou agora recebe em que pe esta o turno
                yield sse("status", {"texto": f["texto"],
                                     "desde": int((time.time() - f["t0"]) * 1000)})
                if parc:
                    yield sse("parcial", {"texto": parc, "n": len(parc)})
            else:
                yield sse("fim", {})                # limpa indicador fantasma
            while True:
                try:
                    evento, dados = q.get(timeout=15)
                except queue.Empty:
                    yield ": ping\n\n"              # proxy e celular derrubam ocioso
                    continue
                yield sse(evento, dados)
        finally:
            hub.unsubscribe(tid, q)

    return Response(gen(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",                  # sem isto o proxy segura o buffer
        "Connection": "keep-alive",
    })


def sse(evento, dados) -> str:
    return f"event: {evento}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n"


# --- anexos ------------------------------------------------------------------
@app.get("/anexo/<nome>")
def anexo(nome):
    exige_login()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", nome):
        abort(404)
    caminho = ANEXOS / nome
    if not caminho.exists():
        abort(404)
    m = con().execute("SELECT arquivo_nome,arquivo_tipo FROM mensagens WHERE arquivo=?",
                      (nome,)).fetchone()
    tipo = (m["arquivo_tipo"] if m else None) or "application/octet-stream"
    if tipo.startswith(("image/", "audio/", "video/")):
        # inline e com suporte a Range: sem isso o player do celular nao navega no audio
        return send_file(caminho, mimetype=tipo, conditional=True)
    return send_file(caminho, mimetype=tipo, as_attachment=True,
                     download_name=(m["arquivo_nome"] if m else nome), conditional=True)


# --- app de celular (PWA) ----------------------------------------------------
@app.get("/manifest.webmanifest")
def manifest():
    return jsonify({
        "id": "/", "name": ASSISTENTE, "short_name": ASSISTENTE,
        "start_url": "/", "display": "standalone",
        "background_color": "#0e1013", "theme_color": "#0e1013",
        "icons": [{"src": "/icone.png", "sizes": "512x512", "type": "image/png",
                   "purpose": "any maskable"}],
    })


@app.get("/sw.js")
def sw():
    # de proposito NAO faz cache: service worker guardando JS velho e um dos erros
    # mais caros da casa (voce conserta e o celular continua quebrado).
    return Response("self.addEventListener('fetch', () => {});",
                    mimetype="application/javascript")


@app.get("/icone.png")
def icone():
    p = BASE / "icone.png"
    if p.exists():
        return send_file(p, mimetype="image/png")
    abort(404)


# ---------------------------------------------------------------- desligamento
def desliga(*_):
    """Dreno: recusa turno novo e espera os em voo — CURTO (esperar demais e igual
    a nao esperar: o turno morre do mesmo jeito, so que com o app fora do ar)."""
    DESLIGANDO.set()
    (DADOS / "parei_em.txt").write_text(agora_iso())   # carimbo ANTES de morrer
    fim = time.time() + DRENO
    while time.time() < fim:
        with LOCK:
            voando = len([t for t in EMVOO.values() if t])
        if not voando:
            break
        time.sleep(1)
    log("saindo")
    os._exit(0)


def main():
    init_db()
    log(f"chat do {ASSISTENTE} — porta {PORTA} · trabalho em {WORKDIR}")
    if not os.path.exists(CLAUDE):
        log(f"AVISO: nao achei o claude em {CLAUDE}")
    import signal
    signal.signal(signal.SIGTERM, desliga)
    signal.signal(signal.SIGINT, desliga)
    threading.Thread(target=reconciliar_orfaos, daemon=True).start()
    app.run(host="127.0.0.1", port=PORTA, threaded=True, debug=False,
            use_reloader=False)


if __name__ == "__main__":
    main()
