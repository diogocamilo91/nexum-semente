#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Semente — Aprendizado: coletor dos canais de YouTube que o DONO segue.

Junta o material bruto pro fechamento da noite: o que os canais da pessoa
lançaram nas últimas horas, via RSS público de uploads do YouTube (sem chave,
sem custo, sem API). Quem escreve bonito em cima disso é o snippet do
fechamento (claude headless) — este script só coleta.

Uso:
  aprendizado.py                  # lançamentos das últimas 30h (padrão)
  aprendizado.py --horas 48       # janela maior
  aprendizado.py --sem-shorts     # ignora #shorts
  aprendizado.py --achar <url|@handle>
                                  # descobre o channel_id de um canal (pra montar
                                  # a config na entrevista)

Config dos canais: ~/.config/semente/aprendizado_canais.json
  {"temas": {"nome do tema": [{"nome": "Canal", "id": "UCxxxx..."}, ...], ...}}
Sem dependência externa: só stdlib.
"""
import sys, os, json, re, argparse, urllib.request, datetime as dt
import xml.etree.ElementTree as ET
import concurrent.futures as cf

CONFIG = os.path.expanduser("~/.config/semente/aprendizado_canais.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
NS = {"a": "http://www.w3.org/2005/Atom"}


def http(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def agora_utc():
    return dt.datetime.now(dt.timezone.utc)


def parse_data(s):
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


# ---------- descobrir o channel_id (usado na entrevista) ----------
def achar_canal(alvo):
    """Recebe @handle, URL de canal ou URL de vídeo; devolve (channel_id, nome) ou erro."""
    alvo = alvo.strip()
    if alvo.startswith("UC") and len(alvo) == 24:
        return alvo, "(id direto)"
    if alvo.startswith("@"):
        alvo = "https://www.youtube.com/" + alvo
    if not alvo.startswith("http"):
        alvo = "https://www.youtube.com/@" + alvo
    pagina = http(alvo).decode("utf-8", "replace")
    # ordem importa: o 1º "channelId" solto da página pode ser de um canal
    # RELACIONADO (pegadinha real); canonical/externalId são o canal da página.
    m = (re.search(r'rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"', pagina)
         or re.search(r'"externalId":"(UC[\w-]{22})"', pagina)
         or re.search(r'"channelId":"(UC[\w-]{22})"', pagina)
         or re.search(r'channel/(UC[\w-]{22})', pagina))
    if not m:
        raise RuntimeError("não achei o channelId nessa página")
    cid = m.group(1)
    mn = re.search(r'<meta property="og:title" content="([^"]+)"', pagina)
    nome = mn.group(1) if mn else "?"
    return cid, nome


# ---------- coleta ----------
def uploads_canal(canal, limite_dt, sem_shorts):
    """Vídeos de um canal publicados depois de limite_dt."""
    out = []
    try:
        raw = http(f"https://www.youtube.com/feeds/videos.xml?channel_id={canal['id']}")
        root = ET.fromstring(raw)
        for e in root.findall("a:entry", NS):
            titulo = (e.findtext("a:title", default="", namespaces=NS) or "").strip()
            link_el = e.find("a:link", NS)
            link = link_el.get("href") if link_el is not None else ""
            pub = parse_data(e.findtext("a:published", default="", namespaces=NS))
            if pub is None or pub < limite_dt:
                continue
            short = ("/shorts/" in link) or ("#shorts" in titulo.lower())
            if sem_shorts and short:
                continue
            out.append({"titulo": titulo, "link": link, "pub": pub, "short": short})
    except Exception as ex:
        return {"erro": str(ex)[:80]}
    out.sort(key=lambda v: v["pub"], reverse=True)
    return out


def coletar(cfg, limite_dt, sem_shorts):
    temas = cfg.get("temas", {})
    tarefas = {}
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for tema, canais in temas.items():
            for c in canais:
                tarefas[ex.submit(uploads_canal, c, limite_dt, sem_shorts)] = (tema, c["nome"])
        dados = {}
        for fut in cf.as_completed(tarefas):
            tema, nome = tarefas[fut]
            dados.setdefault(tema, {})[nome] = fut.result()

    linhas = []
    total = 0
    falhas = []
    for tema, canais in temas.items():
        bloco = []
        for c in canais:
            nome = c["nome"]
            r = dados.get(tema, {}).get(nome, [])
            if isinstance(r, dict) and "erro" in r:
                falhas.append(nome)
                continue
            # vídeo cheio primeiro, short por último
            for v in sorted(r, key=lambda x: (x["short"], -x["pub"].timestamp())):
                d = v["pub"].astimezone().strftime("%d/%m")
                tag = "⚡short" if v["short"] else "🎬vídeo"
                bloco.append(f"   • [{tag}] [{nome}] {v['titulo']} ({d})\n     {v['link']}")
                total += 1
        if bloco:
            linhas.append(f" {tema}")
            linhas.extend(bloco)
    cab = f"=== YOUTUBE — {total} vídeo(s) novo(s) dos canais do dono ==="
    if falhas:
        cab += f"\n(falhou ler: {', '.join(falhas)})"
    if total == 0:
        return cab + "\n   (nenhum lançamento novo na janela)"
    return cab + "\n" + "\n".join(linhas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horas", type=float, default=30)
    ap.add_argument("--sem-shorts", action="store_true")
    ap.add_argument("--achar", help="descobre o channel_id de @handle/URL")
    args = ap.parse_args()

    if args.achar:
        try:
            cid, nome = achar_canal(args.achar)
            print(f'{{"nome": "{nome}", "id": "{cid}"}}')
        except Exception as e:
            print(f"ERRO: {e}", file=sys.stderr)
            sys.exit(1)
        return

    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    except OSError:
        print("(sem canais configurados — crie ~/.config/semente/aprendizado_canais.json)")
        return
    limite = agora_utc() - dt.timedelta(hours=args.horas)
    print(coletar(cfg, limite, args.sem_shorts))


if __name__ == "__main__":
    main()
