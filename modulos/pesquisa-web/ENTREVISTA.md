# 🔎 Pesquisa web — texto da entrevista (falar isso pra pessoa, com suas palavras)

> Roteiro pro Claude instalador. Módulo trivial: não instala nada — é capacidade
> que o assistente já tem. A entrevista existe pra pessoa SABER que tem e decidir.

---

## O que é

"Esse 'módulo' sou eu pesquisando na internet por você. Não precisa instalar nada —
eu já sei fazer. Você me pergunta qualquer coisa no Telegram e, quando a resposta
pede informação fresca, eu busco na web, leio algumas fontes e te trago a conclusão,
não uma lista de links."

## Exemplo concreto do dia a dia

"'Que horas é o jogo hoje?', 'esse produto vale a pena? compara os preços',
'resume essa notícia que tá todo mundo falando', 'qual o melhor voo pra esse fim
de semana?'. Você pergunta como perguntaria a um amigo; eu pesquiso, cruzo 2-3
fontes e respondo curto."

## Recomendação

"Recomendo deixar ligado — não custa nada, não dá trabalho e transforma o assistente
num 'pergunta-qualquer-coisa'. O único motivo pra desligar é se você quiser um
assistente que só olhe pra dentro (seus arquivos, seu e-mail) e nunca pra internet."

## 🔒 A trava de segurança (DIZER, mesmo sendo simples)

"Duas coisas pra você saber:

1. **Pesquisar é só LER a internet.** Eu não publico, não posto, não comento, não
   preencho formulário em site nenhum por conta própria — qualquer ação pra fora
   continua precisando do seu ok, caso a caso.
2. **Eu não saio espalhando seus dados na busca.** Quando a pesquisa precisar de algo
   seu (ex.: cotar voo saindo da sua cidade), eu uso o mínimo necessário e nada de
   sensível — senha, documento, conversa sua não entram em busca, nunca."

## Medos comuns

- **"Você acredita em qualquer coisa que ler?"**
  "Não. Pra coisa importante eu cruzo mais de uma fonte e te digo o quanto estou
  confiante. Se as fontes discordam, eu falo que discordam."

- **"Isso custa mais caro?"**
  "Não — está dentro da mesma assinatura do Claude que você já paga."

## Decisão

- ✅ "Quero" (quase todo mundo) → seguir o `LEIA-ME.md` (1 minuto: é só registrar).
- ❌ "Não quero" → registrar `PESQUISA_WEB=nao` e gravar a regra na identidade
  (o assistente só pesquisa se o dono pedir explicitamente naquela conversa).
