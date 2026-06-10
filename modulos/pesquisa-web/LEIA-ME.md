# 🔎 Módulo Pesquisa web — roteiro (PRO CLAUDE instalador)

Este módulo NÃO instala nada: pesquisar na web é capacidade nativa do Claude
(ferramentas de busca/leitura de página da própria plataforma). O "trabalho" aqui é
só registrar a preferência do dono e a regra de uso na identidade do assistente.

**Antes:** entrevista feita (`ENTREVISTA.md`).

## PASSO 1 — registrar a escolha no config

```
[DENTRO DA VPS]
printf '\nPESQUISA_WEB=sim\n' >> ~/.config/semente/config.env     # ou =nao
```

## PASSO 2 — registrar a regra na identidade do assistente

Edite o `identidade.md` (em `~/nexum/_nexum/`) e acrescente, na seção de capacidades:

- Se **sim**: "Pesquisa web: LIGADA. Quando a resposta pedir informação fresca ou de
  fora, pesquiso por iniciativa própria, cruzo mais de uma fonte em assunto que importa
  e digo meu grau de confiança. Pesquisar é só LER: nunca publico, posto ou preencho
  nada em site por conta própria — ação externa segue precisando de ok do dono. Dado
  sensível do dono nunca entra em termo de busca."
- Se **não**: "Pesquisa web: SÓ SOB DEMANDA. Não pesquiso na internet por iniciativa
  própria; apenas quando o dono pedir explicitamente naquela conversa."

## PASSO 3 — testar (se ligou)

Faça uma pesquisa real de algo do interesse do dono (ele citou times, hobbies, cidade
na entrevista — use isso) e mande a resposta no Telegram. Serve de teste E de
demonstração: "isso é o que a pesquisa web faz".

**Check:** a busca retornou e o dono recebeu uma resposta curta com conclusão.

> Nota: algumas VPS têm IP de datacenter bloqueado por certos sites (antibot). Não é
> defeito do módulo; quando um site específico recusar, o caminho é dar o link pro dono
> abrir, ou usar outra fonte.

## Chaves no config

```
PESQUISA_WEB=sim|nao
```

Sem cron, sem token, sem credencial. Registrar no `INDEX.md` que o módulo foi decidido.
