#!/usr/bin/env python3
"""
Transcritor de audio (Whisper rodando na propria VPS, de graca).
(Parte do kit NEXUM Semente. Configuracao em ~/.config/semente/config.env)

Uso:  transcribe.py <arquivo_de_audio>
Imprime SO o texto transcrito no stdout. Erro -> stderr + codigo != 0.

Roda como subprocesso (chamado pelo bot.py). De proposito separado:
- mantem o bot leve (o modelo so ocupa RAM enquanto transcreve; depois libera).
- isola qualquer travada do Whisper do processo do bot.

Motor: faster-whisper (CTranslate2) — eficiente em CPU, sem GPU.
Modelo (WHISPER_MODELO na config; baixa sozinho na 1a vez):
  - "small"  (padrao) ~460 MB em disco — bom equilibrio pra VPS de 2 GB de RAM
  - "base"   mais rapido, menos preciso (VPS muito fraca)
  - "medium" / "large-v3"  mais precisos, MAIS RAM (large-v3 so com 4 GB+)
"""

import os
import sys
from pathlib import Path

CONFIG_FILE = Path.home() / ".config" / "semente" / "config.env"
MODELS_DIR = str(Path(__file__).resolve().parent / "whisper-models")


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


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: transcribe.py <arquivo_de_audio>", file=sys.stderr)
        return 2
    audio = sys.argv[1]
    if not Path(audio).exists():
        print(f"arquivo nao encontrado: {audio}", file=sys.stderr)
        return 2

    cfg = load_config()
    model_size = cfg.get("WHISPER_MODELO", "small")
    idioma = cfg.get("IDIOMA_AUDIO", "pt")     # pular a deteccao = mais rapido e certeiro

    from faster_whisper import WhisperModel

    # int8 = baixa RAM; cpu_threads = nucleos da VPS
    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
        cpu_threads=os.cpu_count() or 2,
        download_root=MODELS_DIR,
    )

    # vad_filter corta silencio -> acelera audio longo.
    segments, _info = model.transcribe(
        audio,
        language=idioma or None,
        beam_size=5,
        vad_filter=True,
    )
    texto = "".join(seg.text for seg in segments).strip()
    print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
