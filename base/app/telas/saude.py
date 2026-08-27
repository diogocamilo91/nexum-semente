# -*- coding: utf-8 -*-
"""
Tela "A casa" — o painel de saúde da máquina, em português de gente.

Só LEITURA: mede disco/memória/carga, pergunta o status das peças (nunca liga
nem desliga nada), lê o log do backup, traduz os despertadores do sistema e
mostra os últimos erros dos logs. Se um pedaço não puder ser lido, aquele
pedaço mostra um recado honesto — a tela nunca quebra.

Só biblioteca padrão + Flask (a máquina pode ser pequena).
"""
import os
import re
import glob
import html
import time
import shutil
import subprocess
import datetime

from flask import Response, jsonify

CHAVE = "casa"
TITULO = "A casa"
ICONE = "pulso"
GRUPO = "casa"
ORDEM = 10

TEMPO_COMANDO = 3          # segundos: comando que trava não pode segurar a tela
TEMPO_TOTAL_PECAS = 9      # segundos no TOTAL perguntando às peças (a tela tem que abrir)
BACKUP_ATRASO_H = 3        # horas sem cópia = chip vermelho
MAX_ERROS = 20             # linhas de erro mostradas
MAX_ARQUIVOS_LOG = 25      # logs varridos (os mais recentes)
DIAS_LOG = 30              # registro mais velho que isso é considerado parado


# ─────────────────────────── ferramentas de base ───────────────────────────

def _esc(t):
    """Escapa pra HTML. Campo faltando vira vazio — nunca a palavra 'None'."""
    if t is None:
        return ""
    try:
        return html.escape(str(t), quote=True)
    except Exception:
        return ""


def _casa_dir(casca, nome, padrao):
    """Caminho vindo da casca, com queda pro padrão do kit."""
    try:
        v = getattr(casca, nome, None)
        if v:
            return os.path.expanduser(str(v))
    except Exception:
        pass
    return os.path.expanduser(padrao)


def _rodar(argumentos):
    """Roda um comando de LEITURA. Devolve (deu_certo, saída). Nunca levanta."""
    try:
        r = subprocess.run(
            argumentos, capture_output=True, text=True, errors="replace",
            timeout=TEMPO_COMANDO, stdin=subprocess.DEVNULL,
        )
        saida = ((r.stdout or "") + ("\n" + r.stderr if r.stderr else "")).strip()
        return (r.returncode == 0), saida
    except Exception:
        return False, ""


def _num(v, casas=0):
    """Número em português: 1234.5 -> '1.234,5'."""
    try:
        t = ("%%.%df" % casas) % float(v)
        inteiro, _, dec = t.partition(".")
        sinal = ""
        if inteiro.startswith("-"):
            sinal, inteiro = "-", inteiro[1:]
        blocos = []
        while len(inteiro) > 3:
            blocos.insert(0, inteiro[-3:])
            inteiro = inteiro[:-3]
        blocos.insert(0, inteiro)
        saida = sinal + ".".join(blocos)
        return saida + ("," + dec if dec else "")
    except Exception:
        return str(v)


def _mb_txt(mb):
    """740 -> '740 MB' · 2048 -> '2 GB' (a pessoa lê, não converte)."""
    try:
        mb = float(mb)
    except Exception:
        return "?"
    if mb >= 1024:
        return "%s GB" % _num(mb / 1024.0, 1)
    return "%s MB" % _num(mb)


def _plural(n, um, muitos):
    return um if abs(n) == 1 else muitos


def _duracao(segundos):
    """3 dias e 4 horas · 5 horas e 12 minutos · 40 minutos."""
    try:
        s = int(segundos)
    except Exception:
        return "algum tempo"
    if s < 60:
        return "menos de um minuto"
    d, h, m = s // 86400, (s % 86400) // 3600, (s % 3600) // 60
    if d:
        p = "%d %s" % (d, _plural(d, "dia", "dias"))
        return p + (" e %d %s" % (h, _plural(h, "hora", "horas")) if h else "")
    if h:
        p = "%d %s" % (h, _plural(h, "hora", "horas"))
        return p + (" e %d %s" % (m, _plural(m, "minuto", "minutos")) if m else "")
    return "%d %s" % (m, _plural(m, "minuto", "minutos"))


def _encurta(texto, tamanho):
    try:
        t = " ".join(str(texto).split())
        return t if len(t) <= tamanho else t[:tamanho] + "…"
    except Exception:
        return ""


