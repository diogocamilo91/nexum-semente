#!/usr/bin/env bash
# Semente — snippet do fechamento: seção 🗞️ News.
# Vai pra ~/.config/semente/fechamento.d/30-news.sh (com +x).
# Contrato: imprime a seção pronta (1ª linha = título); nada = seção omitida.
set -u

SAIDA=$(timeout 60 python3 "$HOME/semente-bin/news.py" --painel 2>/dev/null)

# se o coletor falhou ou só devolveu a frase de erro, omite a seção (sem drama)
case "$SAIDA" in
  ""|*"Não consegui ler os portais"*) exit 0 ;;
esac

printf '%s\n' "$SAIDA"
