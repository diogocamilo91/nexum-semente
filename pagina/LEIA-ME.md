# pagina/ — LEIA-ME (pra QUEM PUBLICA o presente, não pro instalador)

Esta pasta é a **página-guia** que leva o amigo do zero (alugar VPS) até colar o
prompt-semente. Ela NÃO é instalada na VPS de ninguém — é publicada (qualquer
hospedagem estática serve) e o link é enviado pro amigo.

## ✅ Checklist ANTES de publicar (obrigatório)

1. **Preencher `{URL_REPO_SEMENTE}`** — aparece em DOIS lugares e tem que ser a
   mesma URL nos dois:
   - `pagina/index.html` (dentro do bloco do prompt-semente, passo 8);
   - `prompt-semente.txt` (linha do `git clone`).

   | Slot | O que é | Exemplo |
   |---|---|---|
   | `{URL_REPO_SEMENTE}` | URL **https pública** deste repositório, clonável SEM login (o amigo recém-chegou, não tem chave SSH nem conta GitHub) | `https://github.com/usuario/nexum-semente.git` |

   Teste antes de mandar o link: `git clone {a-url-que-você-pôs} /tmp/teste-semente`
   numa máquina qualquer, sem credencial. Tem que funcionar.

2. **Validar o comando de instalação do Claude Code** (passo 5.2 do index.html —
   tem um comentário `VALIDAR` marcando o lugar): conferir em docs.claude.com se
   ainda é o comando vigente.

3. **Conferir que não sobrou placeholder**: `grep -n '{URL_REPO_SEMENTE}' pagina/index.html prompt-semente.txt`
   tem que voltar **vazio** na cópia publicada.

> O `grep` de slots do teste final da instalação NÃO cobre esta pasta (ela roda na
> VPS do amigo, onde a página já chegou pronta) — por isso este checklist existe.