def _quando(dt):
    """Momento em português: 'hoje às 14:07', 'ontem às 23:10', 'em 12/08/2026 às 09:00'."""
    try:
        hoje = datetime.date.today()
        hora = dt.strftime("%H:%M")
        if dt.date() == hoje:
            return "hoje às " + hora
        if dt.date() == hoje - datetime.timedelta(days=1):
            return "ontem às " + hora
        return "em %s às %s" % (dt.strftime("%d/%m/%Y"), hora)
    except Exception:
        return "em data desconhecida"


def _agora_txt():
    try:
        return datetime.datetime.now().strftime("medido em %d/%m/%Y às %H:%M")
    except Exception:
        return ""


# ─────────────────────────── 1) os números da máquina ───────────────────────

def _medir_maquina():
    """Disco, memória, tempo ligada e carga. Cada medida é opcional."""
    d = {}
    try:
        u = shutil.disk_usage("/")
        d["disco_total_gb"] = u.total / 1024.0 ** 3
        d["disco_livre_gb"] = u.free / 1024.0 ** 3
        d["disco_pct"] = int(round(u.used * 100.0 / u.total)) if u.total else None
    except Exception:
        pass
    try:
        mi = {}
        with open("/proc/meminfo") as f:
            for ln in f:
                p = ln.split(":")
                if len(p) == 2:
                    try:
                        mi[p[0].strip()] = int(p[1].strip().split()[0])
                    except Exception:
                        pass
        if mi.get("MemTotal"):
            d["mem_total_mb"] = mi["MemTotal"] // 1024
            livre = mi.get("MemAvailable")
            if livre is None:
                livre = mi.get("MemFree")
            if livre is not None:          # sem a medida eu NÃO invento um zero
                d["mem_livre_mb"] = livre // 1024
    except Exception:
        pass
    try:
        with open("/proc/uptime") as f:
            d["ligada_s"] = int(float(f.read().split()[0]))
    except Exception:
        pass
    try:
        d["carga"] = os.getloadavg()[0]
        d["nucleos"] = os.cpu_count() or 1
    except Exception:
        pass
    return d


