#!/usr/bin/env bash
# Semente — blindagem da VPS em DUAS FASES, pra NUNCA trancar o dono pra fora.
#
#   fase1  → instala ufw + fail2ban + atualizações automáticas; abre a porta SSH
#            NOVA mantendo a atual funcionando; liga o firewall (SSH atual + nova
#            + 80 + 443). NADA é fechado ainda.
#   (a pessoa TESTA o login pela porta nova, numa janela nova, sem fechar a atual)
#   fase2  → SÓ roda de uma conexão que JÁ entrou pela porta nova. Fecha a porta
#            antiga e — se houver chave instalada e login por chave comprovado —
#            desliga login por senha (inclusive o de root). SEM chave comprovada,
#            NENHUM login por senha é desligado: ninguém fica trancado fora.
#
# Configuração: PORTA_SSH em ~/.config/semente/config.env (porta alta escolhida
# na entrevista). Estado entre as fases: /etc/semente-blindagem.state.
#
# Uso:  sudo bash blindar.sh fase1
#       sudo bash blindar.sh fase2     (conectado pela porta NOVA!)
#       bash blindar.sh status         (não precisa de sudo)
set -euo pipefail

FASE="${1:-}"

# Guarda a conexão SSH atual ANTES de virar root (sudo apaga o ambiente)
if [ "$(id -u)" -ne 0 ] && [ "$FASE" != "status" ]; then
  exec sudo SEMENTE_SSH_CONN="${SSH_CONNECTION:-}" SEMENTE_USER="$USER" bash "$0" "$@"
fi

USUARIO="${SEMENTE_USER:-${SUDO_USER:-$USER}}"
HOMEDIR=$(getent passwd "$USUARIO" | cut -d: -f6)
CONFIG="$HOMEDIR/.config/semente/config.env"
STATE="/etc/semente-blindagem.state"
DROPIN_DIR="/etc/ssh/sshd_config.d"
DROPIN_F1="$DROPIN_DIR/49-semente-porta.conf"
DROPIN_F2="$DROPIN_DIR/50-semente-blindagem.conf"

erro() { echo "❌ $*" >&2; exit 1; }
ok()   { echo "✅ $*"; }

[ -f "$CONFIG" ] || erro "config não existe: $CONFIG"
# shellcheck disable=SC1090
set -a; . "$CONFIG"; set +a
PORTA_NOVA="${PORTA_SSH:-}"

# porta(s) em que o sshd REALMENTE escuta agora
portas_ativas() { sshd -T 2>/dev/null | awk '/^port /{print $2}' | sort -un | tr '\n' ' '; }

reiniciar_ssh() {
  sshd -t || erro "sshd -t reprovou a config — NÃO reiniciei o SSH (nada mudou no serviço)."
  # Ubuntu 22.10+: o ssh pode ser ativado por socket, que IGNORA a porta do sshd_config
  if systemctl is-enabled ssh.socket >/dev/null 2>&1; then
    systemctl disable --now ssh.socket >/dev/null 2>&1 || true
    systemctl enable ssh.service >/dev/null 2>&1 || true
  fi
  systemctl restart ssh 2>/dev/null || systemctl restart sshd
}

# ---------------------------------------------------------------- status
if [ "$FASE" = "status" ]; then
  if [ "$(id -u)" -eq 0 ]; then
    echo "Portas SSH ativas: $(portas_ativas)"
  else
    # sem root não dá pra perguntar ao sshd; lemos a configuração (legível por todos)
    PORTAS_CFG=$(grep -his '^[[:space:]]*Port[[:space:]]' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf 2>/dev/null | awk '{print $2}' | sort -un | tr '\n' ' ' || true)
    echo "Portas SSH configuradas: ${PORTAS_CFG:-22 (padrão)}"
  fi
  if ! command -v ufw >/dev/null 2>&1; then
    echo "ufw não instalado"
  elif [ "$(id -u)" -eq 0 ]; then
    ufw status 2>/dev/null | head -15
  else
    UFW_ESTADO=$(systemctl is-active ufw 2>/dev/null || true)   # is-active retorna ≠0 quando inativo
    echo "firewall ufw: ${UFW_ESTADO:-desconhecido} (detalhe: sudo ufw status)"
  fi
  [ -f "$STATE" ] && cat "$STATE" || echo "(fase1 ainda não rodou)"
  exit 0
fi

