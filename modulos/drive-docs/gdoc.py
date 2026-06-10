#!/usr/bin/env python3
"""
Semente — gdoc.py: o assistente lê e escreve DENTRO de um Google Doc do dono
(mesmo arquivo, mesmo link — ex.: um doc de Pendências/Anotações mantido a dois).

REGRAS EMBUTIDAS (way of life): não existe apagar documento. O `replace` com
"novo" vazio remove UMA frase combinada (manutenção de lista) — nunca usar pra
esvaziar um doc.

Python de biblioteca padrão (urllib), sem dependências. Usa o MESMO token do
drive.py (~/.config/semente/google/token_drive_docs.json) — uma autorização
cobre os dois; os comandos auth-* existem aqui só por conveniência.

Uso:
  gdoc.py auth-url
  gdoc.py auth-finish "<URL colada do navegador, ou só o code>"
  gdoc.py ler     <docId>
  gdoc.py append  <docId> "texto"            # linha no fim
  gdoc.py prepend <docId> "texto"            # linha no começo
  gdoc.py replace <docId> "antigo" "novo"    # troca texto (novo vazio = remove)

O docId é o trecho entre /d/ e /edit no link do documento.
"""
import sys, os, json, urllib.parse, urllib.request, urllib.error

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
TOKEN_FILE = os.path.expanduser("~/.config/semente/google/token_drive_docs.json")
SCOPE      = ("https://www.googleapis.com/auth/drive "
              "https://www.googleapis.com/auth/documents")
REDIRECT   = "http://localhost:8767"
AUTH_URI   = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI  = "https://oauth2.googleapis.com/token"
DOCS_API   = "https://docs.googleapis.com/v1/documents/"


def _client():
    if not os.path.exists(KEYS_FILE):
        sys.exit("Credencial não encontrada: %s\n(ver PARTE 1 do LEIA-ME do módulo Drive/Docs)" % KEYS_FILE)
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
    print("OK - autorizado. Docs e Drive liberados (drive.py usa o mesmo token).")


def _access_token():
    if not os.path.exists(TOKEN_FILE):
        sys.exit("Sem autorização ainda. Rode 'auth-url' e 'auth-finish' primeiro "
                 "(aqui ou no drive.py — o token é o mesmo).")
    with open(TOKEN_FILE) as f:
        rt = json.load(f)["refresh_token"]
    cid, sec = _client()
    tok = _post_form(TOKEN_URI, {
        "refresh_token": rt, "client_id": cid, "client_secret": sec,
        "grant_type": "refresh_token"})
    return tok["access_token"]


# --- Docs API ------------------------------------------------------------------

def _get_doc(doc_id):
    tok = _access_token()
    req = urllib.request.Request(DOCS_API + doc_id,
        headers={"Authorization": "Bearer " + tok})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit("ERRO API %s: %s" % (e.code, e.read().decode()[:600]))


def _batch(doc_id, requests):
    tok = _access_token()
    req = urllib.request.Request(
        DOCS_API + doc_id + ":batchUpdate",
        data=json.dumps({"requests": requests}).encode(),
        headers={"Authorization": "Bearer " + tok,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit("ERRO API %s: %s" % (e.code, e.read().decode()[:600]))


def ler(doc_id):
    doc = _get_doc(doc_id)
    print("# " + doc.get("title", "(sem título)"))
    for el in doc.get("body", {}).get("content", []):
        par = el.get("paragraph")
        if not par:
            continue
        linha = "".join(r.get("textRun", {}).get("content", "")
                        for r in par.get("elements", []))
        sys.stdout.write(linha)


def append(doc_id, texto):
    _batch(doc_id, [{"insertText": {
        "endOfSegmentLocation": {}, "text": "\n" + texto}}])
    print("OK - linha acrescentada no fim.")


def prepend(doc_id, texto):
    _batch(doc_id, [{"insertText": {
        "location": {"index": 1}, "text": texto + "\n"}}])
    print("OK - linha acrescentada no começo.")


def replace(doc_id, antigo, novo):
    res = _batch(doc_id, [{"replaceAllText": {
        "containsText": {"text": antigo, "matchCase": True},
        "replaceText": novo}}])
    n = (res.get("replies", [{}])[0]
            .get("replaceAllText", {}).get("occurrencesChanged", 0))
    print("OK - %d ocorrência(s) %s." % (n, "removida(s)" if novo == "" else "trocada(s)"))
    if n == 0:
        print("(nada mudou — confira o texto exato com 'gdoc.py ler')")


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    cmd = a[0]
    if   cmd == "auth-url":    auth_url()
    elif cmd == "auth-finish": auth_finish(a[1])
    elif cmd == "ler":         ler(a[1])
    elif cmd == "append":      append(a[1], a[2])
    elif cmd == "prepend":     prepend(a[1], a[2])
    elif cmd == "replace":     replace(a[1], a[2], a[3] if len(a) > 3 else "")
    else:
        sys.exit("comando desconhecido: " + cmd)


if __name__ == "__main__":
    main()
