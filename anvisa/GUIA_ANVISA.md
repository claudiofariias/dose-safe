# Integração Anvisa — inventário dos 100 medicamentos

**Situação:** preparação automatizada, não validação clínica concluída.

A Anvisa disponibiliza no Bulário Eletrônico as bulas e em seu Portal de Dados Abertos os registros de medicamentos. No documento oficial *Bula Digital: Perguntas e Respostas*, item 3.2.4, a Anvisa orienta que ferramentas de *web crawler* não sejam utilizadas para extrair bulas em massa do Bulário. Por isso o processo abaixo **não rastreia o Bulário**.

Fontes:
- Bulário: https://consultas.anvisa.gov.br/#/bulario/
- Base oficial de registros: https://dados.anvisa.gov.br/dados/DADOS_ABERTOS_MEDICAMENTOS.csv
- Orientação sobre crawlers: https://www.gov.br/anvisa/pt-br/setorregulado/regularizacao/medicamentos/bulas-rotulos-e-nome-comercial/arquivos/BulaDigitalPerguntaseRespostas_v.1GGMED.pdf/@@download/file (item 3.2.4)

## 1. Inventariar os 100 medicamentos

Execute na pasta `dose-safe`:

```bash
python anvisa/sincronizar_anvisa.py
```

A saída `anvisa/saidas/catalogo_anvisa_revisao.json` lista os 100 princípios ativos, a pesquisa sugerida e pendências. O relatório está em `anvisa/saidas/RELATORIO_REVISAO.md`.

## 2. Cruzar automaticamente com registros oficiais

```bash
python anvisa/sincronizar_anvisa.py --baixar-csv
```

O comando baixa apenas **uma cópia pública** do CSV `DADOS_ABERTOS_MEDICAMENTOS.csv`, sem acessar o Bulário. Se a conexão falhar, baixe o arquivo pelo portal de Dados Abertos e execute:

```bash
python anvisa/sincronizar_anvisa.py --csv "caminho/para/DADOS_ABERTOS_MEDICAMENTOS.csv"
```

A correspondência por princípio ativo é conservadora. Os candidatos são **apenas registros para revisão**, incluindo registros potencialmente expirados/inativos e marcas diferentes. Não constituem seleção automática da bula correta. A base de registros **não contém regras clínicas de posologia**; não altera `catalog_100.json` nem `server.py`.

## 3. Extrair texto de bulas profissionais vinculadas

Baixe manualmente bulas **profissionais** oficiais para as apresentações que realmente deseja validar (selecionar fabricante, concentração, forma e registro). Guarde os arquivos em `anvisa/bulas_profissional/`.

Adicione cada vínculo em `anvisa/vinculos_bulas.json` no formato:

```json
[
  {
    "medicamento": "Dipirona",
    "arquivo": "dipirona-profissional.pdf",
    "tipo_bula": "profissional",
    "numero_registro": "PREENCHER_COM_REGISTRO_REAL",
    "fabricante": "PREENCHER",
    "apresentacao": "Solução oral 50 mg/mL — confirmar na bula",
    "versao_ou_expediente": "PREENCHER",
    "fonte_url": "URL_DA_BULA_OFICIAL",
    "data_consulta": "2026-11-11"
  }
]
```

O exemplo acima é **somente um modelo**: não há bula já vinculada e os campos devem ser substituídos por dados verificados. Para extrair:

```bash
python -m pip install pypdf
python anvisa/sincronizar_anvisa.py --extrair-bulas
```

O arquivo `anvisa/saidas/extracoes_bulas_pendentes.json` contém trechos candidatos de **posologia, contraindicações e interações**, com hash SHA-256 do PDF, registro, fonte e data de consulta. O reconhecimento de seções pode falhar em PDFs com sumário ou diagramação complexa; conferir obrigatoriamente com a bula original.

## 4. Referência documental necessária para comparar doses

Cada regra posológica precisa no mínimo de: princípio ativo, **produto/registro**, fabricante, apresentação exata, concentração, via, **indicação**, faixa etária, peso quando aplicável, dose por administração, intervalo, dose máxima, ajustes e contraindicações relevantes, seção e versão da bula, data de registro da fonte (sem exigência de revisor).

**Não** converter automaticamente texto extraído em faixas numéricas ou marcar uma prescrição como segura com base em registros de produtos. Até haver regras documentadas e completas, o aviso **“Posologia não verificada”** deve continuar ativo no Dose Safe. A base acadêmica de interações permanece separada.

## 5. Testes

```bash
python -m unittest discover -s anvisa -p 'test_*.py' -v
```

Se executar o script sem CSV e sem PDFs, ele gera o inventário e mantém todos os medicamentos como pendentes. Isso é intencional: **100 inventariados ≠ 100 clinicamente validados**.