[ -n "$PORTA_NOVA" ] || erro "PORTA_SSH não definida em $CONFIG. O instalador escolhe uma porta alta (20000-60000) na entrevista e grava lá."
[[ "$PORTA_NOVA" =~ ^[0-9]+$ ]] && [ "$PORTA_NOVA" -ge 1024 ] && [ "$PORTA_NOVA" -le 65535 ] || erro "PORTA_SSH inválida: $PORTA_NOVA"

# ---------------------------------------------------------------- fase 1
if [ "$FASE" = "fase1" ]; then
  PORTAS_ATUAIS=$(portas_ativas)
  echo "Portas SSH hoje: $PORTAS_ATUAIS — vou ACRESCENTAR a $PORTA_NOVA sem fechar nada."

  # 1) pacotes de defesa
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ufw fail2ban unattended-upgrades openssh-server >/dev/null
  ok "ufw + fail2ban + unattended-upgrades instalados"

  # 2) atualizações de segurança automáticas
  cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
  ok "atualizações de segurança automáticas ligadas"

  # 3) porta nova ALÉM das atuais (Port é cumulativo no sshd)
  grep -q "^Include /etc/ssh/sshd_config.d" /etc/ssh/sshd_config 2>/dev/null \
    || erro "este sshd_config não tem Include de sshd_config.d — sistema fora do padrão Ubuntu/Debian; pare e ajuste manualmente."
  mkdir -p "$DROPIN_DIR"
  {
    echo "# Semente fase1: porta nova convivendo com a(s) antiga(s) até a fase2"
    for p in $PORTAS_ATUAIS; do echo "Port $p"; done
    echo "Port $PORTA_NOVA"
  } > "$DROPIN_F1"
  reiniciar_ssh
  sleep 1
  portas_ativas | grep -qw "$PORTA_NOVA" || erro "a porta $PORTA_NOVA não subiu (portas ativas: $(portas_ativas)). A antiga continua funcionando — nada foi fechado."
  ok "SSH escutando em: $(portas_ativas)(antiga(s) + nova)"

  # 4) firewall: libera TUDO que precisamos ANTES de ligar
  for p in $PORTAS_ATUAIS; do ufw allow "$p"/tcp >/dev/null; done
  ufw allow "$PORTA_NOVA"/tcp >/dev/null
  ufw allow 80/tcp  >/dev/null
  ufw allow 443/tcp >/dev/null
  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null
  ufw --force enable >/dev/null
  ok "firewall ligado: entrada só SSH ($PORTAS_ATUAIS$PORTA_NOVA), 80 e 443"

  # 5) fail2ban vigiando o SSH (todas as portas)
  cat > /etc/fail2ban/jail.d/semente-sshd.conf <<EOF
[sshd]
enabled = true
port = ssh,$PORTA_NOVA
EOF
  systemctl restart fail2ban
  ok "fail2ban ativo no SSH"

  printf 'PORTAS_ANTIGAS="%s"\nPORTA_NOVA="%s"\nFASE1="%s"\n' "$PORTAS_ATUAIS" "$PORTA_NOVA" "$(date '+%F %T')" > "$STATE"

  cat <<EOF

══════════════════════════════════════════════════════════════
FASE 1 OK — NADA foi fechado ainda. Agora o TESTE obrigatório:

1. NÃO feche esta janela.
2. Abra um terminal NOVO no computador da pessoa e conecte pela porta nova:
     ssh -p $PORTA_NOVA $USUARIO@IP-DA-VPS
3. Entrou? Então, NESSA CONEXÃO NOVA, rode:
     sudo bash $(realpath "$0" 2>/dev/null || echo "$0") fase2
4. Não entrou? Nada se perdeu: a porta antiga segue aberta.
   Diagnostique antes de pensar em fase2.
══════════════════════════════════════════════════════════════
EOF
  exit 0
fi

