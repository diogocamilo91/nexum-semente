# 🎙️ Gravações — texto da entrevista (falar isso pra pessoa, com suas palavras)

> Este arquivo é o roteiro do que VOCÊ (Claude instalador) fala pro dono na entrevista.
> Adapte o tom, mas NÃO pule: a parte da chave do Gemini (é a única coisa paga do módulo)
> e a regra de privacidade. Diga as duas ANTES de perguntar se a pessoa quer.

---

## O que é (explicar em linguagem de gente)

"Esse módulo transforma áudio em texto organizado. Você grava uma reunião, uma aula,
uma conversa importante ou uma nota de voz longa, joga o arquivo numa pasta da sua VPS —
e alguns minutos depois eu te entrego **a transcrição completa, separada por quem fala,
com resumo, decisões, pendências e os momentos-chave**. Tudo vira um documento guardado
no seu acervo, e você pode me perguntar qualquer coisa sobre ele depois."

## Exemplo concreto do dia a dia

"Você sai de uma reunião de 40 minutos que gravou no celular. Manda o arquivo pra pasta
(te ensino o jeito mais fácil pro seu caso) e segue a vida. Daqui a pouco chega no seu
Telegram: 'Transcrevi e avaliei a reunião'. Aí você me pergunta 'o que ficou combinado?'
e eu respondo na hora, citando até o minuto em que foi dito."

## Recomendação

"Recomendo pra quem grava coisas com alguma frequência — reuniões, aulas, ideias faladas.
Se você nunca grava nada, pula sem dó; dá pra ativar em 10 minutos qualquer dia."

## 💸 O custo (dizer SEMPRE, com os números)

"Esse é o único módulo que usa um serviço pago por fora: a transcrição é feita pelo
**Gemini, a IA do Google** — é o jeito certo de transcrever áudio longo numa VPS pequena
como a sua (fazer isso aqui dentro travaria a máquina).

- Você cria uma **chave própria**, na SUA conta Google, em 2 minutos. Eu te guio.
- O custo é por uso: **na casa de R$ 0,50 a R$ 1 por HORA de áudio** (estimativa de
  hoje; áudio curto custa centavos). O Google ainda tem uma cota gratuita por dia que,
  pra pouco uso, pode zerar essa conta — mas não prometo que ela dura pra sempre.
- Você acompanha e limita o gasto na sua conta Google, e pode matar a chave quando quiser."

## 🔒 Privacidade (dizer SEMPRE)

"Como funciona com os seus áudios:

1. **O áudio sai da VPS UMA vez, só pra transcrever**: vai pro Gemini (Google), que
   devolve o texto. É a mesma confiança de usar qualquer serviço do Google — mas é
   justo você saber que o áudio passa por lá.
2. **O resultado fica na SUA VPS**, no seu acervo de conhecimento — e nunca em chat
   ou link público.
3. **Eu nunca apago um áudio.** Os arquivos processados ficam guardados numa pasta;
   se algo der errado, o original está sempre lá."

## A chave do Gemini (guiar na hora, se a pessoa topar)

1. "Abre **aistudio.google.com/apikey** logado na sua conta Google."
2. "Clica em **Create API key** (criar chave). Se pedir, cria/escolhe um projeto qualquer."
3. "Vai aparecer uma chave começando com **AIza**. Copia e me manda — eu guardo num
   arquivo protegido aqui na VPS, que não sai daqui."
4. (Se a pessoa quiser teto de gasto: no mesmo site dá pra ver o uso; o cartão só é
   cobrado se ela ativar o faturamento — sem faturamento, vale a cota grátis e para
   quando acaba. Explique conforme o caso dela.)

## Pergunta extra (se ativar)

"Como você prefere me mandar os áudios? Pelo app de arquivos que você já usa pra VPS
(te mostro a pasta), ou quer que eu te ensine outro caminho?" — anote a resposta e
ensine o caminho escolhido na prática, com um áudio de teste.

## Decisão

- ✅ "Quero" → seguir o `LEIA-ME.md` deste módulo (instalação ~10 min + teste real).
- ❌ "Agora não" → registrar `GRAVACOES_ATIVO=nao` no config e seguir.
  Avisar: "se um dia você gravar algo importante, me fala que a gente liga isso."
