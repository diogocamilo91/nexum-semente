# 📅 Agenda — texto da entrevista (falar isso pra pessoa, com suas palavras)

> Roteiro pro Claude instalador. Adapte o tom; não pule a trava de segurança.

---

## O que é

"Esse módulo me deixa **ler a sua agenda do Google** (Google Calendar). Com isso eu sei
o que você tem marcado e consigo te lembrar das coisas sem você precisar abrir o app."

## Exemplo concreto do dia a dia

"Todo fim de dia, junto com o resumo que eu te mando, vai a sua agenda de amanhã:
'amanhã você tem dentista às 9h e reunião às 14h'. E a qualquer momento você pode me
perguntar no Telegram 'o que eu tenho quinta?' que eu respondo na hora."

## Recomendação

"Recomendo ativar — é leve, só leitura, e deixa o resumo do dia muito mais útil.
Só não vale a pena se você não usa o Google Agenda."

## 🔒 A trava de segurança (DIZER EM VOZ ALTA, sempre)

"Minhas regras com a sua agenda:

1. **A permissão que vamos criar é SÓ DE LEITURA.** Tecnicamente eu não consigo criar,
   mudar nem apagar compromisso — a chave não abre essa porta.
2. Se um dia você quiser que eu também marque compromissos por você, a gente cria essa
   permissão à parte — e mesmo aí a regra é: **eu só mexo na agenda com a sua
   confirmação, caso a caso.**
3. O que está na sua agenda fica entre você e eu, aqui na sua VPS."

## Medos comuns

- **"Você vai remarcar/apagar algo sem querer?"**
  "Impossível. A autorização é de leitura — o Google nem aceita um pedido meu de escrita.
  É como te entregar a agenda pra olhar com as mãos amarradas."

- **"Você vê agendas compartilhadas comigo?"**
  "Só as que você escolher. Na instalação eu pergunto quais agendas entram — pode ser só
  a principal, ou também a da família/trabalho se você quiser."

- **"E se eu me arrepender?"**
  "Revoga em 1 minuto na sua conta Google (Segurança → conexões de terceiros) e eu perco
  o acesso na hora."

## Pergunta extra (se ativar)

"Você quer que eu olhe só a sua agenda principal, ou tem outras (família, trabalho,
feriados) que devem entrar no resumo também?"
→ anotar a resposta; vira a chave `AGENDA_CALENDARIOS` no config.

## Decisão

- ✅ "Quero" → seguir o `LEIA-ME.md` deste módulo. Se o módulo Gmail já foi instalado,
  é rápido (~3 min): a credencial do Google já existe, só ativa a API e autoriza.
- ❌ "Agora não" → `AGENDA_ATIVO=nao` no config e seguir em frente.
