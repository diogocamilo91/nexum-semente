#!/usr/bin/env python3
"""
Semente — drive.py: o assistente acha, baixa e organiza arquivos no Google Drive.

REGRAS EMBUTIDAS (way of life): NÃO existe comando de apagar nem lixeira.
O máximo é MOVER de pasta (reversível). Compartilhar arquivo: nem existe aqui.

Python de biblioteca padrão (urllib), sem dependências. Credencial OAuth
compartilhada (~/.config/semente/google/oauth_client.json); o token deste módulo
(escopos Drive+Docs) é o mesmo do gdoc.py — uma autorização cobre os dois.

Uso:
  drive.py auth-url
  drive.py auth-finish "<URL colada do navegador, ou só o code>"
  drive.py listar <folderId|raiz>
  drive.py buscar "<trecho do nome>" [n]
  drive.py info <fileId>
  drive.py baixar <fileId> <destino>
  drive.py exportar <fileId> <destino> [txt|pdf|csv]   # Docs/Planilhas nativos do Google
  drive.py mkdir <parentId|raiz> "<nome>"
  drive.py mover <fileId> <novoParentId>
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
FILES_API  = "https://www.googleapis.com/drive/v3/files"

EXPORT_MIME = {"txt": "text/plain", "pdf": "application/pdf", "csv": "text/csv"}


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


# --- autorização (uma vez, vale também pro gdoc.py) ---------------------------

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
    print("OK - autorizado. Drive e Docs liberados (gdoc.py usa o mesmo token).")


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


def _api(tok, url, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
        headers={"Authorization": "Bearer " + tok,
                 "Content-Type": "application/json"},
        method=method or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit("ERRO API %s: %s" % (e.code, e.read().decode()[:800]))


def _id(arg):
    return "root" if arg in ("raiz", "root") else arg


# --- comandos ------------------------------------------------------------------

def _print_files(files):
    if not files:
        print("(vazio)")
        return
    for f in files:
        tipo = "📁" if f["mimeType"] == "application/vnd.google-apps.folder" else "  "
        tam = f.get("size", "")
        tam = " (%.1f MB)" % (int(tam) / 1e6) if tam else ""
        print("%s %s | %s%s | %s" % (tipo, f["id"], f["name"], tam,
                                     f.get("modifiedTime", "")[:16]))


def listar(folder_id):
    tok = _access_token()
    params = urllib.parse.urlencode({
        "q": "'%s' in parents and trashed = false" % _id(folder_id),
        "fields": "files(id,name,mimeType,size,modifiedTime)",
        "orderBy": "folder,modifiedTime desc", "pageSize": "200"})
    _print_files(_api(tok, FILES_API + "?" + params).get("files", []))


def buscar(trecho, n):
    tok = _access_token()
    params = urllib.parse.urlencode({
        "q": "name contains '%s' and trashed = false" % trecho.replace("'", "\\'"),
        "fields": "files(id,name,mimeType,size,modifiedTime)",
        "pageSize": str(n)})
    _print_files(_api(tok, FILES_API + "?" + params).get("files", []))


def info(file_id):
    tok = _access_token()
    f = _api(tok, "%s/%s?fields=id,name,mimeType,size,modifiedTime,parents,webViewLink"
             % (FILES_API, file_id))
    print(json.dumps(f, ensure_ascii=False, indent=1))


def _baixar_url(url, dest):
    tok = _access_token()
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
    try:
        with urllib.request.urlopen(req, timeout=600) as r, open(dest, "wb") as out:
            total = 0
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                total += len(chunk)
        print("OK - %s (%.1f MB)" % (dest, total / 1e6))
    except urllib.error.HTTPError as e:
        sys.exit("ERRO download %s: %s" % (e.code, e.read().decode()[:400]))


def baixar(file_id, dest):
    _baixar_url("%s/%s?alt=media" % (FILES_API, file_id), dest)


def exportar(file_id, dest, fmt):
    mime = EXPORT_MIME.get(fmt)
    if not mime:
        sys.exit("formato desconhecido: %s (use txt, pdf ou csv)" % fmt)
    _baixar_url("%s/%s/export?mimeType=%s"
                % (FILES_API, file_id, urllib.parse.quote(mime, safe="")), dest)


def mkdir(parent, nome):
    tok = _access_token()
    f = _api(tok, FILES_API, {
        "name": nome, "parents": [_id(parent)],
        "mimeType": "application/vnd.google-apps.folder"})
    print(f["id"])


def mover(file_id, novo_parent):
    tok = _access_token()
    f = _api(tok, "%s/%s?fields=parents" % (FILES_API, file_id))
    antigos = ",".join(f.get("parents", []))
    _api(tok, "%s/%s?addParents=%s&removeParents=%s"
         % (FILES_API, file_id, _id(novo_parent), antigos), {}, method="PATCH")
    print("OK - movido (reversível: estava em %s)." % (antigos or "?"))


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    cmd = a[0]
    if   cmd == "auth-url":    auth_url()
    elif cmd == "auth-finish": auth_finish(a[1])
    elif cmd == "listar":      listar(a[1])
    elif cmd == "buscar":      buscar(a[1], int(a[2]) if len(a) > 2 else 25)
    elif cmd == "info":        info(a[1])
    elif cmd == "baixar":      baixar(a[1], a[2])
    elif cmd == "exportar":    exportar(a[1], a[2], a[3] if len(a) > 3 else "txt")
    elif cmd == "mkdir":       mkdir(a[1], a[2])
    elif cmd == "mover":       mover(a[1], a[2])
    else:
        sys.exit("comando desconhecido: " + cmd)


if __name__ == "__main__":
    main()