def _html_kpis(m):
    """Linha de números grandes. Cada número que faltar simplesmente não aparece."""
    itens = []
    try:
        if m.get("disco_pct") is not None:
            pct = m["disco_pct"]
            cls = "erro" if pct >= 90 else ("atencao" if pct >= 80 else "")
            itens.append((
                "%s GB" % _num(m.get("disco_livre_gb", 0), 1), cls,
                "livres no disco · %d%% usado" % pct,
            ))
    except Exception:
        pass
    try:
        if m.get("mem_total_mb") and m.get("mem_livre_mb") is not None:
            livre = m["mem_livre_mb"]
            cls = "erro" if livre < 150 else ("atencao" if livre < 300 else "")
            itens.append((
                _mb_txt(livre), cls,
                "de memória livre (de %s no total)" % _mb_txt(m["mem_total_mb"]),
            ))
    except Exception:
        pass
    try:
        if m.get("ligada_s") is not None:
            s = m["ligada_s"]
            if s >= 86400:
                grande = "%d %s" % (s // 86400, _plural(s // 86400, "dia", "dias"))
            elif s >= 3600:
                grande = "%d h" % (s // 3600)
            else:
                grande = "%d min" % max(1, s // 60)
            itens.append((grande, "", "ligada sem reiniciar"))
    except Exception:
        pass
    try:
        if m.get("carga") is not None:
            carga, nuc = m["carga"], m.get("nucleos", 1)
            if carga > nuc * 2:
                cls, palavra = "erro", "sobrecarregada"
            elif carga > nuc:
                cls, palavra = "atencao", "ocupada"
            else:
                cls, palavra = "", "folgada"
            itens.append((_num(carga, 2), cls, "de trabalho agora · %s" % palavra))
    except Exception:
        pass

    if not itens:
        return ("<div class=vazio>Não consegui medir a máquina agora. "
                "Tente atualizar em alguns instantes.</div>")
    partes = []
    for grande, cls, legenda in itens:
        partes.append("<div class='kpi%s'><b>%s</b><span>%s</span></div>"
                      % ((" " + cls) if cls else "", _esc(grande), _esc(legenda)))
    return "<div class=kpis>" + "".join(partes) + "</div>"


# ─────────────────────────── 2) as peças do assistente ──────────────────────

_NOMES_PECA = {
    "semente-bot": "Assistente no Telegram",
    "semente-chat": "Chat no navegador",
    "semente-app": "Aplicativo (esta tela)",
    "semente-whatsapp": "Espelho do WhatsApp",
    "semente-gravacoes": "Transcrição de gravações",
    "semente-bin": "Rotinas da máquina",
}


def _nome_peca(pasta):
    base = os.path.basename(pasta.rstrip("/"))
    if base in _NOMES_PECA:
        return _NOMES_PECA[base]
    limpo = base.replace("semente-", "").replace("-", " ").replace("_", " ").strip()
    return limpo.capitalize() if limpo else base


def _tempo_do_app():
    """Há quanto tempo ESTE programa está no ar (sem depender de nada de fora)."""
    try:
        with open("/proc/self/stat") as f:
            campos = f.read().rsplit(") ", 1)[-1].split()
        inicio_ticks = float(campos[19])           # 22º campo do arquivo
        hz = os.sysconf("SC_CLK_TCK") or 100
        with open("/proc/uptime") as f:
            ligada = float(f.read().split()[0])
        return max(0, int(ligada - inicio_ticks / hz))
    except Exception:
        return None


def _minha_pasta():
    """A pasta onde ESTE app está instalado — pra ele não se listar duas vezes."""
    try:
        return os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    except Exception:
        return ""


def _sabe_status(caminho):
    """Só pergunto 'status' a um painel de controle que conhece essa palavra.
    Script que não a conhece pode fazer OUTRA coisa com ela — e aqui ninguém liga
    nem desliga nada."""
    try:
        with open(caminho, "r", errors="replace") as f:
            return "status" in f.read(200000)
    except Exception:
        return False


def _ler_pecas():
    """Pergunta 'status' pra cada painel de controle do kit. Só olha."""
    pecas = []
    seg = _tempo_do_app()
    pecas.append({
        "nome": "Aplicativo (esta tela)",
        "estado": "ok",
        "detalhe": ("no ar há " + _duracao(seg)) if seg is not None else "respondendo agora",
    })
    try:
        casa = os.path.expanduser("~")
        achados = sorted(glob.glob(os.path.join(casa, "semente-*", "*ctl.sh")))
    except Exception:
        achados = []
    ordem_boa = {"semente-bot": 0, "semente-chat": 1}
    try:
        achados.sort(key=lambda c: (ordem_boa.get(os.path.basename(os.path.dirname(c)), 5),
                                    os.path.basename(os.path.dirname(c))))
    except Exception:
        pass
    minha = _minha_pasta()
    prazo = time.monotonic() + TEMPO_TOTAL_PECAS
    vistos = set()
    for ctl in achados:
        pasta = os.path.dirname(ctl)
        if pasta in vistos:
            continue
        vistos.add(pasta)
        try:
            if minha and os.path.realpath(pasta) == minha:
                continue                    # este app já está na lista, ali em cima
        except Exception:
            pass
        nome = _nome_peca(pasta)
        pausado = False
        try:
            pausado = (os.path.exists(os.path.join(pasta, "PAUSED"))
                       or os.path.exists(pasta + ".PAUSED"))
        except Exception:
            pass
        if not pausado and time.monotonic() >= prazo:
            pecas.append({"nome": nome, "estado": "atencao",
                          "detalhe": "não deu tempo de perguntar como ela está"})
            continue
        if pausado:
            pecas.append({"nome": nome, "estado": "atencao",
                          "detalhe": "desligada de propósito"})
            continue
        if not _sabe_status(ctl):
            pecas.append({"nome": nome, "estado": "atencao",
                          "detalhe": "não sei perguntar como ela está"})
            continue
        ok, saida = _rodar(["bash", ctl, "status"])
        alto = (saida or "").upper()
        if "PAUSAD" in alto:
            estado, detalhe = "atencao", "desligada de propósito"
        elif "VIVO" in alto or "RODANDO" in alto or "ATIVO" in alto or "RUNNING" in alto:
            estado, detalhe = "ok", "no ar"
        elif "PARAD" in alto or "STOPPED" in alto or "MORTO" in alto or "OFF" in alto:
            estado, detalhe = "erro", "fora do ar"
        elif not saida:
            estado, detalhe = "atencao", "não consegui perguntar como ela está"
        else:
            estado, detalhe = "atencao", "respondeu algo que eu não sei ler"
        pecas.append({"nome": nome, "estado": estado, "detalhe": detalhe})
    return pecas


def _html_pecas(pecas):
    try:
        if not pecas:
            return ("<div class=vazio>Ainda não encontrei as peças do assistente "
                    "nesta máquina.</div>")
        linhas = []
        for p in pecas:
            chip = p.get("estado") if p.get("estado") in ("ok", "erro") else "atencao"
            rotulo = {"ok": "de pé", "erro": "parada", "atencao": "atenção"}[chip]
            linhas.append(
                "<div class=item><div class=casa-linha>"
                "<span><b>%s</b><br><span class=fraco>%s</span></span>"
                "<span class='chip %s'>%s</span>"
                "</div></div>" % (_esc(p.get("nome", "")), _esc(p.get("detalhe", "")),
                                  chip, _esc(rotulo))
            )
        return "<div class=lista>" + "".join(linhas) + "</div>"
    except Exception:
        return "<div class=vazio>Não consegui olhar as peças do assistente agora.</div>"


# ─────────────────────────── 3) o backup ────────────────────────────────────

_TS_LOG = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})")
_TS_BR = re.compile(r"(\d{2})/(\d{2})/(\d{4})[ ,]+(\d{2}):(\d{2})")


def _achar_data(texto):
    try:
        cabeca = texto[:48]
        m = _TS_LOG.search(cabeca)
        if m:
            a, me, d, h, mi, s = (int(x) for x in m.groups())
            return datetime.datetime(a, me, d, h, mi, s)
        m = _TS_BR.search(cabeca)
        if m:
            d, me, a, h, mi = (int(x) for x in m.groups())
            return datetime.datetime(a, me, d, h, mi)
    except Exception:
        pass
    return None


def _ultima_linha(caminho):
    """A última linha com conteúdo — lendo só o FIM do arquivo (registro grande
    não pode segurar a tela)."""
    try:
        for ln in reversed(_ultimas_linhas(caminho, max_bytes=60000, max_linhas=200)):
            if ln.strip():
                return ln.strip()
    except Exception:
        pass
    return ""


def _ler_backup(dir_bin):
    caminho = os.path.join(dir_bin, "log", "backup.log")
    dados = {"existe": False, "estado": "atencao", "texto": "", "extra": ""}
    try:
        if not os.path.exists(caminho):
            dados["texto"] = "Ainda não há registro de cópia de segurança nesta máquina."
            return dados
        dados["existe"] = True
        linha = _ultima_linha(caminho)
        if not linha:
            dados["texto"] = "O registro de cópias existe, mas ainda está vazio."
            return dados
        quando = _achar_data(linha)
        if quando is None:
            try:
                quando = datetime.datetime.fromtimestamp(os.path.getmtime(caminho))
            except Exception:
                quando = None
        alto = linha.upper()
        houve_erro = (("ERRO" in alto or "FALH" in alto)
                      and not _FALSO_ERRO.search(linha))
        atraso_h = None
        if quando is not None:
            atraso_h = (datetime.datetime.now() - quando).total_seconds() / 3600.0
        if houve_erro:
            dados["estado"] = "erro"
            dados["texto"] = "A última tentativa de cópia falhou."
        elif atraso_h is not None and atraso_h > BACKUP_ATRASO_H:
            dados["estado"] = "erro"
            dados["texto"] = "A cópia de segurança está atrasada."
        else:
            dados["estado"] = "ok"
            dados["texto"] = "A cópia de segurança está em dia."
        if quando is not None:
            dados["extra"] = "última cópia %s" % _quando(quando)
            if atraso_h is not None and atraso_h >= 1:
                dados["extra"] += " (há %s)" % _duracao(atraso_h * 3600)
        else:
            dados["extra"] = "não consegui descobrir a data da última cópia"
        corpo = re.sub(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}\s*", "", linha)
        dados["linha"] = corpo[:200]
    except Exception:
        dados["texto"] = "Não consegui ler o registro de cópias agora."
    return dados


def _html_backup(b):
    try:
        if not b.get("existe"):
            recado = b.get("texto") or ("Ainda não há registro de cópia de segurança "
                                        "nesta máquina.")
            return "<div class=vazio>%s</div>" % _esc(recado)
        chip = {"ok": "ok", "erro": "erro"}.get(b.get("estado"), "atencao")
        rotulo = {"ok": "em dia", "erro": "atrasada", "atencao": "verificar"}[
            "ok" if chip == "ok" else ("erro" if chip == "erro" else "atencao")]
        detalhe = b.get("extra", "")
        crua = b.get("linha", "")
        return (
            "<div class=casa-linha><span><b>%s</b><br><span class=fraco>%s</span></span>"
            "<span class='chip %s'>%s</span></div>%s"
            % (_esc(b.get("texto", "")), _esc(detalhe), chip, _esc(rotulo),
               ("<p class='fraco casa-mono'>%s</p>" % _esc(crua)) if crua else "")
        )
    except Exception:
        return "<div class=vazio>Não consegui ler o registro de cópias agora.</div>"


# ─────────────────────────── 4) os despertadores (cron) ─────────────────────

_DIAS_SEMANA = {
    "0": "domingo", "1": "segunda-feira", "2": "terça-feira", "3": "quarta-feira",
    "4": "quinta-feira", "5": "sexta-feira", "6": "sábado", "7": "domingo",
    "sun": "domingo", "mon": "segunda-feira", "tue": "terça-feira",
    "wed": "quarta-feira", "thu": "quinta-feira", "fri": "sexta-feira", "sat": "sábado",
}

_ATALHOS = {
    "@reboot": "toda vez que a máquina liga",
    "@yearly": "uma vez por ano",
    "@annually": "uma vez por ano",
    "@monthly": "uma vez por mês",
    "@weekly": "uma vez por semana",
    "@daily": "todo dia à meia-noite",
    "@midnight": "todo dia à meia-noite",
    "@hourly": "de hora em hora",
}

_TAREFAS = {
    "backup.sh": "guarda uma cópia de segurança de tudo",
    "monitor-vps.sh": "vigia a máquina e avisa se algo cair",
    "saude_vps.py": "mede a saúde da máquina",
    "fechamento-dia.sh": "monta o resumo do dia",
    "alerta.sh": "manda um aviso pra você",
    "nexumctl.sh": "cuida do assistente no Telegram",
    "chatctl.sh": "cuida do chat no navegador",
    "news.py": "busca as notícias do dia",
    "gmail.py": "dá uma olhada nos e-mails",
    "agenda.py": "dá uma olhada na agenda",
    "drive.py": "cuida dos arquivos do Google Drive",
    "gdoc.py": "cuida dos documentos do Google",
    "aprendizado.py": "separa o material de estudo",
}


def _hora_txt(minuto, hora):
    try:
        h, m = int(hora), int(minuto)
        return ("às %02dh" % h) if m == 0 else ("às %02d:%02d" % (h, m))
    except Exception:
        return ""


def _frase_do_horario(expr):
    """Traduz a expressão do despertador. Devolve None se for exótica demais."""
    try:
        p = expr.split()
        if len(p) != 5:
            return None
        mi, ho, dm, me, ds = p
        so_dia = (dm == "*" and me == "*" and ds == "*")
        if mi == "*" and ho == "*" and so_dia:
            return "a cada minuto"
        if mi.startswith("*/") and mi[2:].isdigit() and ho == "*" and so_dia:
            n = int(mi[2:])
            return "a cada minuto" if n == 1 else "de %d em %d minutos" % (n, n)
        if mi.isdigit() and ho == "*" and so_dia:
            return ("de hora em hora" if int(mi) == 0
                    else "de hora em hora (aos %d minutos)" % int(mi))
        if "," in mi and ho == "*" and so_dia:
            n = len([x for x in mi.split(",") if x.strip()])
            return "%d vezes por hora" % n
        if mi.isdigit() and ho.startswith("*/") and ho[2:].isdigit() and so_dia:
            n = int(ho[2:])
            return "de hora em hora" if n == 1 else "de %d em %d horas" % (n, n)
        if mi.isdigit() and ho.isdigit():
            base = _hora_txt(mi, ho)
            if so_dia:
                return "todo dia " + base
            if ds != "*" and dm == "*" and me == "*":
                nomes = [_DIAS_SEMANA.get(x.strip().lower(), "") for x in ds.split(",")]
                nomes = [n for n in nomes if n]
                if nomes:
                    return "toda %s %s" % (" e ".join(nomes), base)
            if dm.isdigit() and me == "*" and ds == "*":
                return "todo dia %d de cada mês %s" % (int(dm), base)
        if mi.isdigit() and "," in ho and so_dia:
            horas = [x.strip() for x in ho.split(",") if x.strip().isdigit()]
            if horas:
                textos = [_hora_txt(mi, h) for h in horas]
                return "todo dia " + " e ".join(textos)
    except Exception:
        pass
    return None


def _nome_da_tarefa(comando):
    try:
        limpo = re.split(r"\s+[12]?>+", comando)[0].strip()
        alvos = []
        for tok in limpo.split():
            base = os.path.basename(tok.strip("'\""))
            if base.endswith(".sh") or base.endswith(".py"):
                alvos.append(base)
        base = alvos[0] if alvos else os.path.basename(limpo.split(" ")[0] or limpo)
        nome = _TAREFAS.get(base)
        if nome:
            if base in ("nexumctl.sh", "chatctl.sh") and " start" in (" " + limpo):
                return nome.replace("cuida d", "religa, se cair, ")
            return nome
        bonito = base.replace(".sh", "").replace(".py", "").replace("-", " ").replace("_", " ")
        return bonito.strip().capitalize() or "tarefa da máquina"
    except Exception:
        return "tarefa da máquina"


def _ler_despertadores():
    """Lista o que roda sozinho. Devolve (lista, recado_de_erro)."""
    ok, saida = _rodar(["crontab", "-l"])
    if not saida:
        if ok:
            return [], ""
        return [], "vazio"
    itens = []
    for bruto in saida.splitlines():
        ln = bruto.strip()
        if not ln or ln.startswith("#"):
            continue
        if re.match(r"^[A-Z_]+\s*=", ln):          # ajuste do ambiente, não é tarefa
            continue
        try:
            if ln.startswith("@"):
                pedaco = ln.split(None, 1)
                atalho = pedaco[0].lower()
                comando = pedaco[1] if len(pedaco) > 1 else ""
                frase = _ATALHOS.get(atalho)
                itens.append({"quando": frase or "em um horário especial",
                              "o_que": _nome_da_tarefa(comando)})
                continue
            partes = ln.split(None, 5)
            if len(partes) < 6:
                continue
            expr = " ".join(partes[:5])
            comando = partes[5]
            frase = _frase_do_horario(expr)
            itens.append({"quando": frase or "em horários específicos",
                          "o_que": _nome_da_tarefa(comando)})
        except Exception:
            continue
    return itens, ""


def _html_despertadores(itens, recado):
    try:
        if recado == "vazio" and not itens:
            return ("<div class=vazio>Não consegui ver a lista de tarefas automáticas "
                    "desta máquina. Pode ser que ainda não exista nenhuma.</div>")
        if not itens:
            return ("<div class=vazio>Nada está programado pra rodar sozinho por aqui — "
                    "nem cópia de segurança, nem vigia.</div>")
        linhas = []
        for it in itens:
            linhas.append(
                "<div class=item><div class=casa-linha>"
                "<span><b>%s</b><br><span class=fraco>%s</span></span>"
                "</div></div>"
                % (_esc(it.get("o_que", "")), _esc(it.get("quando", "")))
            )
        return "<div class=lista>" + "".join(linhas) + "</div>"
    except Exception:
        return "<div class=vazio>Não consegui ler as tarefas automáticas agora.</div>"


# ─────────────────────────── 5) os últimos erros ────────────────────────────

_ACHA_ERRO = re.compile(r"(?i)(traceback|\berros?\b|\berror\b|\bfailed\b|\bfailure\b|\bexception\b)")
_FALSO_ERRO = re.compile(r"(?i)(sem|nenhum|zero|0)\s+erros?|erros?\s*[:=]\s*0")


def _ultimas_linhas(caminho, max_bytes=120000, max_linhas=400):
    try:
        with open(caminho, "rb") as f:
            f.seek(0, os.SEEK_END)
            tam = f.tell()
            inicio = max(0, tam - max_bytes)
            f.seek(inicio)
            dados = f.read()
        txt = dados.decode("utf-8", "replace")
        if inicio and "\n" in txt:
            txt = txt.split("\n", 1)[1]
        return txt.splitlines()[-max_linhas:]
    except Exception:
        return []


def _ler_erros(dir_bin):
    """Devolve (lista, situação). Situação: 'ok' · 'sem-registro' (não há registro
    nenhum pra olhar) · 'parados' (existem, mas ninguém escreve neles) · 'falhou'
    (não consegui ler). Silêncio por falha NÃO pode parecer silêncio por saúde."""
    achados = []
    try:
        casa = os.path.expanduser("~")
        arquivos = set(glob.glob(os.path.join(dir_bin, "log", "*.log")))
        arquivos |= set(glob.glob(os.path.join(casa, "semente-*", "*.log")))
    except Exception:
        return [], "falhou"
    if not arquivos:
        return [], "sem-registro"
    try:
        limite_velho = datetime.datetime.now() - datetime.timedelta(days=DIAS_LOG)
        vivos = []
        for a in arquivos:
            try:
                mt = datetime.datetime.fromtimestamp(os.path.getmtime(a))
                if mt >= limite_velho:
                    vivos.append((mt, a))
            except Exception:
                continue
        if not vivos:
            return [], "parados"
        vivos.sort(reverse=True)
        for mt, caminho in vivos[:MAX_ARQUIVOS_LOG]:
            nome = os.path.basename(caminho)
            bonito = _TAREFAS.get(nome.replace(".log", ".sh"),
                                  _TAREFAS.get(nome.replace(".log", ".py"), ""))
            rotulo = bonito if bonito else nome.replace(".log", "").replace("-", " ")
            linhas = _ultimas_linhas(caminho)
            for i, ln in enumerate(linhas):
                t = ln.strip()
                if not t or len(t) > 1200:
                    continue
                if not _ACHA_ERRO.search(t) or _FALSO_ERRO.search(t):
                    continue
                quando = _achar_data(t) or mt
                achados.append({"quando": quando, "ordem": i, "onde": rotulo, "texto": t})
    except Exception:
        return [], "falhou"
    try:
        achados.sort(key=lambda x: (x["quando"], x["ordem"]), reverse=True)
    except Exception:
        pass
    unicos, vistos = [], set()
    for a in achados:                       # a mesma falha repetida 300 vezes vira uma linha
        chave = (a["onde"], a["texto"][:120])
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(a)
        if len(unicos) >= MAX_ERROS:
            break
    return unicos, "ok"


_RECADO_ERROS = {
    "falhou": "Não consegui ler os registros desta máquina agora — "
              "isto NÃO quer dizer que está tudo bem.",
    "sem-registro": "Ainda não há registro nenhum pra olhar nesta máquina.",
    "parados": "Os registros existem, mas ninguém escreve neles há mais de %d dias — "
               "pode ser que nada esteja rodando." % DIAS_LOG,
    "ok": "Nenhum aviso de erro nos registros recentes.",
}


def _html_erros(erros, situacao="ok"):
    try:
        if not erros:
            recado = _RECADO_ERROS.get(situacao, _RECADO_ERROS["falhou"])
            return "<div class=vazio>%s</div>" % _esc(recado)
        linhas = []
        for e in erros:
            texto = _encurta(e["texto"], 220)
            linhas.append(
                "<div class='item casa-bloco'>"
                "<div class=casa-linha><span class=fraco>%s</span>"
                "<span class=fraco>%s</span></div>"
                "<div class=casa-mono>%s</div></div>"
                % (_esc(e["onde"]), _esc(_quando(e["quando"])), _esc(texto))
            )
        return ("<div class=lista>" + "".join(linhas) + "</div>"
                "<p class=fraco>Se algo aqui te preocupar, copie a linha e me mande — "
                "eu explico e conserto.</p>")
    except Exception:
        return "<div class=vazio>Não consegui ler os registros agora.</div>"


# ─────────────────────────── o recado do topo ───────────────────────────────

def _html_banner(m, pecas, backup, erros, situacao="ok"):
    problemas = []
    try:
        if m.get("disco_pct") is not None and m["disco_pct"] >= 90:
            problemas.append(("erro", "o disco está quase cheio (%d%% usado)" % m["disco_pct"]))
        elif m.get("disco_pct") is not None and m["disco_pct"] >= 80:
            problemas.append(("atencao", "o disco está ficando cheio (%d%% usado)" % m["disco_pct"]))
        if m.get("mem_livre_mb") is not None and m["mem_livre_mb"] < 150:
            problemas.append(("erro", "a memória está no limite"))
        if m.get("carga") is not None and m["carga"] > (m.get("nucleos", 1) * 2):
            problemas.append(("atencao", "a máquina está sobrecarregada agora"))
        for p in pecas:
            if p.get("estado") == "erro":
                problemas.append(("erro", "%s está fora do ar" % p.get("nome", "uma peça")))
        if backup.get("estado") == "erro":
            problemas.append(("erro", "a cópia de segurança está com problema"))
        elif not backup.get("existe"):
            problemas.append(("atencao", "ainda não há cópia de segurança registrada"))
        if situacao == "falhou":
            problemas.append(("atencao", "não consegui ler os registros da máquina"))
        elif situacao == "parados":
            problemas.append(("atencao", "nada é escrito nos registros há mais de "
                                         "%d dias" % DIAS_LOG))
    except Exception:
        pass
    try:
        if not problemas:
            # só afirmo "nenhum erro" quando eu realmente consegui olhar
            extra = " Nenhum erro nos registros." if (situacao == "ok" and not erros) else ""
            return ("<div class='aviso ok'>Está tudo bem por aqui.%s</div>" % extra)
        grave = any(t == "erro" for t, _ in problemas)
        classe = "erro" if grave else "atencao"
        mostra = problemas[:4]
        texto = "; ".join(msg for _, msg in mostra)
        sobra = len(problemas) - len(mostra)
        if sobra > 0:
            texto += " e mais %d %s" % (sobra, _plural(sobra, "ponto", "pontos"))
        titulo = "Precisa de atenção:" if grave else "Fique de olho:"
        return "<div class='aviso %s'><b>%s</b> %s.</div>" % (classe, titulo, _esc(texto))
    except Exception:
        return ""


# ─────────────────────────── a montagem dos blocos ──────────────────────────

def _blocos(casca):
    """Devolve o HTML de cada pedaço da tela. Nenhum pedaço derruba o outro."""
    dir_bin = _casa_dir(casca, "DIR_BIN", "~/semente-bin")

    try:
        m = _medir_maquina()
    except Exception:
        m = {}
    try:
        pecas = _ler_pecas()
    except Exception:
        pecas = []
    try:
        backup = _ler_backup(dir_bin)
    except Exception:
        backup = {"existe": False, "estado": "atencao",
                  "texto": "Não consegui ler o registro de cópias agora."}
    try:
        cron, recado = _ler_despertadores()
    except Exception:
        cron, recado = [], "vazio"
    try:
        erros, situacao = _ler_erros(dir_bin)
    except Exception:
        erros, situacao = [], "falhou"

    return {
        "casa-banner": _html_banner(m, pecas, backup, erros, situacao),
        "casa-kpis": _html_kpis(m),
        "casa-pecas": _html_pecas(pecas),
        "casa-backup": _html_backup(backup),
        "casa-cron": _html_despertadores(cron, recado),
        "casa-erros": _html_erros(erros, situacao),
        "casa-momento": _agora_txt(),
    }


CSS = """
.casa-linha{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.casa-linha>span:first-child{min-width:0;flex:1;overflow-wrap:anywhere}
.lista .item>.casa-linha{flex:1 1 auto;min-width:0;width:100%}
.lista .item.casa-bloco{display:block}
.casa-topo{display:flex;gap:10px;align-items:baseline;justify-content:space-between;flex-wrap:wrap;margin-bottom:12px}
.casa-topo h2{margin:0}
.casa-mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;line-height:1.5;overflow-wrap:anywhere;word-break:break-word;margin-top:4px;color:var(--fraco)}
"""

JS = """
(function(){
  var ocupado = false;
  function pinta(dados){
    for (var chave in dados) {
      var alvo = document.getElementById(chave);
      if (alvo) { alvo.innerHTML = dados[chave]; }
    }
  }
  function atualiza(){
    if (ocupado) { return; }
    ocupado = true;
    var botao = document.getElementById('casa-btn');
    if (botao) { botao.disabled = true; botao.textContent = 'Atualizando…'; }
    fetch('/api/casa/dados', {headers: {'Accept': 'application/json'}})
      .then(function(r){
        if (r.status === 401) { location.reload(); return null; }
        if (!r.ok) { return null; }
        return r.json();
      })
      .then(function(d){ if (d) { pinta(d); } })
      .catch(function(){})
      .then(function(){
        ocupado = false;
        if (botao) { botao.disabled = false; botao.textContent = 'Atualizar'; }
      });
  }
  window.casaAtualiza = atualiza;
  setInterval(function(){ if (!document.hidden) { atualiza(); } }, 60000);
})();
"""


def _cartao(titulo, ident, corpo, explica=""):
    return ("<div class=cartao><h2>%s</h2>%s<div id=%s>%s</div></div>"
            % (_esc(titulo),
               ("<p class=fraco>%s</p>" % _esc(explica)) if explica else "",
               ident, corpo))


def _pagina(b):
    return (
        "<div class=casa-topo>"
        "<div><h2>A casa</h2>"
        "<span class=fraco id=casa-momento>" + _esc(b.get("casa-momento", "")) + "</span></div>"
        "<button class=btn id=casa-btn onclick='casaAtualiza()'>Atualizar</button>"
        "</div>"
        "<div id=casa-banner>" + b.get("casa-banner", "") + "</div>"
        + _cartao("Como a máquina está", "casa-kpis", b.get("casa-kpis", ""))
        + _cartao("As peças do assistente", "casa-pecas", b.get("casa-pecas", ""),
                  "Eu só olho — não ligo nem desligo nada por aqui.")
        + _cartao("Cópia de segurança", "casa-backup", b.get("casa-backup", ""))
        + _cartao("O que roda sozinho", "casa-cron", b.get("casa-cron", ""),
                  "Tarefas que a máquina dispara na hora certa, sem ninguém pedir.")
        + _cartao("Últimos avisos de erro", "casa-erros", b.get("casa-erros", ""),
                  "O que os registros da máquina marcaram como problema nos últimos "
                  "%d dias." % DIAS_LOG)
    )


# ─────────────────────────── o contrato da casca ────────────────────────────

def disponivel(cfg):
    """A saúde da casa vale pra toda instalação."""
    return True


def registra(app, casca, exige_login):

    @app.get("/casa")
    def tela_casa():
        exige_login()
        try:
            b = _blocos(casca)
            corpo = _pagina(b)
        except Exception:
            corpo = ("<div class=cartao><h2>A casa</h2>"
                     "<div class=vazio>Não consegui medir a máquina agora. "
                     "Atualize a página em alguns instantes.</div></div>")
        return Response(casca.shell("A casa", corpo, "/casa", css=CSS, js=JS),
                        mimetype="text/html")

    @app.get("/api/casa/dados")
    def api_casa_dados():
        exige_login()
        try:
            return jsonify(_blocos(casca))
        except Exception:
            return jsonify({
                "casa-banner": "<div class='aviso atencao'>Não consegui medir a máquina "
                               "agora. Tente de novo em alguns instantes.</div>",
            })
