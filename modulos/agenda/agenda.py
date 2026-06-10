#!/usr/bin/env python3
"""
Semente — agenda.py: o assistente LÊ a agenda do dono (Google Calendar).

SÓ-LEITURA POR DESENHO: escopo calendar.readonly — não existe (e não há como
existir com este token) criar/editar/apagar evento.

Python de biblioteca padrão (urllib), sem dependências. Credencial OAuth
compartilhada dos módulos Google (~/.config/semente/google/oauth_client.json).
Configuração em ~/.config/semente/config.env:
  AGENDA_CALENDARIOS=primary[,Nome=id,...]   # quais agendas olhar
  FUSO_HORARIO=America/Sao_Paulo             # opcional

Uso:
  agenda.py auth-url
  agenda.py auth-finish "<URL colada do navegador, ou só o code>"
  agenda.py agendas              # lista as agendas da conta
  agenda.py hoje | amanha | fds
  agenda.py dia 2026-12-25
  agenda.py proximos [N]         # próximos N dias (padrão 7)
"""
import sys, os, json, datetime, urllib.parse, urllib.request, urllib.error
from zoneinfo import ZoneInfo

# --- configuração (um lugar só) ----------------------------------------------

def _cfg():
    path = os.environ.get("SEMENTE_CONFIG",
                          os.path.expanduser("~/.config/semente/config.env"))
    cfg = {}
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = os.path.expanduser(v.strip().strip('"').strip("'"))
    return cfg

CFG        = _cfg()
KEYS_FILE  = CFG.get("GOOGLE_OAUTH_CLIENT",
                     os.path.expanduser("~/.config/semente/google/oauth_client.json"))
TOKEN_FILE = os.path.expanduser("~/.config/semente/google/token_agenda.json")
SCOPE      = "https://www.googleapis.com/auth/calendar.readonly"
REDIRECT   = "http://localhost:8766"
AUTH_URI   = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI  = "https://oauth2.googleapis.com/token"
CAL_API    = "https://www.googleapis.com/calendar/v3"
TZ         = ZoneInfo(CFG.get("FUSO_HORARIO", "America/Sao_Paulo"))

DIAS_SEM = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _calendarios():
    """Lê AGENDA_CALENDARIOS do config: 'primary,Nome=id,...' → [(label, id)]."""
    bruto = CFG.get("AGENDA_CALENDARIOS", "primary")
    out = []
    for item in bruto.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            label, cid = item.split("=", 1)
            out.append((label.strip(), cid.strip()))
        else:
            out.append(("", item))
    return out or [("", "primary")]


def _client():
    if not os.path.exists(KEYS_FILE):
        sys.exit("Credencial não encontrada: %s\n(ver PARTE 1 do LEIA-ME do módulo Agenda)" % KEYS_FILE)
    with open(KEYS_FILE) as f:
        data = json.load(f)
    c = data.get("installed") or data.get("web")
    return c["client_id"], c["client_secret"]


def _post_form(url, fields):
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit("ERRO OAuth %s: %s" % (e.code, e.read().decode()[:600]))


# --- autorização (uma vez) ---------------------------------------------------

def auth_url():
    cid, _ = _client()
    q = urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": REDIRECT, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent"})
    print(AUTH_URI + "?" + q)


