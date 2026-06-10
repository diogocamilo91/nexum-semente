# 📁 Módulo Drive/Docs — roteiro de instalação (PRO CLAUDE instalador)

Acesso ao Google Drive (achar, baixar, organizar — **sem apagar**) e aos Google Docs
(ler e escrever no documento, mantendo o mesmo arquivo/link). Duas ferramentas:
`drive.py` e `gdoc.py` (Python, biblioteca padrão, sem dependência). **Uma autorização
só cobre as duas** (token compartilhado do módulo).

**Antes de instalar:** entrevista feita (`ENTREVISTA.md`) e dono disse SIM.

**Slots usados:** `{EMAIL_DONO}`, `{NOME_ASSISTENTE}`.

**Chaves gravadas em `~/.config/semente/config.env`:**
```
DRIVE_DOCS_ATIVO=sim
#DOC_PENDENCIAS_ID=...          # id do Doc de pendências/anotações, se o dono quis (PARTE 4)
```

---

## PARTE 1 — credencial do Google

**Caso A — Gmail ou Agenda já instalados** (existe `~/.config/semente/google/oauth_client.json`):
só ativar mais duas APIs no MESMO projeto. Dono, logado em `{EMAIL_DONO}`,
em https://console.cloud.google.com/ (projeto `{NOME_ASSISTENTE}` selecionado no topo):
1. Menu ☰ → **APIs e serviços → Biblioteca** → buscar **"Google Drive API"** → **Ativar**.
2. Mesma Biblioteca → buscar **"Google Docs API"** → **Ativar**.
Vá pra PARTE 2.

**Caso B — primeiro módulo Google da casa:** siga o passo a passo completo de criação
de projeto + credencial em **`modulos/gmail/LEIA-ME.md`, PARTES 1 e 2** (criar projeto,
tela de permissão Externo + usuário de teste, **publicar "Em produção"**, credencial
**Desktop**, baixar o JSON, subir pra `~/.config/semente/google/oauth_client.json` com
chmod 600) — trocando o passo da API: ativar **"Google Drive API"** e **"Google Docs API"**.

## PARTE 2 — instalar as ferramentas e autorizar (uma vez pras duas)

```
[DENTRO DA VPS]
mkdir -p ~/semente-bin/log
cp <pasta-do-repo-clonado>/modulos/drive-docs/drive.py ~/semente-bin/drive.py
cp <pasta-do-repo-clonado>/modulos/drive-docs/gdoc.py  ~/semente-bin/gdoc.py
chmod +x ~/semente-bin/drive.py ~/semente-bin/gdoc.py
~/semente-bin/drive.py auth-url
```
Mande o link pro dono (logado em `{EMAIL_DONO}`): "app não verificado" → **Avançado →
Acessar {NOME_ASSISTENTE}** → **Permitir** (vai pedir Drive E Docs juntos) → o navegador
"falha" em `localhost:8767` (esperado) → ele copia a **URL inteira** da barra e cola.
O código expira em minutos:
```
[DENTRO DA VPS]
~/semente-bin/drive.py auth-finish "<URL colada>"
```
**Check:** `OK - autorizado.` — e o `gdoc.py` já funciona com o mesmo token
(`~/.config/semente/google/token_drive_docs.json`), sem segunda autorização.

## PARTE 3 — testar

```
[DENTRO DA VPS]
~/semente-bin/drive.py listar raiz                 # arquivos da raiz do Drive
~/semente-bin/drive.py buscar "<nome de um arquivo que o dono citou>"
```
**Check:** lista sem erro e o dono reconhece os arquivos.

Grave no config:
```
[DENTRO DA VPS]
printf '\nDRIVE_DOCS_ATIVO=sim\n' >> ~/.config/semente/config.env
```

## PARTE 4 (opcional) — Doc de Pendências/Anotações

Se o dono topou na entrevista:
1. Peça pra ELE criar um Google Doc novo (docs.google.com → documento em branco →
   nome tipo "Pendências") e mandar o link. O id é o trecho entre `/d/` e `/edit` da URL.
2. Teste de ponta a ponta (escreve e desfaz, doc volta intacto):
```
[DENTRO DA VPS]
~/semente-bin/gdoc.py ler <docId>
~/semente-bin/gdoc.py prepend <docId> "teste do {NOME_ASSISTENTE} — pode ignorar"
~/semente-bin/gdoc.py replace <docId> "teste do {NOME_ASSISTENTE} — pode ignorar" ""
```
3. **Check:** o dono viu a linha aparecer e sumir; o doc ficou como era.
4. Gravar: `printf 'DOC_PENDENCIAS_ID=<docId>\n' >> ~/.config/semente/config.env`
   e registrar no roteamento: "pendências/anotações" → este doc via `gdoc.py`.
   Combinar a regra de uso com o dono (ex.: item novo sempre no topo via `prepend`).

---

## As ferramentas (referência rápida)

`drive.py` — arquivos:
```
drive.py listar <folderId|raiz>            # conteúdo de uma pasta
drive.py buscar "<trecho do nome>" [n]     # procura no Drive inteiro
drive.py info <fileId>                     # nome, tipo, tamanho, pasta-mãe, link
drive.py baixar <fileId> <destino>         # baixa arquivo comum pro disco da VPS
drive.py exportar <fileId> <destino> [fmt] # Doc/Planilha do Google → txt|pdf|csv (padrão txt)
drive.py mkdir <parentId|raiz> "<nome>"    # cria subpasta (imprime o id)
drive.py mover <fileId> <novoParentId>     # move de pasta (reversível)
```
`gdoc.py` — dentro de um Google Doc:
```
gdoc.py ler     <docId>                    # texto do doc
gdoc.py append  <docId> "texto"            # linha no fim
gdoc.py prepend <docId> "texto"            # linha no começo
gdoc.py replace <docId> "antigo" "novo"    # troca texto ("novo" vazio = remove a frase)
```

**Não existe comando de apagar arquivo nem lixeira** — de propósito (way of life:
nunca apagar; mover, não deletar). O `replace` com vazio remove UMA frase combinada
dentro de um doc (uso de manutenção de lista); nunca usar pra esvaziar documento.

## Escopos, arquivos e privacidade

- Escopos: `drive` + `documents` (uma autorização só). O escopo `drive` permite mover/
  criar pasta; a proibição de apagar é da FERRAMENTA + da identidade do assistente.
- Credencial: `~/.config/semente/google/oauth_client.json` (compartilhada).
- Token: `~/.config/semente/google/token_drive_docs.json` (600).
- Nada disso entra no backup (fora de `~/nexum/`).
- Download de arquivo grande: vai DIRETO pro disco (não passa pela conversa). Cuidado
  com o espaço da VPS — confira com `df -h ~` antes de baixar coisa de GB.

## Se falhar

| Sintoma | Causa | Conserto |
|---|---|---|
| `403 accessNotConfigured` | Drive ou Docs API não ativada | PARTE 1 |
| `invalid_grant` no auth-finish | código expirou/cortado | `auth-url` de novo |
| Parou após ~7 dias | app OAuth "Em teste" | publicar "Em produção" + refazer auth |
| `404` num fileId/docId | id errado ou sem acesso | conferir o link com o dono |
| `baixar` falha em Doc do Google | Doc nativo não tem download direto | usar `exportar` |
| Token antigo sem o escopo novo | autorizou antes de ativar uma API | refazer auth-url/auth-finish |

Depois de instalado: registrar no `INDEX.md` e no roteamento (assunto "arquivos/Drive/
documentos" → este módulo).
