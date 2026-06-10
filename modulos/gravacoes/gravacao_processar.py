#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Semente — Gravações: transcreve UM áudio (Gemini) + resumo/avaliação (Claude)
e guarda tudo como .md na pasta de conhecimento do dono.

Fluxo:
  1. converte o áudio pra mp3 mono 16k (upload pequeno) com ffmpeg;
  2. sobe pro Gemini (File API) e pede a transcrição com separação de locutores;
     áudio > 30 min é FATIADO em blocos de 25 min e juntado (pega qualquer duração);
  3. chama o Claude (headless, a sessão já logada da VPS) pra escrever a ficha:
     tipo, resumo, decisões, pendências, destaques;
  4. grava ~/nexum/pessoal/gravacoes/AAAA-MM-DD--<nome>.md (transcrição + ficha).

Uso:  gravacao_processar.py <audio> [--titulo "nome bonito"]
Saída: imprime o caminho do .md gravado. Sai != 0 com erro no stderr se falhar.

Config (~/.config/semente/config.env):
  GEMINI_API_KEY    (obrigatória) chave do Google AI Studio
  GEMINI_MODELO     (opcional) padrão gemini-2.5-flash
  CLAUDE_BIN        (opcional) caminho do claude; padrão: acha no PATH
Dependências: ffmpeg/ffprobe (apt) e Python stdlib. Privacidade: o ÁUDIO vai pro
Gemini (Google) só pra transcrever; o .md final fica na VPS (e no backup do dono).
"""
import sys, os, re, json, time, shutil, datetime, subprocess, tempfile, argparse
import urllib.request, urllib.error
from pathlib import Path

CONFIG_ENV = os.path.expanduser(
    os.environ.get("SEMENTE_CONFIG", "~/.config/semente/config.env"))
DESTINO = Path(os.path.expanduser("~/nexum/pessoal/gravacoes"))
API = "https://generativelanguage.googleapis.com"

LIMITE_SEG = 1800   # até 30 min vai numa tacada só
CHUNK_SEG = 1500    # acima disso, blocos de 25 min

# Texto livre (NÃO JSON): cada fala numa linha "[mm:ss] Locutor N: texto".
# Linha a linha é robusto — uma linha torta a gente pula, sem perder o resto.
PROMPT_TRANSCR = (
    "Transcreva ESTE ÁUDIO em português do Brasil, na íntegra e fielmente, sem "
    "resumir nem inventar nem comentar. Separe por quem fala: rotule Locutor 1, "
    "Locutor 2, ... e mantenha o mesmo rótulo para a mesma voz. "
    "Escreva UMA FALA POR LINHA, EXATAMENTE neste formato:\n"
    "[mm:ss] Locutor N: o que foi dito\n"
    "onde mm:ss é o tempo (minutos:segundos desde o início) em que a fala começa "
    "(use h:mm:ss se passar de 60 min). Não escreva mais nada além dessas linhas."
)
LINHA_RE = re.compile(r"^\[\s*([\d:]+)\s*\]\s*(.*)$")


def ler_config():
    cfg = {}
    try:
        with open(CONFIG_ENV, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha and not linha.startswith("#") and "=" in linha:
                    k, v = linha.split("=", 1)
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return cfg


def falhar(msg):
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(1)


def _segundos(ts):
    p = [int(x) for x in ts.split(":") if x.isdigit()]
    if len(p) == 3:
        return p[0] * 3600 + p[1] * 60 + p[2]
    if len(p) == 2:
        return p[0] * 60 + p[1]
    return p[0] if p else 0


def _fmt(seg):
    seg = int(seg)
    if seg >= 3600:
        return f"{seg//3600}:{seg%3600//60:02d}:{seg%60:02d}"
    return f"{seg//60:02d}:{seg%60:02d}"


def duracao_audio(audio):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(audio)],
            capture_output=True, text=True)
        return round(float(r.stdout.strip()), 1)
    except Exception:
        return 0.0


def converter(audio, dest, inicio=None, dur=None):
    """qualquer formato -> mp3 mono 16k (leve, suficiente pra fala)."""
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if inicio is not None:
        cmd += ["-ss", str(inicio)]
    cmd += ["-i", str(audio)]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-ac", "1", "-ar", "16000", "-b:a", "32k", str(dest)]
    subprocess.run(cmd, check=True)


def _post(url, data, headers, timeout=300):
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.headers, r.read()


def subir(mp3, key):
    """Sobe o arquivo (File API, resumable). Retorna uri."""
    size = os.path.getsize(mp3)
    h, _ = _post(
        f"{API}/upload/v1beta/files?key={key}",
        json.dumps({"file": {"display_name": "grav"}}).encode(),
        {"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
         "X-Goog-Upload-Header-Content-Length": str(size),
         "X-Goog-Upload-Header-Content-Type": "audio/mp3",
         "Content-Type": "application/json"})
    upurl = h["X-Goog-Upload-URL"]
    _h, body = _post(
        upurl, Path(mp3).read_bytes(),
        {"X-Goog-Upload-Command": "upload, finalize", "X-Goog-Upload-Offset": "0",
         "Content-Length": str(size)}, timeout=600)
    finfo = json.loads(body)["file"]
    name, uri = finfo["name"], finfo["uri"]
    for _ in range(60):  # espera ficar ATIVO
        with urllib.request.urlopen(f"{API}/v1beta/{name}?key={key}") as r:
            st = json.loads(r.read())["state"]
        if st == "ACTIVE":
            return uri
        if st == "FAILED":
            raise RuntimeError("upload do áudio FALHOU no Gemini")
        time.sleep(2)
    raise RuntimeError("áudio não ficou ATIVO a tempo no Gemini")


def gemini_transcrever(uri, key, modelo):
    """Chama o modelo com o áudio. Retorna o texto cru (linhas [mm:ss] ...)."""
    payload = {
        "contents": [{"parts": [
            {"file_data": {"mime_type": "audio/mp3", "file_uri": uri}},
            {"text": PROMPT_TRANSCR},
        ]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 65536},
    }
    req = urllib.request.Request(
        f"{API}/v1beta/models/{modelo}:generateContent?key={key}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        d = json.loads(r.read())
    try:
        partes = d["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in partes)
    except (KeyError, IndexError):
        razao = (d.get("candidates") or [{}])[0].get("finishReason", "?")
        raise RuntimeError(f"Gemini não devolveu texto (finishReason={razao})")


def parse_linhas(texto, offset=0.0):
    """[(segundos, 'Locutor N: fala')]; linha torta é pulada, sem drama."""
    out = []
    for linha in texto.splitlines():
        linha = linha.strip()
        m = LINHA_RE.match(linha)
        if not m:
            continue
        out.append((_segundos(m.group(1)) + offset, m.group(2).strip()))
    return out


def transcrever_tudo(audio, key, modelo, tmp):
    """Converte, fatia se precisar, transcreve. Devolve (segmentos, duracao)."""
    dur = duracao_audio(audio)
    if dur <= 0:
        raise RuntimeError("não consegui ler a duração (arquivo corrompido? ffprobe?)")
    segs = []
    if dur <= LIMITE_SEG:
        mp3 = os.path.join(tmp, "todo.mp3")
        converter(audio, mp3)
        segs = parse_linhas(gemini_transcrever(subir(mp3, key), key, modelo))
    else:
        ini = 0
        while ini < dur:
            mp3 = os.path.join(tmp, f"bloco-{ini}.mp3")
            converter(audio, mp3, inicio=ini, dur=CHUNK_SEG)
            texto = gemini_transcrever(subir(mp3, key), key, modelo)
            segs.extend(parse_linhas(texto, offset=ini))
            ini += CHUNK_SEG
    if not segs:
        raise RuntimeError("transcrição veio vazia (áudio sem fala? formato estranho?)")
    return segs, dur


def claude_ficha(transcricao, titulo, claude_bin):
    """Pede a ficha (resumo/decisões/pendências) pro Claude headless. '' se falhar."""
    emptymcp = os.path.expanduser("~/.config/semente/empty-mcp.json")
    if not os.path.exists(emptymcp):
        os.makedirs(os.path.dirname(emptymcp), exist_ok=True)
        Path(emptymcp).write_text('{"mcpServers":{}}')
    prompt = f"""Você é um assistente pessoal avaliando a transcrição de um áudio do seu dono ("{titulo}"). A transcrição automática erra com confiança; leia tudo com crítica. Escreva em português do Brasil, em Markdown, EXATAMENTE estas seções (e nada mais):

