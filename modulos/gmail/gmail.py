#!/usr/bin/env python3
"""
Semente — gmail.py: o assistente lê, organiza e escreve no Gmail do dono.

Python de biblioteca padrão (urllib), sem dependências. Credencial OAuth criada
pelo dono no Google Cloud (ver LEIA-ME.md do módulo). Configuração em
~/.config/semente/config.env; nada fixo no código.

REGRAS EMBUTIDAS (way of life):
- NÃO existe comando de apagar/lixeira. Nunca. O máximo é arquivar/marcar lido.
- `enviar`/`responder` só devem ser chamados COM OK EXPLÍCITO do dono (regra de
  identidade do assistente; a ferramenta confia em quem chama).

Uso:
  gmail.py auth-url
  gmail.py auth-finish "<URL colada do navegador, ou só o code>"
  gmail.py nao-lidos [n]
  gmail.py buscar "<busca do gmail>" [n]
  gmail.py ler <id>
  gmail.py enviar   --para a@b [--cc c@d] --assunto "X" --corpo "..." [--anexo arq]
  gmail.py responder <id> --corpo "..."
  gmail.py rascunho --para a@b --assunto "X" --corpo "..."
  gmail.py arquivar <id>
  gmail.py marcar-lido <id>
  gmail.py rotular <id> "Nome do rótulo"
  gmail.py limpa-propaganda [--max N]      # marca Promoções como lidas (não apaga)

Corpo por stdin: --corpo -   (lê a entrada padrão)
"""
import sys, os, json, base64, argparse, mimetypes
import urllib.parse, urllib.request, urllib.error
from email.message import EmailMessage

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
TOKEN_FILE = os.path.expanduser("~/.config/semente/google/token_gmail.json")
SCOPE      = "https://www.googleapis.com/auth/gmail.modify"
REDIRECT   = "http://localhost:8765"
AUTH_URI   = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI  = "https://oauth2.googleapis.com/token"
API        = "https://gmail.googleapis.com/gmail/v1/users/me"


def _client():
    if not os.path.exists(KEYS_FILE):
        sys.exit("Credencial não encontrada: %s\n(ver PARTE 1-2 do LEIA-ME do módulo Gmail)" % KEYS_FILE)
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
    print("OK - autorizado. Já posso trabalhar no Gmail.")


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


# --- chamadas à API ----------------------------------------------------------

