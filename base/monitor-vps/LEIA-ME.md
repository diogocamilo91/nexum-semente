# base/monitor-vps/ — LEIA-ME (instruções pra VOCÊ, Claude instalador)

Você vai instalar o vigia da máquina: um coletor que mede CPU, memória, disco, serviços e a saúde do backup a cada 30 minutos, guarda histórico, e **só interrompe o dono em emergência de verdade** (serviço caído ou disco quase cheio). O retrato completo aparece uma vez por dia, no fechamento das 21h — a filosofia é: na dúvida, quieto.

Pré-requisitos: `base/lib/alerta.sh` instalado e testado. (O bloco de backup no retrato fica "(ainda sem log)" até o `base/backup/` ser instalado — não é erro.)

## O que tem aqui

| Arquivo | Vira o quê |
|---|---|
| `saude_vps.py` | `~/semente-bin/saude_vps.py` — coletor (só Python padrão, leve pra VPS de 1-2 GB) |
| `monitor-vps.sh` | `~/semente-bin/monitor-vps.sh` — roda no cron e alerta só emergência |

## Slots / configuração

| Variável no config.env | O que é | De onde vem |
|---|---|---|
| `MONITOR_SERVICOS` | serviços vigiados, formato `"Nome:padrão-do-pgrep,Nome2:padrão2"` | você escreve, conforme o que instalou |

O padrão (se ausente) é `"Bot Telegram:bot.py"`. Ajuste pro processo REAL do bot da pessoa (confira com `pgrep -af bot.py`) e acrescente cada serviço novo que módulos futuros criarem. Exemplo:

```bash
grep -q "^MONITOR_SERVICOS=" ~/.config/semente/config.env || \
  echo 'MONITOR_SERVICOS="Bot Telegram:bot.py"' >> ~/.config/semente/config.env
```

## Passo a passo

### 1. Instalar

```bash
cp <pasta-do-repo-clonado>/base/monitor-vps/saude_vps.py  ~/semente-bin/saude_vps.py
cp <pasta-do-repo-clonado>/base/monitor-vps/monitor-vps.sh ~/semente-bin/monitor-vps.sh
chmod +x ~/semente-bin/saude_vps.py ~/semente-bin/monitor-vps.sh
```

### 2. Verificar o coletor

```bash
python3 ~/semente-bin/saude_vps.py
```

**Check:** imprime o retrato ("🖥️ VPS — ...") com CPU, memória, disco, serviços e backup; e `~/semente-bin/log/vps-historico.csv` ganhou uma linha. Mostre o retrato pra pessoa e traduza: "sua máquina está assim".

**Se falhar:** quase sempre é serviço com padrão errado em `MONITOR_SERVICOS` (aparece ❌ pra um serviço que está no ar) — confira o padrão com `pgrep -af <padrão>`.

### 3. Verificar o alarme (sem esperar uma emergência real)

```bash
bash ~/semente-bin/monitor-vps.sh && echo "rodou ok (silêncio = tudo saudável)"
```

Silêncio é o comportamento certo. Pra provar que o alarme dispara, derrube o bot por um instante (`pkill -f bot.py`), rode o monitor de novo (deve chegar "🖥️ VPS — emergência" no Telegram) e **religue o bot em seguida** (do jeito que o `base/bot-telegram/` documenta). Rode o monitor mais uma vez: não deve repetir o alerta (anti-spam).

### 4. Cron de 30 em 30 minutos

```bash
( crontab -l 2>/dev/null | grep -v semente-bin/monitor-vps.sh ; echo '*/30 * * * * /usr/bin/bash $HOME/semente-bin/monitor-vps.sh' ) | crontab -
crontab -l | grep monitor
```

## Operação (deixe anotado pro assistente da pessoa)

- Retrato sob demanda: `python3 ~/semente-bin/saude_vps.py` (é o que o fechamento das 21h usa).
- Pausar alertas: `touch ~/monitor-vps.PAUSED` · religar: `rm ~/monitor-vps.PAUSED`.
- Afinar limites (disco/memória/carga): constantes no topo de `saude_vps.py`.
- O que conta como emergência: função `emergencias()` — mexa com parcimônia; a régua é não encher o saco do dono.
