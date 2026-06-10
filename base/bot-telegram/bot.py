#!/usr/bin/env python3
"""
Bot do Telegram — ponte entre o Telegram e o Claude Code rodando nesta VPS.
(Parte do kit NEXUM Semente. Versao generica: NADA aqui e fixo de uma pessoa;
tudo que e "da pessoa" vem de ~/.config/semente/config.env)

Ideia:
- Um grupo no Telegram (so o dono + o bot), com TOPICOS ativados.
- Cada topico = uma conversa = uma sessao separada do Claude Code.
- Mensagem nova num topico -> roda o claude naquela sessao -> devolve no mesmo topico.

Recursos do nucleo:
- STREAMING: o claude roda em --output-format stream-json; o bot enxerga o que ele
  faz ao vivo. Nada de kill cego: so trava se ficar 5 min MUDO ou passar de 1h.
- BARRA DE STATUS que atualiza ("trabalhando... (2min) — lendo um arquivo").
- BATCH por topico: fotos de um album + legenda + texto que chegam juntos viram
  UMA resposta so (espera ~1,8s pra agrupar).
- AUDIO que entra (Whisper local via transcribe.py) e sai (Edge-TTS via falar.py).
- AUTO-TITULO: na 1a mensagem de um topico, batiza o topico com o assunto.
- Tratador de erro global + resposta que cai no Geral se o topico sumir.

Seguranca:
- So responde ao TELEGRAM_OWNER_ID (o dono). Qualquer outro e ignorado em silencio.
- Se TELEGRAM_GROUP_ID estiver setado, so funciona dentro desse grupo.
- O token e os IDs ficam em ~/.config/semente/config.env (fora do git, chmod 600).
"""

import os
import sys
import re
import time
import html
import json
import shutil
import asyncio
import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ---------------------------------------------------------------- config
BASE = Path(__file__).resolve().parent
CONFIG_FILE = Path.home() / ".config" / "semente" / "config.env"   # fonte unica de config
SESSIONS_FILE = BASE / "sessions.json"
TOPIC_NAMES_FILE = BASE / "topic_names.json"   # de-para topico(id) -> nome do topico
AUTONAMED_FILE = BASE / "autonamed.json"       # topicos que o bot ja batizou sozinho (1x cada)
CHAT_TOPICS_FILE = BASE / "chat_topics.json"   # topicos "chat livre" (nome com ⚡)
CHAT_EMOJI = "⚡"                          # ⚡ no nome do topico = perguntas aleatorias / pesquisa
INCOMING_DIR = BASE / "incoming"               # imagens/audios recebidos pelo Telegram
INCOMING_DIR.mkdir(exist_ok=True)


def load_config() -> dict:
    """Le a config unica do kit (~/.config/semente/config.env).
    Formato: CHAVE=valor, uma por linha, # comenta. Sem nada fixo no codigo."""
    cfg = {}
    candidates = [CONFIG_FILE, BASE / ".env"]   # .env local so como reserva/transicao
    for f in candidates:
        if f.exists():
            for line in f.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return cfg


cfg = load_config()
try:
    TOKEN = cfg["TELEGRAM_BOT_TOKEN"]
except KeyError:
    sys.exit(f"ERRO: TELEGRAM_BOT_TOKEN nao encontrado em {CONFIG_FILE}. "
             "Crie o arquivo a partir do config.env.example (chmod 600).")
OWNER_ID = int(cfg["TELEGRAM_OWNER_ID"]) if cfg.get("TELEGRAM_OWNER_ID") else None
GROUP_ID = int(cfg["TELEGRAM_GROUP_ID"]) if cfg.get("TELEGRAM_GROUP_ID") else None
ASSISTENTE = cfg.get("NOME_ASSISTENTE", "Assistente")        # como o bot se chama
DONO = cfg.get("NOME_DONO", "o dono")                        # como o bot se refere ao dono

# onde o assistente trabalha (a pasta de conhecimento, com o CLAUDE.md)
WORKDIR = os.path.expanduser(cfg.get("DIR_CONHECIMENTO", "~/nexum"))
# binario do Claude Code (auto-detecta se nao vier na config)
CLAUDE = os.path.expanduser(cfg.get("CLAUDE_BIN", "")) or shutil.which("claude") \
    or os.path.expanduser("~/.local/bin/claude")

# Teto de quantos Claude rodam AO MESMO TEMPO (topicos diferentes em paralelo).
# VPS pequena (2 nucleos / 2-4 GB RAM) -> 2 e um bom teto. Suba so se a VPS for forte.
MAX_CONCORRENTES = int(cfg.get("MAX_CONCORRENTES", "2"))

# --- relogio do claude --------------------------------------------------------
# Medimos duas coisas: (1) ficou MUDO tempo demais = travou de verdade;
# (2) um teto absoluto bem alto como rede de seguranca. Trabalho que esta
# progredindo (gerando passos) NUNCA e morto.
CLAUDE_INACTIVITY = 300                        # s sem NENHUMA saida -> considero travado
CLAUDE_HARD_CAP = 3600                         # s no total -> rede de seguranca (1h)