def auth_finish(arg):
    code = arg.strip()
    if "code=" in code:
        qs = urllib.parse.urlparse(code).query or code.split("?", 1)[-1]
        code = urllib.parse.parse_qs(qs).get("code", [""])[0]
    if not code:
        sys.exit("Não achei o 'code' no que você colou.")
    cid, sec = _client()
    tok = _post_form(TOKEN_URI, {
        "code": code, "client_id": cid, "client_secret": sec,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code"})
    rt = tok.get("refresh_token")
    if not rt:
        sys.exit("Google não devolveu refresh_token. Resposta: " + json.dumps(tok)[:300])
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump({"refresh_token": rt}, f)
    os.chmod(TOKEN_FILE, 0o600)
    print("OK - autorizado. Já posso ler a agenda (só leitura).")


def _access_token():
    if not os.path.exists(TOKEN_FILE):
        sys.exit("Sem autorização ainda. Rode 'auth-url' e 'auth-finish' primeiro.")
    with open(TOKEN_FILE) as f:
        rt = json.load(f)["refresh_token"]
    cid, sec = _client()
    tok = _post_form(TOKEN_URI, {
        "refresh_token": rt, "client_id": cid, "client_secret": sec,
        "grant_type": "refresh_token"})
    return tok["access_token"]


# --- leitura -----------------------------------------------------------------

def agendas():
    tok = _access_token()
    req = urllib.request.Request(
        CAL_API + "/users/me/calendarList",
        headers={"Authorization": "Bearer " + tok})
    with urllib.request.urlopen(req, timeout=60) as r:
        items = json.load(r).get("items", [])
    for c in items:
        marca = " (principal)" if c.get("primary") else ""
        print("%s | %s%s" % (c["id"], c.get("summary", ""), marca))


def _events(tok, cal_id, dia):
    ini = datetime.datetime.combine(dia, datetime.time(0, 0), TZ)
    fim = ini + datetime.timedelta(days=1)
    params = urllib.parse.urlencode({
        "timeMin": ini.isoformat(), "timeMax": fim.isoformat(),
        "singleEvents": "true", "orderBy": "startTime",
        "timeZone": str(TZ), "maxResults": "50"})
    url = "%s/calendars/%s/events?%s" % (
        CAL_API, urllib.parse.quote(cal_id, safe=""), params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r).get("items", [])
    except urllib.error.HTTPError:
        return []          # uma agenda com problema não derruba o resto


def _fmt(ev, label):
    titulo = (ev.get("summary") or "(sem título)").strip()
    start = ev.get("start", {})
    if "date" in start:
        hora = "dia todo"
    else:
        dt = datetime.datetime.fromisoformat(start["dateTime"]).astimezone(TZ)
        endt = ev.get("end", {}).get("dateTime")
        fim = datetime.datetime.fromisoformat(endt).astimezone(TZ) if endt else None
        hora = dt.strftime("%H:%M") + (("–" + fim.strftime("%H:%M")) if fim else "")
    extra = []
    if label:
        extra.append("[" + label + "]")
    local = (ev.get("location") or "").strip()
    if local:
        extra.append("@ " + local)
    return "%s  %s%s" % (hora, titulo, ("  " + " ".join(extra)) if extra else "")


def mostrar(dias):
    tok = _access_token()
    blocos = []
    for d in dias:
        cab = "%s %s" % (DIAS_SEM[d.weekday()].capitalize(), d.strftime("%d/%m"))
        linhas = []
        for label, cid in _calendarios():
            linhas += [s for s in (_fmt(ev, label) for ev in _events(tok, cid, d)) if s]
        blocos.append(cab + "\n" + ("\n".join("  " + l for l in linhas)
                                    if linhas else "  (sem compromissos)"))
    print("\n\n".join(blocos))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    hoje = datetime.datetime.now(TZ).date()
    um = datetime.timedelta(days=1)
    if   cmd == "auth-url":    auth_url()
    elif cmd == "auth-finish": auth_finish(sys.argv[2])
    elif cmd == "agendas":     agendas()
    elif cmd == "hoje":        mostrar([hoje])
    elif cmd == "amanha":      mostrar([hoje + um])
    elif cmd == "fds":
        sab = hoje + datetime.timedelta(days=(5 - hoje.weekday()) % 7)
        mostrar([sab, sab + um])
    elif cmd == "dia":         mostrar([datetime.date.fromisoformat(sys.argv[2])])
    elif cmd == "proximos":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        mostrar([hoje + datetime.timedelta(days=i) for i in range(1, n + 1)])
    else:
        sys.exit("comando desconhecido: " + cmd)


if __name__ == "__main__":
    main()
