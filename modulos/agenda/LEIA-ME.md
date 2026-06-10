# 📅 Módulo Agenda — roteiro de instalação (PRO CLAUDE instalador)

Leitura da agenda do Google Calendar do dono, **só-leitura por desenho** (escopo
`calendar.readonly`). Ferramenta: `agenda.py` (Python, biblioteca padrão, sem dependência).

**Antes de instalar:** entrevista feita (`ENTREVISTA.md`) e dono disse SIM.

**Slots usados:** `{EMAIL_DONO}`, `{NOME_ASSISTENTE}`.

**Chaves gravadas em `~/.config/semente/config.env`:**
```
AGENDA_ATIVO=sim
AGENDA_CALENDARIOS=primary                  # ou lista: primary,id-da-agenda-2,...
#FUSO_HORARIO=America/Sao_Paulo             # só se o dono não for desse fuso
```

---

## PARTE 1 — credencial do Google

**Caso A — módulo Gmail JÁ instalado** (existe `~/.config/semente/google/oauth_client.json`):
a credencial serve. Só falta ativar a API do Calendar no MESMO projeto. Peça pro dono,
logado em `{EMAIL_DONO}`:
1. Abrir https://console.cloud.google.com/ e conferir no seletor do topo que o projeto
   `{NOME_ASSISTENTE}` está selecionado.
2. Menu ☰ → **APIs e serviços → Biblioteca** → buscar **"Google Calendar API"** →
   clicar → **Ativar**.
Pronto, vá pra PARTE 2.

**Caso B — primeiro módulo Google da casa:** o dono precisa criar o projeto + a
credencial OAuth do zero. O passo a passo completo (criar projeto, tela de permissão,
publicar "Em produção", credencial Desktop, download do JSON, subir pra VPS) está em
**`modulos/gmail/LEIA-ME.md`, PARTES 1 e 2** — siga exatamente aquilo, com UMA troca:
no passo de ativar API, ative **"Google Calendar API"** (em vez de Gmail API; pode
ativar as duas se a pessoa pretende ter o Gmail depois). O destino do arquivo é o mesmo:
`~/.config/semente/google/oauth_client.json` (chmod 600).

> ⚠️ Não esqueça o passo **"Publicar app → Em produção"** — sem ele a autorização morre
> a cada 7 dias.

## PARTE 2 — instalar a ferramenta e autorizar

```
[DENTRO DA VPS]
mkdir -p ~/semente-bin/log
cp <pasta-do-repo-clonado>/modulos/agenda/agenda.py ~/semente-bin/agenda.py
chmod +x ~/semente-bin/agenda.py
~/semente-bin/agenda.py auth-url
```
Mande o link pro dono (logado em `{EMAIL_DONO}`): ele vai ver "app não verificado" →
**Avançado → Acessar {NOME_ASSISTENTE}** → **Permitir** → o navegador "falha" em
`localhost:8766` (esperado) → ele copia a **URL inteira** da barra e cola no chat.
O código expira em minutos:
```
[DENTRO DA VPS]
~/semente-bin/agenda.py auth-finish "<URL colada>"
```
**Check:** `OK - autorizado.`

Na tela de permissão o dono confere que o pedido é **"Ver eventos"** (leitura) — vale
mostrar isso a ele: é a trava prometida na entrevista, visível no próprio Google.

## PARTE 3 — escolher as agendas e testar

Listar as agendas da conta (pra montar a resposta da pergunta extra da entrevista):
```
[DENTRO DA VPS]
~/semente-bin/agenda.py agendas
```
Mostre a lista pro dono e pergunte quais entram. Grave no config (ids separados por
vírgula; `primary` = a principal; pra dar nome a uma agenda extra use `Nome=id`):
```
[DENTRO DA VPS]
printf '\nAGENDA_ATIVO=sim\nAGENDA_CALENDARIOS=primary\n' >> ~/.config/semente/config.env
```
Exemplo com mais agendas: `AGENDA_CALENDARIOS=primary,Família=abc123@group.calendar.google.com,Feriados=pt-br.brazilian.official#holiday@group.v.calendar.google.com`