# --- silencio -> 5 min -> previsao ---------------------------------------------
# Recebeu a mensagem: NAO fala nada (so o 'digitando…'). Passou 5 min e ainda
# trabalhando: avisa UMA vez com a previsao. Depois so ATUALIZA a previsao.
PREVISAO_PRIMEIRA = 300                        # s ate o 1º toque com previsao (5 min)
PREVISAO_INTERVALO = 300                       # s entre uma atualizacao e outra

TRANSCRIBE = str(BASE / "transcribe.py")      # transcritor de audio (Whisper local, de graca)
TRANSCRIBE_TIMEOUT = 300                       # segundos: teto pra transcrever um audio (5 min)

FALAR = str(BASE / "falar.py")                # texto -> voz (Edge-TTS / Piper local)
FALAR_TIMEOUT = 180                            # segundos: teto pra gerar a voz (3 min)
VOZ_MARKER = "[VOZ]"

# quanto tempo agrupar mensagens que chegam coladas (album, foto+pergunta) num turno so
DEBOUNCE = 1.8                                 # segundos de silencio antes de processar o lote

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
# silencia o ruido (e o vazamento de token na URL) do cliente HTTP
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("semente-bot")


# ---------------------------------------------------------------- sessoes
def load_sessions() -> dict:
    if SESSIONS_FILE.exists():
        try:
            return json.loads(SESSIONS_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_sessions(s: dict) -> None:
    SESSIONS_FILE.write_text(json.dumps(s, indent=2))


sessions = load_sessions()          # topico -> session_id do claude
locks: dict[str, asyncio.Lock] = {}  # 1 fila por topico (evita corrida)
claude_slots = asyncio.Semaphore(MAX_CONCORRENTES)


# ---------------------------------------------------------------- auto-titulo
def load_autonamed() -> set:
    if AUTONAMED_FILE.exists():
        try:
            return set(json.loads(AUTONAMED_FILE.read_text()))
        except Exception:
            return set()
    return set()


def save_autonamed() -> None:
    AUTONAMED_FILE.write_text(json.dumps(sorted(autonamed)))


autonamed = load_autonamed()        # ids (str) de topicos ja batizados automaticamente


def load_chat_topics() -> set:
    if CHAT_TOPICS_FILE.exists():
        try:
            return set(json.loads(CHAT_TOPICS_FILE.read_text()))
        except Exception:
            return set()
    return set()


def save_chat_topics() -> None:
    CHAT_TOPICS_FILE.write_text(json.dumps(sorted(chat_topics)))


chat_topics = load_chat_topics()    # ids (str) de topicos "chat livre" (nome tinha ⚡)


# ---------------------------------------------------------------- nomes dos topicos
def load_topic_names() -> dict:
    if TOPIC_NAMES_FILE.exists():
        try:
            return json.loads(TOPIC_NAMES_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_topic_names(t: dict) -> None:
    TOPIC_NAMES_FILE.write_text(json.dumps(t, indent=2, ensure_ascii=False))


topic_names = load_topic_names()    # topico(id como str) -> nome do topico


def remember_topic_name(update: Update) -> None:
    """Aprende o nome do topico quando ele e criado/renomeado (ou via reply)."""
    msg = update.message
    if not msg:
        return
    tid = msg.message_thread_id
    if tid is None:
        return
    name = None
    authoritative = False   # nome vindo de evento (criacao/rename) = nome ATUAL e confiavel
    created = getattr(msg, "forum_topic_created", None)
    edited = getattr(msg, "forum_topic_edited", None)
    reply = getattr(msg, "reply_to_message", None)
    if edited and getattr(edited, "name", None):
        name = edited.name          # renomeou agora -> sempre vale
        authoritative = True
    elif created and getattr(created, "name", None):
        name = created.name         # acabou de criar -> sempre vale
        authoritative = True
    elif reply and getattr(reply, "forum_topic_created", None):
        # nome de carona numa mensagem comum: e o nome de CRIACAO, pode estar velho.
        name = reply.forum_topic_created.name
    if created or edited:
        log.info("evento topico  tid=%s  criado=%s  editado=%s  nome=%r",
                 tid, bool(created), bool(edited), name)
    if name:
        known = topic_names.get(str(tid))
        if authoritative:
            if known != name:
                topic_names[str(tid)] = name
                save_topic_names(topic_names)
                log.info("nome do topico aprendido  tid=%s -> %r", tid, name)
        elif known is None:        # so preenche se ainda nao conhecemos o topico
            topic_names[str(tid)] = name
            save_topic_names(topic_names)
            log.info("nome do topico aprendido (carona)  tid=%s -> %r", tid, name)
        # ⚡ no nome = topico de chat livre. Gruda no topico (flag persistente):
        # uma vez chat, sempre chat, mesmo depois de renomeado (mantem o ⚡).
        # So o dono tirando o ⚡ num rename de verdade (evento authoritative) desliga.
        skey = str(tid)
        if CHAT_EMOJI in name:
            if skey not in chat_topics:
                chat_topics.add(skey)
                save_chat_topics()
                log.info("topico marcado CHAT LIVRE  tid=%s", tid)
        elif authoritative and skey in chat_topics:
            chat_topics.discard(skey)
            save_chat_topics()
            log.info("topico DESmarcado de chat livre  tid=%s", tid)


def thread_key(update: Update) -> str:
    tid = update.message.message_thread_id
    return str(tid) if tid is not None else "general"


def origem_label(update: Update) -> str:
    """Monta a etiqueta de origem com o topico (nome + numero) quando possivel."""
    key = thread_key(update)
    nome = topic_names.get(key)
    # ⚡ = chat livre: vale pelo flag persistente OU pelo ⚡ no nome atual.
    eh_chat = (key in chat_topics) or (nome is not None and CHAT_EMOJI in nome)
    chat_tag = (" | ⚡ CHAT LIVRE (pergunta aleatoria/pesquisa — NAO assumir "
                "assunto de trabalho)") if eh_chat else ""
    if key == "general":
        return f"[ORIGEM: Telegram | Topico: Geral{chat_tag}]"
    if nome:
        return f'[ORIGEM: Telegram | Topico: "{nome}" (#{key}){chat_tag}]'
    return f"[ORIGEM: Telegram | Topico #{key}{chat_tag}]"


def authorized(update: Update) -> bool:
    u = update.effective_user
    c = update.effective_chat
    if OWNER_ID and (not u or u.id != OWNER_ID):
        return False
    if GROUP_ID and (not c or c.id != GROUP_ID):
        return False
    return True


# ---------------------------------------------------------------- claude (streaming)
class ClaudeTimeout(Exception):
    """O claude travou (ficou mudo demais) ou estourou o teto absoluto.
    NUNCA dispara recomeco-do-zero automatico — so um aviso claro pro dono."""


# nome de ferramenta -> frase humana pra barra de status ("o que estou fazendo agora")
_FRIENDLY = {
    "Bash": "rodando um comando",
    "Read": "lendo um arquivo",
    "Edit": "editando um arquivo",
    "Write": "escrevendo um arquivo",
    "Grep": "procurando no conteudo",
    "Glob": "procurando arquivos",
    "WebFetch": "abrindo um site",
    "WebSearch": "buscando na web",
    "Task": "chamando um agente",
    "TodoWrite": "organizando os passos",
}


def friendly(name: str | None) -> str:
    if not name:
        return "trabalhando"
    if name.startswith("mcp__gmail") or "Gmail" in name:
        return "mexendo no e-mail"
    if "Calendar" in name:
        return "vendo a agenda"
    if "Drive" in name:
        return "no Google Drive"
    if name.startswith("mcp__"):
        return "usando uma ferramenta"
    return _FRIENDLY.get(name, "trabalhando")


async def run_claude_stream(text: str, session_id: str | None, on_event):
    """Roda o claude em streaming. Retorna (resposta, session_id).

    on_event(kind, name) e chamado a cada passo do claude:
      kind="tool" name=<nome da ferramenta>  ·  kind="text" name=<trecho de texto>
    Assim a barra de status mostra o que ele esta fazendo AGORA.
    Levanta ClaudeTimeout se ele ficar mudo demais ou estourar o teto absoluto.
    """
    cmd = [
        CLAUDE, "-p", text,
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "bypassPermissions",
    ]
    if session_id:
        cmd += ["--resume", session_id]

    async with claude_slots:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=WORKDIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=16 * 1024 * 1024,   # linhas de stream-json podem ser grandes
        )
        state = {"result": "", "sid": None, "is_error": False}
        stderr_buf: list[str] = []

        async def drain_err():
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                stderr_buf.append(line.decode(errors="replace"))

        async def read_out():
            deadline = time.monotonic() + CLAUDE_HARD_CAP
            while True:
                if time.monotonic() > deadline:
                    raise ClaudeTimeout("passou de 1 hora")
                try:
                    line = await asyncio.wait_for(
                        proc.stdout.readline(), timeout=CLAUDE_INACTIVITY)
                except asyncio.TimeoutError:
                    raise ClaudeTimeout(f"ficou {CLAUDE_INACTIVITY // 60} min sem responder")
                if not line:
                    break
                s = line.strip()
                if not s:
                    continue
                try:
                    ev = json.loads(s)
                except Exception:
                    continue
                t = ev.get("type")
                if t == "system":
                    if ev.get("session_id"):
                        state["sid"] = ev["session_id"]
                elif t == "assistant":
                    content = (ev.get("message") or {}).get("content") or []
                    for blk in content:
                        bt = blk.get("type")
                        if bt == "tool_use":
                            on_event("tool", blk.get("name"))
                        elif bt == "text" and (blk.get("text") or "").strip():
                            on_event("text", blk["text"])
                elif t == "result":
                    state["sid"] = ev.get("session_id") or state["sid"]
                    state["is_error"] = bool(ev.get("is_error"))
                    state["result"] = ev.get("result") or ""

        err_task = asyncio.create_task(drain_err())
        try:
            await read_out()
        except ClaudeTimeout:
            proc.kill()
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except Exception:
                pass
            err_task.cancel()
            raise
        await proc.wait()
        err_task.cancel()

        if proc.returncode not in (0, None) and not state["result"]:
            raise RuntimeError(("".join(stderr_buf).strip() or "claude falhou")[-800:])
        if state["is_error"]:
            raise RuntimeError(str(state["result"])[-800:])
        return state["result"], state["sid"]


TITLE_PROMPT = (
    "Voce vai dar nome a uma conversa. Com base na mensagem abaixo, escreva um TITULO "
    "curto (3 a 5 palavras), em portugues, sem aspas e sem ponto final, que resuma o "
    "assunto. Responda APENAS o titulo, mais nada.\n\nMensagem:\n"
)


async def generate_title(text: str) -> str:
    """Gera um titulo curto pro topico a partir da 1a mensagem (modelo rapido, sem sessao).

    Roda em /tmp de proposito: assim NAO carrega o CLAUDE.md do projeto e o modelo
    responde so o titulo, em vez de 'pensar como assistente' e escrever demais.
    """
    cmd = [
        CLAUDE, "-p", TITLE_PROMPT + text[:1000],
        "--output-format", "json",
        "--model", "haiku",
        "--permission-mode", "bypassPermissions",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd="/tmp",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await asyncio.wait_for(proc.communicate(), timeout=90)
    if proc.returncode != 0:
        raise RuntimeError((err.decode().strip() or "claude falhou")[-300:])
    data = json.loads(out.decode())
    if data.get("is_error"):
        raise RuntimeError(str(data.get("result"))[-300:])
    titulo = (data.get("result") or "").strip()
    titulo = titulo.splitlines()[0].strip().strip('"\'').rstrip(".").strip() if titulo else ""
    return titulo[:128]


# ---------------------------------------------------------------- audio (whisper)
async def transcrever(audio_path: str) -> str:
    """Transcreve um audio chamando o transcribe.py (Whisper local). Retorna o texto."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, TRANSCRIBE, audio_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=TRANSCRIBE_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"a transcricao demorou demais (mais de {TRANSCRIBE_TIMEOUT}s)")
    if proc.returncode != 0:
        raise RuntimeError((err.decode().strip() or "transcricao falhou")[-300:])
    return out.decode().strip()


# ---------------------------------------------------------------- voz (TTS)
async def falar(texto: str, ogg_path: str) -> str:
    """Gera um recado de voz (.ogg/opus) a partir do texto, chamando o falar.py."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, FALAR, ogg_path,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(input=texto.encode("utf-8")), timeout=FALAR_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"gerar a voz demorou demais (mais de {FALAR_TIMEOUT}s)")
    if proc.returncode != 0:
        raise RuntimeError((err.decode().strip() or "falar falhou")[-300:])
    return out.decode().strip()


# ---------------------------------------------------------------- barra de status (sinal de vida)
def fmt_dur(secs: int) -> str:
    if secs < 60:
        return f"{secs}s"
    m = secs // 60
    return f"{m}min"


class Progress:
    """Mostra que o assistente esta vivo e PROGREDINDO: uma mensagem de status que
    se atualiza ('trabalhando... (2min) — lendo um arquivo') + o 'digitando...'."""

    def __init__(self, bot, chat_id, thread_id):
        self.bot = bot
        self.chat_id = chat_id
        self.thread_id = thread_id
        self.last = "começando"
        self.msg = None
        self.t0 = time.monotonic()
        self._stop = asyncio.Event()
        self._task = None

    def note(self, kind, name=None):
        """Chamado pelo streaming a cada passo do claude (sincrono, mesmo loop)."""
        if kind == "tool":
            self.last = friendly(name)
        elif kind == "text":
            txt = (name or "").strip().replace("\n", " ")
            self.last = (txt[:50] + "…") if len(txt) > 50 else (txt or "pensando")

    async def start(self):
        # Recebeu a mensagem: NAO fala nada — so o "digitando…" do Telegram
        # (discreto, sem notificacao). O 1º toque com texto so vem aos 5 min,
        # e dai em diante e so atualizar a previsao.
        self.msg = None
        self._task = asyncio.create_task(self._loop())

    async def _previsao(self, elapsed_s):
        """Aos 5 min (e a cada 5 min depois) avisa que ainda esta trabalhando, com
        a previsao. 1º toque = mensagem nova (notifica). Depois so EDITA a mesma
        linha — atualiza a previsao sem ficar pingando notificacao."""
        mins = int(elapsed_s // 60)
        linha = (f"⏳ Ainda trabalhando nisso ({mins} min) — {self.last}.\n"
                 f"Previsão: te dou o resultado em mais uns ~5 min.")
        try:
            if self.msg is None:
                self.msg = await self.bot.send_message(
                    self.chat_id, linha, message_thread_id=self.thread_id)
            else:
                await self.bot.edit_message_text(
                    linha, chat_id=self.chat_id, message_id=self.msg.message_id)
        except Exception:
            pass

    async def _loop(self):
        prox_previsao = self.t0 + PREVISAO_PRIMEIRA
        while not self._stop.is_set():
            try:
                await self.bot.send_chat_action(
                    self.chat_id, ChatAction.TYPING, message_thread_id=self.thread_id)
            except Exception:
                pass
            agora = time.monotonic()
            if agora >= prox_previsao:
                await self._previsao(agora - self.t0)
                prox_previsao = agora + PREVISAO_INTERVALO
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=4)
            except asyncio.TimeoutError:
                pass

    async def stop(self):
        self._stop.set()
        if self._task:
            try:
                await self._task
            except Exception:
                pass
        if self.msg:
            try:
                await self.bot.delete_message(self.chat_id, self.msg.message_id)
            except Exception:
                pass
            self.msg = None


# ---- Markdown -> HTML do Telegram --------------------------------------------
_CODE_BLOCK = re.compile(r"```[a-zA-Z0-9_+-]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")
_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_BOLD2 = re.compile(r"__([^_\n]+)__")
_ITALIC = re.compile(r"(?<![\*\w])\*([^*\n]+)\*(?![\*\w])")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$", re.MULTILINE)
_BULLET = re.compile(r"^(\s*)[-*]\s+", re.MULTILINE)


def md_to_html(text: str) -> str:
    """Converte o markdown da resposta no HTML enxuto que o Telegram aceita.
    'Boa o suficiente' de proposito: o reply() tem fallback pra texto puro se falhar."""
    blocks = []
    def _stash_block(m):
        blocks.append("<pre>" + html.escape(m.group(1).rstrip("\n")) + "</pre>")
        return f"\x00B{len(blocks) - 1}\x00"
    text = _CODE_BLOCK.sub(_stash_block, text)

    inlines = []
    def _stash_inline(m):
        inlines.append("<code>" + html.escape(m.group(1)) + "</code>")
        return f"\x00I{len(inlines) - 1}\x00"
    text = _INLINE_CODE.sub(_stash_inline, text)

    text = html.escape(text)

    text = _LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    text = _HEADING.sub(lambda m: "<b>" + m.group(1).strip() + "</b>", text)
    text = _BOLD.sub(r"<b>\1</b>", text)
    text = _BOLD2.sub(r"<b>\1</b>", text)
    text = _ITALIC.sub(r"<i>\1</i>", text)
    text = _BULLET.sub(lambda m: m.group(1) + "• ", text)

    for i, b in enumerate(blocks):
        text = text.replace(f"\x00B{i}\x00", b)
    for i, c in enumerate(inlines):
        text = text.replace(f"\x00I{i}\x00", c)
    return text


def _split_chunks(text: str, lim: int):
    if len(text) <= lim:
        return [text]
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(line) > lim:
            if cur:
                chunks.append(cur)
                cur = ""
            for i in range(0, len(line), lim):
                chunks.append(line[i:i + lim])
            continue
        if cur and len(cur) + len(line) + 1 > lim:
            chunks.append(cur)
            cur = line
        else:
            cur = cur + ("\n" if cur else "") + line
    if cur:
        chunks.append(cur)
    return chunks


def _is_thread_gone(e: Exception) -> bool:
    s = str(e).lower()
    return ("thread not found" in s) or ("topic_closed" in s) or ("topic closed" in s)


async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Manda texto no topico certo, formatado, quebrando se for longo.
    Resiliencia: se o HTML falhar, reenvia em TEXTO PURO; se o TOPICO sumiu/fechou,
    reenvia no GERAL (sem thread) com um aviso — a resposta NUNCA se perde calada."""
    chat_id = update.effective_chat.id
    thread_id = update.message.message_thread_id if update.message else None
    if not text:
        text = "(resposta vazia)"

    async def _send(chunk, thread, parse):
        await context.bot.send_message(
            chat_id=chat_id, text=chunk, message_thread_id=thread, parse_mode=parse)

    avisou_geral = False
    for chunk in _split_chunks(text, 4000):
        try:
            await _send(md_to_html(chunk), thread_id, "HTML")
            continue
        except Exception as e:
            if _is_thread_gone(e):
                # topico fechado/apagado: joga no Geral pra nao perder
                if not avisou_geral:
                    try:
                        await _send("↩️ (o topico sumiu; respondo aqui no Geral)", None, None)
                    except Exception:
                        pass
                    avisou_geral = True
                try:
                    await _send(chunk, None, None)
                except Exception as e2:
                    log.warning("falhei ate no Geral: %s", e2)
                continue
            log.warning("envio com markdown falhou, caindo pra texto puro  tid=%s: %s",
                        thread_id, e)
        # fallback texto puro no mesmo topico
        try:
            await _send(chunk, thread_id, None)
        except Exception as e:
            if _is_thread_gone(e):
                try:
                    await _send(chunk, None, None)
                except Exception as e2:
                    log.warning("falhei ate no Geral: %s", e2)
            else:
                log.warning("falha no envio texto puro  tid=%s: %s", thread_id, e)


# Frases com que o dono pede pra OUVIR a resposta (rede de seguranca; o jeito
# principal e a marca [VOZ], que o assistente poe entendendo o pedido).
import re as _re
_AUDIO_TRIGGER = _re.compile(
    r"\b(responde|responda|me responde|manda|fala|me fala|quero|pode)\b[^.\n]*"
    r"\b(em |por |no |de |com )?\s*(audio|áudio|voz|falando|falado)\b"
    r"|\b(em |por |no )\s*(audio|áudio|voz)\b"
    r"|/voz\b",
    _re.IGNORECASE,
)


def pediu_audio(texto: str) -> bool:
    return bool(texto and _AUDIO_TRIGGER.search(texto))


async def send_voice(update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str):
    """Gera a voz do texto e manda como recado de voz no topico. Erro nao derruba o fluxo."""
    chat_id = update.effective_chat.id
    thread_id = update.message.message_thread_id if update.message else None
    msg_id = update.message.message_id if update.message else "x"
    ogg = INCOMING_DIR / f"tts_{chat_id}_{msg_id}.ogg"
    stop = asyncio.Event()
    rec = asyncio.create_task(_recording_loop(context.bot, chat_id, thread_id, stop))
    try:
        await falar(texto, str(ogg))
        with open(ogg, "rb") as f:
            await context.bot.send_voice(
                chat_id=chat_id, voice=f, message_thread_id=thread_id,
                read_timeout=120, write_timeout=120, connect_timeout=30)
    except Exception as e:
        log.warning("falha ao gerar/enviar voz  tid=%s: %s", thread_id, e)
    finally:
        stop.set()
        await rec
        try:
            ogg.unlink(missing_ok=True)
        except Exception:
            pass


async def _recording_loop(bot, chat_id, thread_id, stop: asyncio.Event):
    while not stop.is_set():
        try:
            await bot.send_chat_action(chat_id, ChatAction.RECORD_VOICE, message_thread_id=thread_id)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=4)
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------- nucleo do turno
async def _run_with_retry(text, sid, prog):
    """Roda o claude. Se o --resume falhar (sessao expirada), recomeca UMA vez do zero.
    Mas se foi TIMEOUT (travou), NAO recomeca — so propaga pra avisar o dono."""
    try:
        return await run_claude_stream(text, sid, prog.note)
    except ClaudeTimeout:
        raise
    except Exception as first:
        if sid:
            log.warning("resume falhou (%s); recomecando do zero", first)
            prog.note("text", "retomando a conversa")
            return await run_claude_stream(text, None, prog.note)
        raise


async def run_turn(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str,
                   title_seed: str, quer_audio: bool = False, confirma: str = ""):
    """Roda o claude no topico (1 fila por topico), com barra de status, responde
    e auto-nomeia. text = ja com a etiqueta de origem; title_seed = base pro titulo."""
    key = thread_key(update)
    chat_id = update.effective_chat.id
    thread_id = update.message.message_thread_id

    lock = locks.setdefault(key, asyncio.Lock())
    async with lock:
        sid = sessions.get(key)
        first_message = sid is None
        prog = Progress(context.bot, chat_id, thread_id)
        await prog.start()
        try:
            result, new_sid = await _run_with_retry(text, sid, prog)
            if new_sid:
                sessions[key] = new_sid
                save_sessions(sessions)
        except ClaudeTimeout as e:
            await prog.stop()
            await reply(update, context,
                        f"⚠️ Travei o relogio: a tarefa {e}. Nao recomecei do zero pra "
                        f"nao te fazer esperar de novo. Se for algo demorado mesmo, me "
                        f"fala pra eu rodar em segundo plano e te avisar quando terminar.")
            return
        except Exception as e:
            await prog.stop()
            await reply(update, context, f"⚠️ deu um erro aqui:\n{e}")
            return
        await prog.stop()

        # A marca [VOZ] pede audio e pode estar em QUALQUER ponto da resposta.
        result_txt = result or ""
        spoken = None
        if VOZ_MARKER in result_txt:
            quer_audio = True
            idx = result_txt.find(VOZ_MARKER)
            spoken = result_txt[idx + len(VOZ_MARKER):].strip()
            result_txt = (result_txt[:idx].rstrip() + "\n\n" + spoken).strip()
        if quer_audio and spoken is None:
            spoken = result_txt

        if confirma:
            texto_escrito = f"{confirma}\n──────────────\n{result_txt}".strip()
        else:
            texto_escrito = result_txt
        await reply(update, context, texto_escrito)
        if quer_audio and spoken and spoken.strip():
            await send_voice(update, context, spoken)

        # auto-titulo: na 1a mensagem de um topico, batiza com base no assunto
        if first_message and thread_id is not None and key not in autonamed and title_seed:
            try:
                titulo = await generate_title(title_seed)
                if titulo:
                    # topico de chat livre: nunca perder o ⚡ no rename (e o sinal do modo)
                    if key in chat_topics and CHAT_EMOJI not in titulo:
                        titulo = f"{CHAT_EMOJI} {titulo}"
                    await context.bot.edit_forum_topic(
                        chat_id=chat_id, message_thread_id=thread_id, name=titulo)
                    autonamed.add(key)
                    save_autonamed()
                    topic_names[key] = titulo
                    save_topic_names(topic_names)
                    log.info("topico auto-nomeado  tid=%s -> %r", thread_id, titulo)
            except Exception as e:
                log.warning("auto-titulo falhou  tid=%s: %s", thread_id, e)


# ---------------------------------------------------------------- BATCH (agrupar o que chega junto)
# Album de fotos, foto+legenda, foto + pergunta em texto separada: tudo isso chega
# como VARIAS mensagens coladas. Sem o batch, cada uma viraria um claude (album de
# 6 fotos = 6 respostas; e a pergunta seria respondida ANTES da foto baixar).
# Juntamos as partes que chegam dentro de DEBOUNCE segundos num TURNO SO.
class Batch:
    def __init__(self):
        self.parts: list[dict] = []
        self.update = None
        self.context = None
        self.title_seed = ""
        self.timer = None


batches: dict[str, Batch] = {}


async def _add_part(update, context, part, title_seed=""):
    """Junta uma 'parte' (texto/imagem/audio) ao lote do topico e rearma o cronometro."""
    key = thread_key(update)
    b = batches.get(key)
    if b is None:
        b = Batch()
        batches[key] = b
    b.parts.append(part)
    b.update = update
    b.context = context
    if not b.title_seed and title_seed:
        b.title_seed = title_seed
    # sinal de vida imediato (antes mesmo do lote fechar)
    try:
        await context.bot.send_chat_action(
            update.effective_chat.id, ChatAction.TYPING,
            message_thread_id=update.message.message_thread_id)
    except Exception:
        pass
    if b.timer:
        b.timer.cancel()
    loop = asyncio.get_event_loop()
    b.timer = loop.call_later(DEBOUNCE, lambda: asyncio.create_task(_flush(key)))


async def _flush(key):
    """Fecha o lote do topico e roda UM turno com tudo junto."""
    b = batches.pop(key, None)
    if not b or not b.parts:
        return
    update, context = b.update, b.context
    images = [p for p in b.parts if p["kind"] == "image"]
    voices = [p for p in b.parts if p["kind"] == "voice"]
    quer_audio = any(p.get("quer_audio") for p in b.parts) or bool(voices)
    confirmas = [p["confirma"] for p in b.parts if p.get("confirma")]

    body = []
    if len(images) > 1:
        body.append(f"[{DONO} enviou {len(images)} IMAGENS juntas pelo Telegram "
                    f"(um album). Abra TODAS e responda considerando o conjunto.]")
    for p in b.parts:
        if p["kind"] == "text":
            body.append(p["text"])
        elif p["kind"] == "image":
            linha = (f"[IMAGEM salva nesta VPS em: {p['path']}\n"
                     "ABRA essa imagem (sua ferramenta de leitura enxerga imagens) e "
                     "considere o que ela mostra.]")
            if p.get("caption"):
                linha += f"\nLegenda nesta imagem: {p['caption']}"
            body.append(linha)
        elif p["kind"] == "voice":
            body.append(f"[{DONO} mandou um AUDIO; transcricao automatica (Whisper) "
                        f"abaixo — trate como a mensagem dele:]\n{p['transcript']}")

    text = origem_label(update) + "\n" + "\n\n".join(body)
    confirma = "\n".join(confirmas)
    await run_turn(update, context, text, b.title_seed or f"mensagem de {DONO}",
                   quer_audio=quer_audio, confirma=confirma)


# ---------------------------------------------------------------- handlers
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensagem de texto comum -> entra no lote do topico."""
    if not authorized(update):
        log.warning("IGNORADO  user=%s  chat=%s",
                    getattr(update.effective_user, "id", "?"),
                    getattr(update.effective_chat, "id", "?"))
        return
    remember_topic_name(update)
    raw = update.message.text or ""
    await _add_part(update, context,
                    {"kind": "text", "text": raw, "quer_audio": pediu_audio(raw)},
                    title_seed=raw)


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foto/arquivo de imagem: baixa e entra no lote (album vira UM turno so)."""
    if not authorized(update):
        log.warning("IGNORADO (img)  user=%s  chat=%s",
                    getattr(update.effective_user, "id", "?"),
                    getattr(update.effective_chat, "id", "?"))
        return
    remember_topic_name(update)
    msg = update.message
    caption = msg.caption or ""
    try:
        if msg.photo:
            biggest = msg.photo[-1]
            tgfile = await context.bot.get_file(biggest.file_id)
            dest = INCOMING_DIR / f"{biggest.file_unique_id}.jpg"
        else:
            doc = msg.document
            tgfile = await context.bot.get_file(doc.file_id)
            ext = Path(doc.file_name).suffix if doc.file_name else ".img"
            dest = INCOMING_DIR / f"{doc.file_unique_id}{ext}"
        await tgfile.download_to_drive(custom_path=str(dest))
        log.info("imagem recebida  tid=%s  -> %s", msg.message_thread_id, dest)
    except Exception as e:
        log.warning("falha ao baixar imagem  tid=%s: %s", msg.message_thread_id, e)
        await reply(update, context, f"⚠️ recebi uma imagem mas nao consegui baixar:\n{e}")
        return
    await _add_part(update, context,
                    {"kind": "image", "path": str(dest), "caption": caption,
                     "quer_audio": pediu_audio(caption)},
                    title_seed=caption or "imagem enviada")


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Audio: baixa, transcreve com Whisper e entra no lote (resposta em audio)."""
    if not authorized(update):
        log.warning("IGNORADO (audio)  user=%s  chat=%s",
                    getattr(update.effective_user, "id", "?"),
                    getattr(update.effective_chat, "id", "?"))
        return
    remember_topic_name(update)
    msg = update.message
    caption = msg.caption or ""
    chat_id = update.effective_chat.id
    thread_id = msg.message_thread_id

    media = msg.voice or msg.audio
    if media is None:
        return
    try:
        tgfile = await context.bot.get_file(media.file_id)
        dest = INCOMING_DIR / f"{media.file_unique_id}.oga"
        await tgfile.download_to_drive(custom_path=str(dest))
        log.info("audio recebido  tid=%s  -> %s", thread_id, dest)
    except Exception as e:
        log.warning("falha ao baixar audio  tid=%s: %s", thread_id, e)
        await reply(update, context, f"⚠️ recebi um audio mas nao consegui baixar:\n{e}")
        return

    # transcreve mostrando 'digitando...' (o Whisper pode demorar)
    stop = asyncio.Event()
    typer = asyncio.create_task(_typing_simple(context.bot, chat_id, thread_id, stop))
    try:
        texto = await transcrever(str(dest))
    except Exception as e:
        stop.set(); await typer
        log.warning("falha ao transcrever  tid=%s: %s", thread_id, e)
        await reply(update, context, f"⚠️ recebi seu audio mas nao consegui transcrever:\n{e}")
        return
    stop.set(); await typer

    if not texto:
        await reply(update, context,
                    "🎧 recebi seu audio, mas nao consegui entender nada (silencio ou ruido?). "
                    "Tenta de novo falando mais perto?")
        return

    part = {"kind": "voice", "transcript": texto, "quer_audio": True,
            "confirma": f"🎧 você disse: “{texto}”"}
    if caption:
        part["transcript"] += f"\n(Legenda escrita junto: {caption})"
    await _add_part(update, context, part, title_seed=texto)


async def _typing_simple(bot, chat_id, thread_id, stop: asyncio.Event):
    while not stop.is_set():
        try:
            await bot.send_chat_action(chat_id, ChatAction.TYPING, message_thread_id=thread_id)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=4)
        except asyncio.TimeoutError:
            pass


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    await reply(update, context,
                f"{ASSISTENTE} no ar. ✅\n"
                "Cada topico deste grupo e uma conversa separada.\n"
                "Crie um topico novo pra comecar um assunto novo.\n"
                "Use /new pra zerar a conversa do topico atual.")


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    key = thread_key(update)
    batches.pop(key, None)          # descarta lote pendente do topico
    sessions.pop(key, None)
    save_sessions(sessions)
    await reply(update, context, "\U0001f195 Conversa zerada neste topico. A proxima mensagem comeca do zero.")


async def on_topic_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensagens de servico do Telegram: topico criado/renomeado -> aprende o nome."""
    if not authorized(update):
        return
    remember_topic_name(update)
    msg = update.effective_message
    if msg and getattr(msg, "forum_topic_created", None) and msg.message_thread_id:
        try:
            await context.bot.unpin_all_forum_topic_messages(
                chat_id=msg.chat_id, message_thread_id=msg.message_thread_id)
            log.info("topico %s: desfixei a mensagem inicial", msg.message_thread_id)
        except Exception as e:
            log.warning("nao consegui desfixar topico %s: %s", msg.message_thread_id, e)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Tratador GLOBAL: nenhum erro mais passa calado. Loga e tenta avisar o dono."""
    log.error("erro nao tratado", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_chat:
            tid = (update.effective_message.message_thread_id
                   if update.effective_message else None)
            await context.bot.send_message(
                update.effective_chat.id,
                "⚠️ Tive um erro interno aqui, mas ja registrei. Pode mandar de novo?",
                message_thread_id=tid)
    except Exception:
        pass


def main():
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(MessageHandler(
        filters.StatusUpdate.FORUM_TOPIC_CREATED | filters.StatusUpdate.FORUM_TOPIC_EDITED,
        on_topic_service))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_error_handler(on_error)
    log.info("%s bot iniciando  (owner=%s  group=%s)", ASSISTENTE, OWNER_ID, GROUP_ID)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