def _api(tok, path, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data,
        headers={"Authorization": "Bearer " + tok,
                 "Content-Type": "application/json"},
        method=method or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        sys.exit("ERRO API %s em %s: %s" % (e.code, path, e.read().decode()[:800]))


def _header(msg, name):
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


# --- ler / buscar ------------------------------------------------------------

def buscar(query, n):
    tok = _api_tok()
    res = _api(tok, "/messages?" + urllib.parse.urlencode(
        {"q": query, "maxResults": str(n)}))
    ids = [m["id"] for m in res.get("messages", [])]
    if not ids:
        print("(nenhum e-mail pra essa busca)")
        return
    for i in ids:
        m = _api(tok, "/messages/%s?format=metadata&metadataHeaders=From"
                      "&metadataHeaders=Subject&metadataHeaders=Date" % i)
        flag = "●" if "UNREAD" in m.get("labelIds", []) else " "
        print("%s %s | %s | %s | %s" % (
            flag, i, _header(m, "Date")[:22],
            _header(m, "From")[:48], _header(m, "Subject")[:80]))


def _api_tok():
    return _access_token()


def _texto_do_payload(payload):
    """Acha a melhor parte de texto (text/plain > text/html cru)."""
    mime = payload.get("mimeType", "")
    body = payload.get("body", {})
    if mime.startswith("text/") and body.get("data"):
        txt = base64.urlsafe_b64decode(body["data"] + "==").decode("utf-8", "replace")
        return txt, mime
    melhor = None
    for parte in payload.get("parts", []) or []:
        txt, m = _texto_do_payload(parte)
        if txt and m == "text/plain":
            return txt, m
        if txt and melhor is None:
            melhor = (txt, m)
    return melhor or ("", "")


def ler(msg_id):
    tok = _api_tok()
    m = _api(tok, "/messages/%s?format=full" % msg_id)
    for h in ("Date", "From", "To", "Cc", "Subject"):
        v = _header(m, h)
        if v:
            print("%s: %s" % (h, v))
    anexos = [p.get("filename") for p in m.get("payload", {}).get("parts", []) or []
              if p.get("filename")]
    if anexos:
        print("Anexos: " + ", ".join(anexos))
    txt, mime = _texto_do_payload(m.get("payload", {}))
    print("-" * 60)
    if mime == "text/html":
        print("(corpo só em HTML — texto cru abaixo)")
    print(txt.strip() or "(sem corpo de texto)")


# --- escrever ----------------------------------------------------------------

def _corpo(arg):
    if arg == "-" or arg is None:
        return sys.stdin.read()
    return arg


def _montar(para, assunto, corpo, cc=None, anexo=None, extra_headers=None):
    msg = EmailMessage()
    msg["To"] = para
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = assunto
    for k, v in (extra_headers or {}).items():
        msg[k] = v
    msg.set_content(corpo)
    if anexo:
        ctype, _ = mimetypes.guess_type(anexo)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        with open(anexo, "rb") as f:
            msg.add_attachment(f.read(), maintype=maintype, subtype=subtype,
                               filename=os.path.basename(anexo))
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def enviar(a):
    tok = _api_tok()
    raw = _montar(a.para, a.assunto, _corpo(a.corpo), a.cc, a.anexo)
    res = _api(tok, "/messages/send", {"raw": raw})
    print("Enviado. id=%s" % res.get("id"))


def rascunho(a):
    tok = _api_tok()
    raw = _montar(a.para, a.assunto, _corpo(a.corpo), a.cc, a.anexo)
    res = _api(tok, "/drafts", {"message": {"raw": raw}})
    print("Rascunho criado (pasta Rascunhos do Gmail). id=%s" % res.get("id"))


def responder(a):
    tok = _api_tok()
    orig = _api(tok, "/messages/%s?format=metadata&metadataHeaders=Subject"
                     "&metadataHeaders=From&metadataHeaders=Reply-To"
                     "&metadataHeaders=Message-ID" % a.id)
    para = _header(orig, "Reply-To") or _header(orig, "From")
    assunto = _header(orig, "Subject")
    if not assunto.lower().startswith("re:"):
        assunto = "Re: " + assunto
    mid = _header(orig, "Message-ID")
    extra = {"In-Reply-To": mid, "References": mid} if mid else {}
    raw = _montar(para, assunto, _corpo(a.corpo), extra_headers=extra)
    res = _api(tok, "/messages/send",
               {"raw": raw, "threadId": orig.get("threadId")})
    print("Respondido na mesma conversa. id=%s" % res.get("id"))


# --- organizar (nunca apagar) -------------------------------------------------

def _modify(msg_id, add=None, remove=None):
    tok = _api_tok()
    _api(tok, "/messages/%s/modify" % msg_id,
         {"addLabelIds": add or [], "removeLabelIds": remove or []})


def rotular(msg_id, nome):
    tok = _api_tok()
    labels = _api(tok, "/labels").get("labels", [])
    lid = next((l["id"] for l in labels
                if l["name"].lower() == nome.lower()), None)
    if not lid:
        lid = _api(tok, "/labels", {"name": nome})["id"]
        print("(rótulo '%s' criado)" % nome)
    _api(tok, "/messages/%s/modify" % msg_id, {"addLabelIds": [lid]})
    print("OK - rotulado com '%s'." % nome)


def limpa_propaganda(maximo):
    """Marca como LIDA a aba Promoções. Não apaga, não arquiva, não move."""
    tok = _api_tok()
    total = 0
    while total < maximo:
        lote = min(500, maximo - total)
        res = _api(tok, "/messages?" + urllib.parse.urlencode(
            {"q": "category:promotions is:unread", "maxResults": str(lote)}))
        ids = [m["id"] for m in res.get("messages", [])]
        if not ids:
            break
        _api(tok, "/messages/batchModify",
             {"ids": ids, "removeLabelIds": ["UNREAD"]})
        total += len(ids)
        if len(ids) < lote:
            break
    print("limpa-propaganda: %d marcada(s) como lida(s). Nada foi apagado." % total)


# --- linha de comando ---------------------------------------------------------

def main():
    p = argparse.ArgumentParser(add_help=False)
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("auth-url")
    s = sub.add_parser("auth-finish"); s.add_argument("url")
    s = sub.add_parser("nao-lidos");  s.add_argument("n", nargs="?", type=int, default=10)
    s = sub.add_parser("buscar");     s.add_argument("query"); s.add_argument("n", nargs="?", type=int, default=10)
    s = sub.add_parser("ler");        s.add_argument("id")
    for nome in ("enviar", "rascunho"):
        s = sub.add_parser(nome)
        s.add_argument("--para", required=True); s.add_argument("--cc")
        s.add_argument("--assunto", required=True)
        s.add_argument("--corpo", default="-"); s.add_argument("--anexo")
    s = sub.add_parser("responder");  s.add_argument("id"); s.add_argument("--corpo", default="-")
    s = sub.add_parser("arquivar");   s.add_argument("id")
    s = sub.add_parser("marcar-lido"); s.add_argument("id")
    s = sub.add_parser("rotular");    s.add_argument("id"); s.add_argument("nome")
    s = sub.add_parser("limpa-propaganda"); s.add_argument("--max", type=int, default=200)
    a = p.parse_args()

    if   a.cmd == "auth-url":     auth_url()
    elif a.cmd == "auth-finish":  auth_finish(a.url)
    elif a.cmd == "nao-lidos":    buscar("is:unread in:inbox", a.n)
    elif a.cmd == "buscar":       buscar(a.query, a.n)
    elif a.cmd == "ler":          ler(a.id)
    elif a.cmd == "enviar":       enviar(a)
    elif a.cmd == "rascunho":     rascunho(a)
    elif a.cmd == "responder":    responder(a)
    elif a.cmd == "arquivar":     _modify(a.id, remove=["INBOX"]) or print("OK - arquivado (continua na conta, fora da caixa de entrada).")
    elif a.cmd == "marcar-lido":  _modify(a.id, remove=["UNREAD"]) or print("OK - marcado como lido.")
    elif a.cmd == "rotular":      rotular(a.id, a.nome)
    elif a.cmd == "limpa-propaganda": limpa_propaganda(a.max)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
