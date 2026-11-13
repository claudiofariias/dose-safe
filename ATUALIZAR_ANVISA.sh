#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -f anvisa/DADOS_ABERTOS_MEDICAMENTOS.csv ]; then
  python3 anvisa/sincronizar_anvisa.py --extrair-bulas
else
  echo "Copie DADOS_ABERTOS_MEDICAMENTOS.csv para anvisa/ para atualizar; relatório anterior preservado."
  echo "A relação já gerada está em anvisa/saidas/RELATORIO_REVISAO.md"
fi
echo "Veja anvisa/GUIA_ANVISA.md"
