#!/usr/bin/env python3
"""
falar.py : transforma TEXTO em VOZ (recado de voz pro Telegram).
(Parte do kit NEXUM Semente. Configuracao em ~/.config/semente/config.env)

E o espelho do transcribe.py:
- transcribe.py: audio  -> texto (Whisper / faster-whisper)
- falar.py     : texto  -> audio (Edge-TTS, com Piper de reserva)

Motor principal: Edge-TTS (vozes neurais da Microsoft).
  - De graca, com entonacao de verdade (sobe/desce, pausa na virgula).
  - Precisa de internet. Se a rede falhar, cai pro Piper (local, opcional).

Configuracao (config.env):
  TTS_VOZ        voz do Edge-TTS (padrao pt-BR-AntonioNeural; feminina: pt-BR-FranciscaNeural)
  TTS_VELOCIDADE ex.: "-5%" mais devagar (padrao "+0%")
  TTS_TOM        ex.: "+2Hz" (padrao "+0Hz")
  PIPER_VOZ      caminho do .onnx da voz Piper de reserva (opcional)

Uso (chamado pelo bot como subprocesso):
    python falar.py <arquivo_saida.ogg>
    (o TEXTO entra pela ENTRADA PADRAO / stdin — assim nao tem limite de tamanho)

Faz:
1. Edge-TTS gera um MP3 (ou Piper gera WAV, na reserva).
2. PyAV converte pra OGG/Opus 48 kHz (formato de "recado de voz" do Telegram),
   sem precisar de ffmpeg do sistema (o 'av' ja vem com os codecs).

Imprime, no fim, o caminho do .ogg gerado.
"""

import sys
import subprocess
import tempfile
from pathlib import Path

import av  # PyAV — ja instalado (o Whisper usa pra decodificar audio)

BASE = Path(__file__).resolve().parent
CONFIG_FILE = Path.home() / ".config" / "semente" / "config.env"


def load_config() -> dict:
    cfg = {}
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


_cfg = load_config()

# --- Motor principal: Edge-TTS ---
EDGE_VOICE = _cfg.get("TTS_VOZ", "pt-BR-AntonioNeural")
EDGE_RATE = _cfg.get("TTS_VELOCIDADE", "+0%")
EDGE_PITCH = _cfg.get("TTS_TOM", "+0Hz")

# --- Reserva: Piper (local, offline; OPCIONAL — so se a voz estiver baixada) ---
PIPER_VOICE = Path(_cfg.get("PIPER_VOZ", str(BASE / "piper-voices" / "pt_BR-faber-medium.onnx")))

# Teto pratico pra nao gerar audio gigante.
MAX_CHARS = 4000


def limpar(texto: str) -> str:
    """Tira o que nao se 'fala' bem em voz: marcadores de markdown, emojis soltos, links cruos.

    Nao precisa ser perfeito — so evita soletrar '#', '*', 'https://...'.
    """
    import re
    t = texto
    t = re.sub(r"```.*?```", " ", t, flags=re.S)        # blocos de codigo
    t = re.sub(r"`([^`]*)`", r"\1", t)                  # code inline
    t = re.sub(r"https?://\S+", "link", t)              # URLs viram a palavra "link"
    t = re.sub(r"[*_#>~|]", " ", t)                     # simbolos de markdown
    t = re.sub(r"^\s*[-•]\s*", "", t, flags=re.M)       # marcadores de lista
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def gerar_mp3_edge(texto: str, mp3_path: str) -> None:
    """Motor principal: Edge-TTS (Microsoft) -> MP3. Precisa de internet."""
    proc = subprocess.run(
        [sys.executable, "-m", "edge_tts",
         "--voice", EDGE_VOICE,
         "--rate", EDGE_RATE,
         "--pitch", EDGE_PITCH,
         "--text", texto,
         "--write-media", mp3_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    if proc.returncode != 0 or not Path(mp3_path).exists() or Path(mp3_path).stat().st_size == 0:
        raise RuntimeError((proc.stderr.decode().strip() or "edge-tts falhou")[-300:])


def gerar_wav_piper(texto: str, wav_path: str) -> None:
    """Reserva: Piper (local, offline) -> WAV. So funciona se a voz estiver baixada."""
    if not PIPER_VOICE.exists():
        raise RuntimeError(f"voz Piper nao instalada ({PIPER_VOICE}) — reserva indisponivel")
    proc = subprocess.run(
        [sys.executable, "-m", "piper", "-m", str(PIPER_VOICE), "-f", wav_path],
        input=texto.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr.decode().strip() or "piper falhou")[-300:])


def audio_para_ogg(src_path: str, ogg_path: str) -> None:
    """Converte qualquer audio (mp3/wav) -> OGG/Opus 48 kHz mono (recado de voz do Telegram)."""
    inp = av.open(src_path)
    out = av.open(ogg_path, "w", format="ogg")
    stream = out.add_stream("libopus", rate=48000)
    stream.bit_rate = 48000          # qualidade boa pra voz, arquivo leve
    # opus exige 48 kHz mono: reamostra o que sai do motor
    resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)

    for frame in inp.decode(audio=0):
        frame.pts = None
        for rs in resampler.resample(frame):
            for packet in stream.encode(rs):
                out.mux(packet)
    for packet in stream.encode(None):   # esvazia o encoder
        out.mux(packet)
    out.close()
    inp.close()


def gerar_audio(texto: str, ogg_path: str) -> None:
    """Tenta Edge-TTS; se falhar (rede), cai pro Piper. Nunca deixa o bot mudo."""
    # 1) Motor principal: Edge-TTS
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            mp3_path = tmp.name
        try:
            gerar_mp3_edge(texto, mp3_path)
            audio_para_ogg(mp3_path, ogg_path)
            return
        finally:
            Path(mp3_path).unlink(missing_ok=True)
    except Exception as e:
        print(f"edge-tts indisponivel ({e}); usando Piper de reserva", file=sys.stderr)

    # 2) Reserva: Piper (local)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        gerar_wav_piper(texto, wav_path)
        audio_para_ogg(wav_path, ogg_path)
    finally:
        Path(wav_path).unlink(missing_ok=True)


def main():
    if len(sys.argv) < 2:
        print("uso: falar.py <saida.ogg>  (texto vem pelo stdin)", file=sys.stderr)
        sys.exit(2)
    ogg_path = sys.argv[1]

    texto = limpar(sys.stdin.read())[:MAX_CHARS].strip()
    if not texto:
        print("texto vazio — nada a falar", file=sys.stderr)
        sys.exit(3)

    gerar_audio(texto, ogg_path)
    print(ogg_path)


if __name__ == "__main__":
    main()