# ---------------------------------------------------------------- fase 2
if [ "$FASE" = "fase2" ]; then
  [ -f "$STATE" ] || erro "fase1 ainda não rodou (não achei $STATE)."
  # shellcheck disable=SC1090
  . "$STATE"

  # TRAVA 1: esta conexão TEM que ter entrado pela porta nova (prova viva de que ela funciona)
  CONN="${SEMENTE_SSH_CONN:-${SSH_CONNECTION:-}}"
  PORTA_CONN=$(echo "$CONN" | awk '{print $4}')
  if [ "$PORTA_CONN" != "$PORTA_NOVA" ]; then
    erro "você está conectado pela porta ${PORTA_CONN:-?}, não pela $PORTA_NOVA. Entre por 'ssh -p $PORTA_NOVA ...' e rode a fase2 de lá. (É a prova de que a porta nova funciona — sem ela eu não fecho a antiga.)"
  fi
  ok "conexão atual veio pela porta nova ($PORTA_NOVA) — seguro fechar a antiga"

  # TRAVA 2: só desligamos senha se existir chave instalada E login por chave comprovado
  TEM_CHAVE=0
  for h in "$HOMEDIR" /root; do
    if [ -s "$h/.ssh/authorized_keys" ]; then TEM_CHAVE=1; fi
  done
  CHAVE_USADA=0
  if grep -qs "Accepted publickey" /var/log/auth.log 2>/dev/null; then CHAVE_USADA=1; fi

  # root só perde o login por senha se tiver caminho garantido sem ela:
  # (a) chave instalada em /root + login por chave comprovado, OU
  # (b) o dono nem entra como root — esta instalação roda de um usuário comum,
  #     que continua entrando normalmente e tem sudo.
  ROOT_SEM_SENHA=0
  if [ -s /root/.ssh/authorized_keys ] && [ "$CHAVE_USADA" -eq 1 ]; then ROOT_SEM_SENHA=1; fi
  if [ "$USUARIO" != "root" ]; then ROOT_SEM_SENHA=1; fi

  {
    echo "# Semente fase2: blindagem final"
    echo "Port $PORTA_NOVA"
    if [ "$ROOT_SEM_SENHA" -eq 1 ]; then
      echo "PermitRootLogin prohibit-password"
    fi
    if [ "$TEM_CHAVE" -eq 1 ] && [ "$CHAVE_USADA" -eq 1 ]; then
      echo "PasswordAuthentication no"
    fi
  } > "$DROPIN_F2"
  rm -f "$DROPIN_F1"
  # comenta Port fixado no arquivo principal (senão a porta antiga continuaria aberta)
  sed -i 's/^[[:space:]]*Port[[:space:]]/#&/' /etc/ssh/sshd_config
  reiniciar_ssh
  sleep 1
  portas_ativas | grep -qw "$PORTA_NOVA" || erro "porta $PORTA_NOVA sumiu após reiniciar — investigue JÁ, sem fechar esta sessão."
  ok "SSH agora SÓ na porta $PORTA_NOVA"

  if [ "$TEM_CHAVE" -eq 1 ] && [ "$CHAVE_USADA" -eq 1 ]; then
    ok "login por senha DESLIGADO (há chave instalada e login por chave já aconteceu)"
  else
    echo "⚠️ login por senha MANTIDO: ainda não vi chave instalada + login por chave comprovado."
    echo "   Instale uma chave (ssh-copy-id), entre com ela, e rode a fase2 de novo."
  fi
  if [ "$ROOT_SEM_SENHA" -eq 1 ]; then
    ok "root: login por senha desligado (root só entra por chave)"
  else
    echo "⚠️ login de root por senha MANTIDO: é assim que você usa a VPS e ainda não há"
    echo "   chave do root comprovada. Quando instalar a chave e entrar com ela, rode a"
    echo "   fase2 de novo que eu fecho isso também."
  fi

  # fecha a(s) porta(s) antiga(s) no firewall
  for p in ${PORTAS_ANTIGAS:-}; do
    [ "$p" != "$PORTA_NOVA" ] && ufw delete allow "$p"/tcp >/dev/null 2>&1 || true
  done
  ok "firewall: porta(s) antiga(s) fechada(s) — entrada só $PORTA_NOVA, 80, 443"

  systemctl restart fail2ban || true
  printf 'FASE2="%s"\n' "$(date '+%F %T')" >> "$STATE"

  cat <<EOF

══════════════════════════════════════════════════════════════
FASE 2 OK. ANTES de fechar esta janela, teste um login NOVO:
     ssh -p $PORTA_NOVA $USUARIO@IP-DA-VPS
Entrou? Blindagem concluída. Rode o checklist (checklist.md).
Não entrou? NÃO feche esta sessão — desfaça com:
     sudo rm $DROPIN_F2 && sudo systemctl restart ssh
══════════════════════════════════════════════════════════════
EOF
  exit 0
fi

erro "uso: blindar.sh fase1 | fase2 | status"
