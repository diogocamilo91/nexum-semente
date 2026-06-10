# base/backup/ — LEIA-ME (instruções pra VOCÊ, Claude instalador)

Você vai instalar a rede de segurança: uma cópia do `~/nexum/` que sobe **sozinha, de hora em hora**, pra um repositório **privado** no GitHub **do dono** (não do criador do kit). A VPS continua sendo a fonte única da verdade; o GitHub é só histórico + recuperação.

Pré-requisitos: `base/cerebro/` instalado (existe `~/nexum/`) e `base/lib/alerta.sh` instalado e testado.

## O que tem aqui

| Arquivo | Vira o quê |
|---|---|
| `backup.sh` | `~/semente-bin/backup.sh` — commit + push de hora em hora, com trava >95MB e alerta de falha |

## Slots usados (neste LEIA-ME)

| Slot | O que é | De onde vem |
|---|---|---|
| `{USUARIO_GITHUB}` | usuário do GitHub do dono | entrevista (passo 1) |
| `{REPO_GITHUB_BACKUP}` | nome do repo privado de backup (sugira `nexum-backup`) | entrevista (passo 1) |
| `{NOME_ASSISTENTE}` | nome do assistente | já está no config.env |

## Passo a passo

### 1. Entrevista (curta)

Explique pra pessoa, em 2-3 frases: *"Vou criar uma cópia de segurança automática de tudo que organizamos, num cofre privado seu no GitHub (um site gratuito de guardar arquivos com histórico). Só você — e eu daqui — acessa. Se a VPS um dia se perder, nada se perde."*

Pergunte:
1. Ela já tem conta no GitHub? **Se não**, guie a criação em github.com (gratuita) → anote `{USUARIO_GITHUB}`.
2. Confirme o nome do repo: sugira **`nexum-backup`** → `{REPO_GITHUB_BACKUP}`.

### 2. A pessoa cria o repositório privado (ela faz, você dita)

Dite pra ela, no navegador:
1. github.com → botão **New repository**.
2. Nome: `{REPO_GITHUB_BACKUP}`. Visibilidade: **Private** (importante — explique: "privado = só você vê").
3. NÃO marcar "Add a README" (o repo precisa nascer vazio).
4. **Create repository**.

### 3. Chave de deploy (a VPS ganha acesso de escrita SÓ nesse repo)

Gere a chave na VPS (sem passphrase — é de robô):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/backup_github -N "" -C "backup-semente"
cat ~/.ssh/backup_github.pub
```

Mostre a chave pública pra pessoa e dite: no repo do GitHub → **Settings → Deploy keys → Add deploy key** → título `vps-backup`, colar a chave, **marcar "Allow write access"** → Add key.

Aponte o SSH do git pra essa chave (só pro github.com):

```bash
touch ~/.ssh/config && chmod 600 ~/.ssh/config
grep -q "Host github.com" ~/.ssh/config 2>/dev/null || cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/backup_github
  IdentitiesOnly yes
EOF
```

### 4. Ligar o repo local ao GitHub

```bash
cd ~/nexum
git init -b main 2>/dev/null || true
git config user.name "{NOME_ASSISTENTE} (VPS)"
git config user.email "assistente@vps.local"
git remote add origin git@github.com:{USUARIO_GITHUB}/{REPO_GITHUB_BACKUP}.git 2>/dev/null \
  || git remote set-url origin git@github.com:{USUARIO_GITHUB}/{REPO_GITHUB_BACKUP}.git
```

Crie o `.gitignore` se ainda não existir (lixo temporário fora do backup):

```bash
[ -f ~/nexum/.gitignore ] || printf '%s\n' '*.tmp' '*.log' '.DS_Store' > ~/nexum/.gitignore
```

> **Regra de ouro de privacidade:** segredos (tokens, senhas) moram em `~/.config/semente/` — **fora** do `~/nexum/`, logo fora do backup, de propósito. Nunca copie credencial pra dentro de `~/nexum/`.

Grave no config central:

```bash
grep -q REPO_GITHUB_BACKUP ~/.config/semente/config.env || \
  echo 'REPO_GITHUB_BACKUP="{USUARIO_GITHUB}/{REPO_GITHUB_BACKUP}"' >> ~/.config/semente/config.env
```

(Se o `base/cerebro/` deixou "(backup ainda não configurado)" em algum template, volte lá e preencha agora.)

### 5. Instalar o script + primeiro envio

```bash
cp <pasta-do-repo-clonado>/base/backup/backup.sh ~/semente-bin/backup.sh
chmod +x ~/semente-bin/backup.sh
bash ~/semente-bin/backup.sh
tail -n 3 ~/semente-bin/log/backup.log
```

**Check:** a última linha do log deve ser `backup enviado OK`. Confirme também pelo GitHub: peça pra pessoa recarregar a página do repo e ver os arquivos lá.

**Se falhar:**
- `Permission denied (publickey)` → a deploy key não foi adicionada, ou sem "Allow write access", ou o `~/.ssh/config` não apontou. Teste: `ssh -T git@github.com` (deve responder com o nome do repo ou "successfully authenticated").
- `Host key verification failed` → rode `ssh-keyscan github.com >> ~/.ssh/known_hosts` e tente de novo.
- `remote: Repository not found` → nome do repo/usuário errados no `git remote -v`, ou o repo não foi criado.

### 6. Cron de hora em hora

```bash
( crontab -l 2>/dev/null | grep -v semente-bin/backup.sh ; echo '0 * * * * /usr/bin/bash $HOME/semente-bin/backup.sh' ) | crontab -
crontab -l | grep backup
```

### 7. Teste de ponta a ponta (obrigatório)

```bash
echo "teste $(date)" > ~/nexum/_entrada/teste-backup.md
bash ~/semente-bin/backup.sh
git -C ~/nexum log --oneline -1
rm ~/nexum/_entrada/teste-backup.md   # único delete permitido: o próprio arquivo de teste que você criou
bash ~/semente-bin/backup.sh
```

Os dois commits devem aparecer no GitHub.

## O que dizer pra pessoa no final

*"Pronto: de hora em hora, tudo que mudou sobe sozinho pro seu cofre no GitHub. Se um dia o envio falhar ou aparecer um arquivo grande demais, eu te aviso no Telegram — backup parado nunca fica em silêncio."*
