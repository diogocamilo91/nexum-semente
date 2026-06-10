#!/usr/bin/env bash
# Semente — EXEMPLO de snippet do fechamento do dia.
# Copie como modelo ao instalar um módulo: o módulo dropa um arquivo assim em
# ~/.config/semente/fechamento.d/NN-nome.sh (NN = ordem: 10 agenda, 20 e-mails,
# 30 news, 40 aprendizado... a VPS fecha a mensagem sozinha, sem snippet).
#
# Contrato (resumo — o completo está no topo de fechamento-dia.sh):
#   - imprime a seção pronta: 1ª linha = título com emoji;
#   - imprimir NADA = seção omitida hoje (use pra "nada a dizer", não é erro);
#   - terminar em <120s, sem input, sem mandar mensagem, sem efeito colateral.
set -u

# Exemplo bobo: frase do dia só pra ver a seção aparecer no fechamento.
echo "🌱 Exemplo"
echo "Este é um snippet de exemplo. Apague-me quando o primeiro módulo de verdade chegar."
