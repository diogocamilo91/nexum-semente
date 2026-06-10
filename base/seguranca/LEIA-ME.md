# base/seguranca/ — LEIA-ME (instruções pra VOCÊ, Claude instalador)

Você vai blindar a VPS da pessoa: firewall só com SSH+80+443, SSH numa porta alta (fora da 22 que os robôs do mundo inteiro varrem), login por senha desligado (inclusive o de root) assim que houver chave instalada e comprovada, fail2ban e atualizações automáticas.

⚠️ **ESTE é o módulo onde dá pra trancar a pessoa pra fora da própria VPS. Por isso o script trabalha em DUAS FASES e você NUNCA pula o teste do meio.** A regra: nada se fecha antes de provar que o caminho novo funciona.

Pré-requisito: `base/cerebro/` instalado (existe o config.env). Instale este módulo **cedo** (logo após bot+lib), antes de acumular serviços.

## O que tem aqui

| Arquivo | Vira o quê |
|---|---|
| `blindar.sh` | `~/semente-bin/blindar.sh` — a blindagem em 2 fases |
| `checklist.md` | `~/nexum/_nexum/seguranca-checklist.md` — verificação periódica |

## Slots usados

| Slot | O que é | De onde vem |
|---|---|---|
| `{PORTA_SSH}` | porta alta nova do SSH (20000-65535) | você sorteia na entrevista (ex.: `38222`) |
| `{IP_VPS}` | IP público da VPS | `curl -s ifconfig.me` (a pessoa já usou pra entrar) |

## Passo a passo

### 1. Explicar pra pessoa (antes de mexer)

Diga algo como: *"Vou trancar as portas da sua VPS: só vai entrar quem bater na porta certa (uma porta secreta de SSH que vamos escolher) — o resto fica fechado. Também ligo um vigia que bane quem fica tentando senha. Faço em duas etapas e você testa no meio: em nenhum momento você corre o risco de ficar trancado(a) fora."*

### 2. Escolher a porta e gravar no config

Sorteie uma porta entre 20000 e 60000 (ex.: `shuf -i 20000-60000 -n 1`) → `{PORTA_SSH}`. Grave:

```bash
grep -q "^PORTA_SSH=" ~/.config/semente/config.env || \
  echo 'PORTA_SSH="{PORTA_SSH}"' >> ~/.config/semente/config.env
```

**Anote pra pessoa em lugar seguro** (ela vai precisar pra sempre): IP da VPS + porta. A partir da fase2, conectar é `ssh -p {PORTA_SSH} usuario@{IP_VPS}`.

### 3. Instalar e rodar a FASE 1 (não fecha nada)

```bash
cp <pasta-do-repo-clonado>/base/seguranca/blindar.sh ~/semente-bin/blindar.sh
chmod +x ~/semente-bin/blindar.sh
sudo bash ~/semente-bin/blindar.sh fase1
```

A fase1: instala ufw/fail2ban/unattended-upgrades, abre a porta nova **mantendo a atual**, e liga o firewall já com as duas + 80 + 443. Se qualquer checagem falhar, ela aborta sem fechar nada.

**Check:** a saída termina com "FASE 1 OK". `bash ~/semente-bin/blindar.sh status` mostra as duas portas ativas.

### 4. O TESTE DO MEIO (obrigatório — não pule)

Peça pra pessoa, **sem fechar a janela atual**, abrir um terminal NOVO no computador dela e conectar pela porta nova:

```
ssh -p {PORTA_SSH} usuario@{IP_VPS}
```

- **Entrou?** → siga pro passo 5, **rodando a fase2 a partir dessa conexão nova** (o script confere isso sozinho e se recusa se não for).
- **Não entrou?** → nada se perdeu (a porta antiga segue aberta). Diagnostique: `bash ~/semente-bin/blindar.sh status`, firewall (`sudo ufw status`), erro de digitação na porta. Só avance quando o teste passar.

### 5. FASE 2 (fecha a porta antiga) — na conexão NOVA

Antes, garanta o login por chave (necessário pra desligar senha): se a pessoa ainda entra só por senha, gere/instale uma chave no computador dela (`ssh-keygen` + `ssh-copy-id -p {PORTA_SSH} usuario@{IP_VPS}`) e faça ela entrar uma vez com a chave.

```bash
sudo bash ~/semente-bin/blindar.sh fase2
```

A fase2 tem duas travas automáticas: (a) só roda se a conexão atual entrou pela porta nova; (b) só desliga login por senha — **inclusive o de root** — se existir chave instalada E já houve login por chave no histórico; sem chave comprovada ela mantém TODO login por senha como está e avisa (instale a chave e rode a fase2 de novo). Ou seja: mesmo que o passo da chave tenha sido pulado, ninguém fica trancado fora — a blindagem só fica completa quando a chave existir.

**Check final (antes de fechar qualquer janela):** abrir mais uma conexão nova `ssh -p {PORTA_SSH} ...` e entrar. Se não entrar, a própria saída da fase2 mostra o comando de desfazer — rode na sessão que ainda está aberta.

### 6. Checklist + arquivar

```bash
cp <pasta-do-repo-clonado>/base/seguranca/checklist.md ~/nexum/_nexum/seguranca-checklist.md
```

Substitua os `{SLOTS}` do arquivo copiado pelos valores reais e rode os 10 itens do checklist, mostrando o resultado pra pessoa em linguagem simples ("sua VPS agora só tem 3 portas abertas; o vigia já está de plantão").

## Se algo der MUITO errado (pessoa trancada fora)

Todo provedor de VPS tem um **console de emergência** no painel (acesso direto, sem SSH — na HostGator/Hostinger chama "Console"/"VNC"). Por lá: `sudo rm /etc/ssh/sshd_config.d/50-semente-blindagem.conf && sudo systemctl restart ssh && sudo ufw disable` e recomece da fase1. Mencione isso pra pessoa como o "extintor de incêndio" — existe, mas com as duas fases ninguém deve precisar.
