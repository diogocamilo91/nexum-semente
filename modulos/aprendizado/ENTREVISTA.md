# 🎓 Aprendizado — texto da entrevista (falar isso pra pessoa, com suas palavras)

> Este arquivo é o roteiro do que VOCÊ (Claude instalador) fala pro dono na entrevista.
> Adapte o tom; a parte de coletar os canais é interativa — faça com calma, canal a canal.

---

## O que é (explicar em linguagem de gente)

"Esse módulo é a sua curadoria pessoal de aprendizado. Você me fala quais canais de
YouTube você acompanha — de qualquer assunto: tecnologia, negócios, história, culinária —
e toda noite, no resumo do dia, eu te conto **o que esses canais lançaram de novo**,
com uma linha sobre cada vídeo. Você nunca mais perde lançamento de canal que gosta,
e nem precisa ficar rolando o YouTube."

## Exemplo concreto do dia a dia

"À noite chega no seu Telegram, dentro do fechamento do dia, uma seção assim:

🎓 Aprendizado
• [Canal X] Como funciona um motor elétrico — explicação visual de 12 min
• [Canal Y] Entrevista com fulano sobre investimentos — parece ser sobre renda fixa

Aí você decide na hora o que vale seu tempo. E se um dia quiser, me manda o link de
qualquer vídeo que eu leio a transcrição e te devolvo o resumo — sem você assistir."

## Recomendação

"Recomendo ativar se você segue pelo menos 3-4 canais. Se você quase não usa YouTube,
pode pular — é fácil ativar depois. Quanto mais canais, melhor a curadoria."

## Trava / custo (dizer sempre)

"Custo: zero — uso o canal público de novidades do YouTube, sem chave, sem login.
Esse módulo não toca em nada seu: não acessa sua conta do YouTube nem do Google,
só lê a lista pública de vídeos dos canais que você me indicar."

## A coleta dos canais (interativa, canal a canal)

Pergunte: **"Quais canais você acompanha? Pode me mandar o @nome, o link do canal ou
até o link de um vídeo dele — eu me viro."**

Pra cada canal que a pessoa mandar, você roda na hora, **direto do repo clonado**
(o script ainda não foi copiado pra `~/semente-bin/` — isso é o passo 1 do LEIA-ME,
que vem depois desta entrevista):

```bash
python3 ~/nexum-semente/modulos/aprendizado/aprendizado.py --achar '<o que a pessoa mandou>'
```

e confirma com ela: "achei: **<nome do canal>** — é esse?". Vá montando a lista.
No fim, pergunte se ela quer agrupar por tema ("tecnologia", "negócios"...) ou se
pode ficar tudo num grupo só ("meus canais").

Pergunta extra: **"Shorts (vídeos curtinhos) entram ou ficam de fora?"** —
recomende deixar de fora (a curadoria fica mais limpa).

## Decisão

- ✅ "Quero" → seguir o `LEIA-ME.md` deste módulo (instalação ~5 min + o tempo da coleta).
- ❌ "Agora não" → registrar `APRENDIZADO_ATIVO=nao` no config e seguir.
  Avisar: "se mudar de ideia, é só me mandar os canais que você segue."
