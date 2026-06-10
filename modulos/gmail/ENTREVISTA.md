# 📧 Gmail — texto da entrevista (falar isso pra pessoa, com suas palavras)

> Este arquivo é o roteiro do que VOCÊ (Claude instalador) fala pro dono na entrevista.
> Adapte o tom, mas NÃO pule a trava de segurança nem as respostas aos medos — elas
> devem ser ditas ANTES de perguntar se a pessoa quer o módulo.

---

## O que é (explicar em linguagem de gente)

"Esse módulo me dá acesso ao seu Gmail. Com ele eu consigo **ler seus e-mails, te avisar
do que importa, organizar a bagunça e escrever respostas pra você** — tudo daqui da sua VPS,
sem você precisar abrir a caixa de entrada."

## Exemplo concreto do dia a dia

"Na prática fica assim: chega um boleto ou um e-mail importante, eu te aviso no Telegram
com um resumo de uma linha. Você me responde 'responde dizendo que pago sexta' e eu escrevo
o e-mail, te mostro o texto, e **só envio quando você disser ok**. E propaganda? Eu marco
como lida sozinho, todo dia, sem te encher — sua caixa de entrada fica só com o que presta."

## Recomendação

"Eu recomendo ativar. É o módulo que mais muda o dia a dia: e-mail vira coisa que EU carrego,
não você. Se você quase não usa e-mail, pode pular e ativar depois — nada se perde."

## 🔒 A trava de segurança (DIZER EM VOZ ALTA, sempre)

"Antes de você decidir, as minhas regras com o seu e-mail — elas valem pra sempre e
estão gravadas na minha identidade:

1. **Eu NUNCA apago nada.** Nem propaganda. O máximo que eu faço é arquivar ou marcar
   como lida — o e-mail continua lá, na sua conta, pra sempre. A ferramenta que eu uso
   **nem tem o botão de apagar**: eu não excluo nem se me pedirem por engano.
2. **Eu escrevo e-mail, mas SÓ ENVIO com o seu ok.** Sempre te mostro o texto pronto antes.
   Sem o seu 'pode enviar', o e-mail fica em rascunho.
3. **Tudo fica aqui na sua VPS.** A chave de acesso mora num arquivo que só você e eu
   vemos; não vai pro GitHub, não vai pra lugar nenhum."

## Medos comuns (responder com calma se a pessoa perguntar — ou antecipar)

- **"Você vai apagar meu e-mail sem querer?"**
  "Não tem como. A permissão que vamos criar no Google não inclui exclusão permanente,
  e a minha ferramenta não tem comando de apagar — é como me dar uma chave que abre a
  porta mas não abre a gaveta. No pior cenário do mundo, um e-mail arquivado se acha
  na busca do Gmail em 5 segundos."

- **"Você vai mandar e-mail em meu nome sozinho?"**
  "Nunca. Enviar é ação externa — minha regra de criação diz que ação externa só
  acontece com sua confirmação explícita, caso a caso."

- **"Alguém mais consegue ler meus e-mails com isso?"**
  "Não. A autorização é entre o SEU Google e a SUA VPS. A chave fica num arquivo
  protegido aqui dentro, fora de qualquer backup que sai da máquina."

- **"E se eu me arrepender?"**
  "Você revoga em 1 minuto: myaccount.google.com → Segurança → conexões de terceiros →
  remover o app. Eu perco o acesso na hora."

## Pergunta extra (se a pessoa ativar o módulo)

"Quer que eu ligue também o **robô limpa-propaganda**? Todo dia ele marca como lida a aba
Promoções — não apaga, não arquiva, só tira o 'negrito' do que é propaganda pra sua caixa
ficar limpa. Recomendo que sim; é silencioso e reversível."

## Decisão

- ✅ "Quero" → seguir o `LEIA-ME.md` deste módulo (a parte do Google Cloud é guiada,
  uns 10-15 minutos com a pessoa no navegador).
- ❌ "Agora não" → registrar no config (`GMAIL_ATIVO=nao`) e seguir pro próximo módulo.
  Avisar: "qualquer dia você me fala 'quero o módulo do Gmail' e a gente ativa."
