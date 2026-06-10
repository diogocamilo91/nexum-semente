#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Semente — saúde da VPS.

Coleta CPU/carga, memória, disco, serviços e uptime; SALVA histórico (CSV) a
cada chamada e sabe dizer, em português, como a máquina anda. Pensado pra rodar
sozinho (cron 30/30min via monitor-vps.sh) e entrar no fechamento do dia.

Só biblioteca padrão do Python — leve de propósito (roda em VPS de 1-2 GB).

Uso:
  saude_vps.py               -> salva histórico + imprime o retrato (fechamento / sob demanda)
  saude_vps.py --emergencia  -> salva histórico + imprime SÓ emergências (vazio se tudo ok)
  saude_vps.py --json        -> salva histórico + imprime os números crus

Configuração (~/.config/semente/config.env):
  MONITOR_SERVICOS  serviços vigiados, formato "Nome:padrão-do-pgrep,Nome2:padrão2"
                    (padrão se ausente: "Bot Telegram:bot.py")
Histórico: ~/semente-bin/log/vps-historico.csv
"""
import os, sys, csv, shutil, subprocess, datetime

HIST = os.path.expanduser("~/semente-bin/log/vps-historico.csv")
LOG_BACKUP = os.path.expanduser("~/semente-bin/log/backup.log")
REPO_BACKUP = os.path.expanduser("~/nexum")
CONFIG = os.path.expanduser("~/.config/semente/config.env")
NPROC = os.cpu_count() or 1

# Limites de alerta (mexer aqui pra afinar)
DISCO_ALERTA = 85      # % de disco: entra no retrato/fechamento
DISCO_CRITICO = 95     # % de disco: EMERGÊNCIA (avisa na hora)
MEM_LIVRE_MIN = 200    # MB disponíveis (VPS pequena: limite mais baixo)
CARGA_FATOR = 2.0      # load(1min) acima de NPROC*fator = sobrecarga
BACKUP_ATRASO_H = 3    # horas sem a rotina de backup rodar = cron morto


def ler_config():
    cfg = {}
    try:
        for ln in open(CONFIG):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return cfg


def servicos_vigiados():
    """MONITOR_SERVICOS="Nome:padrão,Nome2:padrão2" -> {nome: padrão do pgrep}."""
    bruto = ler_config().get("MONITOR_SERVICOS", "Bot Telegram:bot.py")
    serv = {}
    for parte in bruto.split(","):
        if ":" in parte:
            nome, padrao = parte.split(":", 1)
            if nome.strip() and padrao.strip():
                serv[nome.strip()] = padrao.strip()
    return serv


def _git(*args):
    r = subprocess.run(["git", "-C", REPO_BACKUP, *args],
                       capture_output=True, text=True, timeout=15)
    return r.stdout.strip()


def backup_status():
    """Saúde do backup pro GitHub. Dois sinais REAIS de problema:
    - atrasados: commits locais que não subiram (push falhando);
    - erro/horas: última linha do log foi ERRO, ou a rotina não roda há horas
      (cron morto). Medimos pelo LOG, não pela idade do commit: madrugada parada
      não tem commit ('sem mudancas') e isso NÃO é problema."""
    try:
        atrasados = int(_git("rev-list", "--count", "origin/main..HEAD") or 0)
    except Exception:
        atrasados = 0
    horas, erro = None, False
    try:
        ultima = ""
        with open(LOG_BACKUP) as f:
            for linha in f:
                if linha.strip():
                    ultima = linha.strip()
        if ultima:
            t = datetime.datetime.strptime(ultima[:19], "%Y-%m-%d %H:%M:%S")
            horas = round((datetime.datetime.now() - t).total_seconds() / 3600, 1)
            erro = "ERRO" in ultima
    except Exception:
        pass
    return {"atrasados": atrasados, "horas": horas, "erro": erro}


def coletar():
    load1, load5, load15 = os.getloadavg()
    mi = {}
    for ln in open("/proc/meminfo"):
        p = ln.split(":")
        if len(p) == 2:
            mi[p[0]] = int(p[1].strip().split()[0])
    mem_total = mi.get("MemTotal", 0) // 1024
    mem_avail = mi.get("MemAvailable", 0) // 1024
    du = shutil.disk_usage("/")
    up_s = int(float(open("/proc/uptime").read().split()[0]))
    serv = {}
    for nome, padrao in servicos_vigiados().items():
        try:
            n = subprocess.run(["pgrep", "-fc", padrao], capture_output=True, text=True)
            serv[nome] = int((n.stdout or "0").strip() or 0) > 0
        except Exception:
            serv[nome] = False
    return {
        "ts": datetime.datetime.now().strftime("%F %T"),
        "load1": round(load1, 2), "load5": round(load5, 2), "load15": round(load15, 2),
        "mem_total": mem_total, "mem_used": mem_total - mem_avail, "mem_avail": mem_avail,
        "disk_total_gb": round(du.total / 1024**3, 1),
        "disk_avail_gb": round(du.free / 1024**3, 1),
        "disk_used_pct": round(du.used / du.total * 100),
        "up_s": up_s, "serv": serv,
    }


def salvar(d):
    os.makedirs(os.path.dirname(HIST), exist_ok=True)
    novo = not os.path.exists(HIST)
    with open(HIST, "a", newline="") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["ts", "load1", "mem_used_mb", "mem_total_mb", "mem_avail_mb",
                        "disk_used_pct", "disk_avail_gb", "serv_off"])
        off = ",".join(k for k, v in d["serv"].items() if not v)
        w.writerow([d["ts"], d["load1"], d["mem_used"], d["mem_total"], d["mem_avail"],
                    d["disk_used_pct"], d["disk_avail_gb"], off])


def alertas(d):
    out = []
    if d["disk_used_pct"] >= DISCO_ALERTA:
        out.append(f"🗄️ Disco em {d['disk_used_pct']}% (só {d['disk_avail_gb']} GB livres) — perto de encher.")
    if d["mem_avail"] < MEM_LIVRE_MIN:
        out.append(f"💾 Memória apertada: só {d['mem_avail']} MB livres.")
    if d["load1"] > NPROC * CARGA_FATOR:
        out.append(f"🧠 CPU sobrecarregada: carga {d['load1']} (máquina tem {NPROC} núcleo(s)).")
    for nome, ok in d["serv"].items():
        if not ok:
            out.append(f"⚙️ Serviço {nome} CAIU — não achei o processo no ar.")
    b = backup_status()
    if b["atrasados"] > 0 or b["erro"]:
        out.append("🔄 Backup TRAVADO: a última rodada falhou (não subiu pro GitHub) "
                   "— ver ~/semente-bin/log/backup.log.")
    elif b["horas"] is not None and b["horas"] > BACKUP_ATRASO_H:
        out.append(f"🔄 Backup parado: a rotina não roda há {b['horas']}h "
                   "(o normal é de hora em hora) — pode ser o agendamento (cron) caído.")
    return out


def emergencias(d):
    """Só o que NÃO pode esperar o fechamento das 21h: serviço caído (assistente
    fora do ar) ou disco quase cheio. O resto vai no informe diário — a régua é
    UM relatório por dia; isto é a exceção de socorro."""
    out = []
    for nome, ok in d["serv"].items():
        if not ok:
            out.append(f"⚙️ Serviço {nome} CAIU — não achei o processo no ar.")
    if d["disk_used_pct"] >= DISCO_CRITICO:
        out.append(f"🗄️ Disco em {d['disk_used_pct']}% (só {d['disk_avail_gb']} GB livres) — quase cheio.")
    return out


def tendencia_disco(d):
    try:
        agora = datetime.datetime.strptime(d["ts"], "%F %T")
        alvo = agora - datetime.timedelta(hours=24)
        melhor = None
        for row in csv.DictReader(open(HIST)):
            try:
                t = datetime.datetime.strptime(row["ts"], "%F %T")
            except Exception:
                continue
            if t <= alvo:
                melhor = row
        if melhor:
            dif = d["disk_used_pct"] - int(melhor["disk_used_pct"])
            if dif > 0:
                return f" (subiu {dif} ponto(s) em 24h)"
            if dif < 0:
                return f" (caiu {abs(dif)} ponto(s) em 24h)"
            return " (estável nas últimas 24h)"
    except Exception:
        pass
    return ""


def dias_no_ar(up_s):
    d, h = up_s // 86400, (up_s % 86400) // 3600
    return f"{d} dia(s) e {h}h" if d else f"{h}h"


def retrato(d):
    al = alertas(d)
    linhas = ["🖥️ VPS — tudo saudável" if not al else "🖥️ VPS — ⚠️ atenção"]
    linhas.append(f"🧠 CPU: carga {d['load1']} (de {NPROC} núcleo(s)) — "
                  + ("folgada" if d["load1"] < NPROC else "ocupada"))
    linhas.append(f"💾 Memória: {d['mem_used']} MB usados de {d['mem_total']} MB "
                  f"({d['mem_avail']} MB livres)")
    linhas.append(f"🗄️ Disco: {d['disk_used_pct']}% cheio "
                  f"({d['disk_avail_gb']} GB livres){tendencia_disco(d)}")
    if d["serv"]:
        linhas.append("⚙️ Serviços: " + " · ".join(
            f"{n} {'✅' if ok else '❌'}" for n, ok in d["serv"].items()))
    b = backup_status()
    if b["atrasados"] > 0 or b["erro"]:
        linhas.append("🔄 Backup: ⚠️ a última rodada falhou (não subiu pro GitHub)")
    elif b["horas"] is not None and b["horas"] > BACKUP_ATRASO_H:
        linhas.append(f"🔄 Backup: ⚠️ a rotina não roda há {b['horas']}h")
    elif b["horas"] is not None:
        linhas.append(f"🔄 Backup: ✅ em dia (última rodada há {b['horas']}h)")
    else:
        linhas.append("🔄 Backup: (ainda sem log — módulo de backup instalado?)")
    linhas.append(f"⏱️ No ar há {dias_no_ar(d['up_s'])}")
    if al:
        linhas.append("")
        linhas += al
    return "\n".join(linhas)


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    d = coletar()
    try:
        salvar(d)
    except Exception as e:
        sys.stderr.write(f"falha ao salvar histórico: {e}\n")
    if arg == "--emergencia":
        em = emergencias(d)
        if em:
            print("🖥️ VPS — EMERGÊNCIA:\n" + "\n".join(em))
    elif arg == "--json":
        import json
        print(json.dumps(d, ensure_ascii=False))
    else:
        print(retrato(d))


if __name__ == "__main__":
    main()