Teste:
```
[DENTRO DA VPS]
~/semente-bin/agenda.py hoje
~/semente-bin/agenda.py amanha
```
**Check:** lista os compromissos (ou "(sem compromissos)") sem erro. Confirme com o dono
que bate com o app dele.

## PARTE 4 — plugar no fechamento do dia

O fechamento (`base/fechamento/`) funciona por snippets em `~/.config/semente/fechamento.d/`.
Crie o da agenda (pode criar mesmo que o fechamento ainda não esteja instalado — ele
passa a valer quando o fechamento entrar; é instalado por último, pela ordem da raiz):

```
[DENTRO DA VPS]
mkdir -p ~/.config/semente/fechamento.d
cat > ~/.config/semente/fechamento.d/10-agenda.sh <<'EOF'
#!/usr/bin/env bash
# Seção 📅 do fechamento — agenda de amanhã (sexta: o fim de semana inteiro).
set -u
if [ "$(date +%u)" = "5" ]; then
  TITULO="📅 Fim de semana"; SAIDA="$("$HOME/semente-bin/agenda.py" fds 2>/dev/null)"
else
  TITULO="📅 Amanhã";        SAIDA="$("$HOME/semente-bin/agenda.py" amanha 2>/dev/null)"
fi
[ -n "$SAIDA" ] && { echo "$TITULO"; echo "$SAIDA"; }
EOF
chmod +x ~/.config/semente/fechamento.d/10-agenda.sh
bash ~/.config/semente/fechamento.d/10-agenda.sh   # teste
```

**Check:** o teste imprime "📅 Amanhã" (ou "📅 Fim de semana") + os compromissos
(ou "(sem compromissos)"). Anote em `~/nexum/_nexum/ponto_atual.md` que o snippet existe.

---

## A ferramenta `agenda.py` (referência rápida)

```
agenda.py agendas              # lista as agendas da conta (id + nome)
agenda.py hoje                 # compromissos de hoje
agenda.py amanha               # compromissos de amanhã (sexta → inclui sáb+dom? não: use fds)
agenda.py fds                  # sábado e domingo próximos
agenda.py dia 2026-12-25       # um dia específico
agenda.py proximos [N]         # os próximos N dias (padrão 7)
```
Saída em texto limpo: `HH:MM–HH:MM  Título  [Agenda] @ Local` (ou "dia todo").

**Não existe comando de criar/editar/apagar evento.** O escopo é `calendar.readonly` —
o Google recusa escrita mesmo que se tente. Se um dia o dono quiser que o assistente
marque compromissos, isso é uma evolução consciente: nova autorização com escopo de
escrita + regra de confirmação caso a caso (documentar no `_nexum/` quando acontecer).

## Arquivos e privacidade

- Credencial: `~/.config/semente/google/oauth_client.json` (compartilhada entre módulos Google).
- Token: `~/.config/semente/google/token_agenda.json` (600; SÓ escopo de leitura de agenda).
- Nada disso entra no backup (fora de `~/nexum/`).

## Se falhar

| Sintoma | Causa | Conserto |
|---|---|---|
| `403 accessNotConfigured` | Calendar API não ativada | PARTE 1 |
| `invalid_grant` no auth-finish | código expirou | gerar `auth-url` de novo |
| Parou após ~7 dias | app OAuth "Em teste" | publicar "Em produção" + refazer auth |
| Agenda extra não aparece | id errado no config | `agenda.py agendas` e copiar o id exato |
| `404` num calendário | dono perdeu acesso àquela agenda | tirar do `AGENDA_CALENDARIOS` |

Depois de instalado: registrar no `INDEX.md` e no roteamento (assunto "agenda/compromissos"
→ este módulo).