## Ficha
- **Tipo:** (reunião, conversa, palestra/aula, nota de voz, outro)
- **Quem fala:** (o que der pra inferir; diga o grau de certeza)
- **Confiança na transcrição:** alta/média/baixa + por quê em 1 frase

## Resumo
(do que se trata, em até 6 linhas)

## Decisões
(o que ficou decidido; "nenhuma identificada" se não houver)

## Pendências
(combinados/tarefas, com quem ficou cada uma; "nenhuma identificada" se não houver)

## Destaques
(3 a 6 momentos-chave, cada um com o tempo [mm:ss] e a frase)

TRANSCRIÇÃO:
{transcricao[:180000]}"""
    try:
        r = subprocess.run(
            [claude_bin, "-p", prompt, "--output-format", "json",
             "--permission-mode", "bypassPermissions",
             "--mcp-config", emptymcp, "--strict-mcp-config"],
            capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            return ""
        return (json.loads(r.stdout).get("result") or "").strip()
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--titulo", default="")
    args = ap.parse_args()

    audio = Path(args.audio)
    if not audio.is_file():
        falhar(f"arquivo não existe: {audio}")
    for dep in ("ffmpeg", "ffprobe"):
        if not shutil.which(dep):
            falhar(f"{dep} não instalado (sudo apt install -y ffmpeg)")

    cfg = ler_config()
    key = cfg.get("GEMINI_API_KEY", "")
    if not key:
        falhar(f"GEMINI_API_KEY faltando em {CONFIG_ENV}")
    modelo = cfg.get("GEMINI_MODELO", "gemini-2.5-flash")
    claude_bin = cfg.get("CLAUDE_BIN") or shutil.which("claude") \
        or os.path.expanduser("~/.local/bin/claude")

    titulo = args.titulo or audio.stem
    with tempfile.TemporaryDirectory(prefix="semente-grav-") as tmp:
        segs, dur = transcrever_tudo(audio, key, modelo, tmp)

    transcricao = "\n".join(f"[{_fmt(t)}] {fala}" for t, fala in segs)
    ficha = claude_ficha(transcricao, titulo, claude_bin)
    if not ficha:
        ficha = ("## Ficha\n*(a avaliação automática falhou — peça ao assistente: "
                 "\"avalia a gravação X\" que ele lê a transcrição abaixo e completa)*")

    DESTINO.mkdir(parents=True, exist_ok=True)
    hoje = datetime.date.today().isoformat()
    nome_limpo = re.sub(r"[^\w\s.-]", "", titulo).strip().replace(" ", "-")[:60]
    md = DESTINO / f"{hoje}--{nome_limpo}.md"
    n = 2
    while md.exists():
        md = DESTINO / f"{hoje}--{nome_limpo}-{n}.md"
        n += 1

    md.write_text(
        f"# 🎙️ {titulo}\n\n"
        f"- **Data do processamento:** {hoje}\n"
        f"- **Duração:** {_fmt(dur)}\n"
        f"- **Arquivo original:** {audio.name}\n"
        f"- **Falas transcritas:** {len(segs)}\n\n"
        f"{ficha}\n\n"
        f"---\n\n## Transcrição completa\n\n{transcricao}\n",
        encoding="utf-8")
    print(str(md))


if __name__ == "__main__":
    main()
