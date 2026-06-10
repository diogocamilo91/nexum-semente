# Segurança da VPS — checklist de verificação

Rode depois da blindagem (e repita de vez em quando — todos os comandos são SÓ LEITURA, não mudam nada). Cada item tem o comando e o resultado esperado. `{PORTA_SSH}` = a porta alta escolhida na entrevista (está em `~/.config/semente/config.env`).

| # | O que conferir | Comando | Esperado |
|---|---|---|---|
| 1 | SSH só na porta nova | `sudo sshd -T \| grep "^port"` | só `port {PORTA_SSH}` |
| 2 | Login de root por senha desligado* | `sudo sshd -T \| grep permitrootlogin` | `prohibit-password` (ou `no`) |
| 3 | Login por senha desligado* | `sudo sshd -T \| grep passwordauthentication` | `passwordauthentication no` |
| 4 | Firewall ligado, entrada negada por padrão | `sudo ufw status verbose` | `Status: active` + `Default: deny (incoming)` |
| 5 | Só {PORTA_SSH}, 80 e 443 abertas | `sudo ufw status numbered` | só essas 3 regras de entrada (tcp) |
| 6 | fail2ban vigiando o SSH | `sudo fail2ban-client status sshd` | jail ativa (mostra failed/banned) |
| 7 | Atualizações automáticas ligadas | `cat /etc/apt/apt.conf.d/20auto-upgrades` | as duas linhas com `"1"` |
| 8 | Nada além do esperado escutando a internet | `sudo ss -tlnp \| grep -v 127.0.0` | só sshd na {PORTA_SSH} (e 80/443 se houver site) |
| 9 | Segredos trancados | `ls -ld ~/.config/semente` | permissão `drwx------` (700) |
| 10 | Segredos fora do backup | `git -C ~/nexum ls-files \| grep -i "token\|senha\|secret"` | vazio |

\* os itens 2 e 3 só valem se a fase2 conseguiu desligar a senha (precisa de chave instalada + login por chave comprovado). Se ainda está `yes`, instale a chave, entre com ela e rode a fase2 de novo — é o item mais importante da lista.

## Sinais de vida (de vez em quando)

```bash
sudo fail2ban-client status sshd      # quantas tentativas de invasão já barrou
last -20                              # últimos logins (reconhece todos?)
```

## Lembretes de comportamento (way of life — valem sempre)

- **Nunca apagar:** arquivo "errado" se MOVE (pra `~/nexum/_entrada/`), não se deleta.
- **Segredos** moram em `~/.config/semente/` (chmod 600/700), nunca dentro de `~/nexum/`.
- **Ação externa** (e-mail, mensagem pra terceiro, editar agenda) só com OK explícito do dono.
- A VPS é de **provedor**: o provedor mantém acesso de gerência root — é o padrão do modelo de hospedagem, não uma falha.
