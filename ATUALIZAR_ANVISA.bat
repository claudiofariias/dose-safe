@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "anvisa\DADOS_ABERTOS_MEDICAMENTOS.csv" (
    echo Coloque o arquivo DADOS_ABERTOS_MEDICAMENTOS.csv na pasta anvisa.
    echo A relacao ja gerada esta em anvisa\saidas\RELATORIO_REVISAO.md
) else (
    python anvisa\sincronizar_anvisa.py --extrair-bulas
)
echo.
echo Veja anvisa\GUIA_ANVISA.md
pause
