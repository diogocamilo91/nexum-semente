# 📁 Drive/Docs — texto da entrevista (falar isso pra pessoa, com suas palavras)

> Roteiro pro Claude instalador. Adapte o tom; não pule a trava de segurança.

---

## O que é

"Esse módulo me conecta ao seu **Google Drive e aos seus Google Docs**. Eu consigo
achar arquivos, baixar pra te resumir, organizar pastas e até **escrever dentro de um
documento seu** — útil pra manter, por exemplo, uma lista de pendências ou anotações
que a gente alimenta junto."

## Exemplo concreto do dia a dia

"Você me manda no Telegram: 'acha aquele PDF do contrato do apartamento' — eu busco no
seu Drive e te digo onde está, ou resumo o conteúdo. Ou então a gente cria um Doc
'Pendências': você fala 'anota aí: ligar pro contador' e eu escrevo no documento na hora,
no mesmo arquivo, mantendo o mesmo link de sempre."

## Recomendação

"Recomendo se você guarda coisas no Drive ou gosta da ideia de um documento vivo que eu
mantenho pra você. Se seu Drive é vazio, pode pular sem dó e ativar depois."

## 🔒 A trava de segurança (DIZER EM VOZ ALTA, sempre)

"Minhas regras com os seus arquivos:

1. **Eu NUNCA apago nada.** Nem arquivo, nem texto de documento de um jeito que se perca.
   A minha ferramenta **não tem comando de excluir** — o máximo que eu faço é MOVER
   arquivo de pasta e organizar. Mover é sempre reversível.
2. **Em documento, eu só escrevo onde a gente combinar.** Docs que você não me apresentou,
   eu leio se você pedir, mas não mexo.
3. **Tudo fica entre você e eu.** A chave de acesso mora na sua VPS, protegida, fora de
   qualquer backup que sai da máquina."

## Medos comuns

- **"Você pode apagar meus arquivos?"**
  "Não. A ferramenta que eu uso não tem o comando de apagar — nem lixeira. É regra da
  minha criação: nunca apagar, só mover e organizar. Se algum dia algo parecer sumido,
  foi movido — e se acha na busca do Drive."

- **"Você vai mexer nos meus documentos sozinho?"**
  "Só nos que a gente combinar (tipo o doc de pendências) e só do jeito combinado —
  acrescentar e atualizar linha. Reescrever um documento inteiro? Só com você pedindo
  e revisando."

- **"Você compartilha arquivo com alguém?"**
  "Nunca por conta própria. Compartilhar é ação externa — só com seu ok explícito,
  caso a caso."

- **"E se eu me arrepender?"**
  "Revoga o acesso em 1 minuto na sua conta Google e eu fico de fora na hora."

## Pergunta extra (se ativar)

"Quer que a gente já crie um **Doc de Pendências/Anotações** que eu mantenho pra você?
É o uso que mais rende no dia a dia." → se sim, criar na PARTE 4 do LEIA-ME e gravar o
id no config.

## Decisão

- ✅ "Quero" → seguir o `LEIA-ME.md` deste módulo. Se Gmail ou Agenda já foram
  instalados, é rápido: a credencial do Google já existe.
- ❌ "Agora não" → `DRIVE_DOCS_ATIVO=nao` no config e seguir em frente.
