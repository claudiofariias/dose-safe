# Dose Safe — testes manuais da versão UX + catálogo Anvisa

## Inicialização

1. Extraia o ZIP.
2. Preserve o seu arquivo `dose_safe.db` da versão antiga (faça cópia de segurança e coloque-o na mesma pasta do `server.py`, com o servidor parado).
3. No terminal, dentro da pasta `dose-safe`: `python server.py`.
4. Abra `http://localhost:8000`.
5. Para testes de lógica: `python -m unittest discover -s anvisa -p "test_*.py" -v`.

## Caso A — criança, Dipirona (dados **fictícios**, apenas teste do software)

- Paciente de teste: idade **5 anos**, peso **25 kg** (ajuste o nascimento para completar 5 anos).
- Medicamento: **Dipirona**.
- Apresentação: **Solução oral 50 mg/mL**.
- Indicação: **febre**.
- Registro Anvisa: **deixe em branco** se não conferiu a embalagem e a bula específicas.
- Quantidade por administração: **5 mL**.
- Frequência: **8/8h**; duração: **3 dias**.
- Volume do frasco: **100 mL**.

**Resultado matemático esperado:** 5 × 3 × 3 = **45 mL**; **1 frasco de 100 mL**; conversão apenas matemática de 250 mg/dose (10 mg/kg/dose). **Isso não aprova uma dose pediátrica real.**

**Verifique:** o título pediátrico fica em linha separada da idade; a informação complementar aparece abaixo. O campo Indicação está alinhado; o registro fica recolhido em `Registro do produto (opcional)`. Em `Analisar segurança`, a posologia continuará **NÃO VERIFICADA** enquanto não houver regra aprovada para a bula, apresentação e indicação.

## Caso B — adulto, Dipirona (dados fictícios)

- Paciente: **25 anos**, peso **70 kg**.
- Medicamento: **Dipirona**, **Solução oral 50 mg/mL**.
- Indicação: **febre**; registro: **não informado**.
- Quantidade por administração: **10 mL**, frequência **8/8h**, duração **5 dias**, frasco **100 mL**.

**Resultado matemático esperado:** **150 mL** necessários; **2 frascos**. O cabeçalho **Modo adulto** e o texto **Informe a dose...** aparecem em linhas distintas. A verificação clínica permanece **NÃO VERIFICADA**, pois nenhuma regra aprovada foi adicionada.

## Caso C — adolescente, inspeção da classificação

- Paciente fictício de **15 anos**.
- Deve aparecer **Modo adolescente — dose por apresentação**, sem classificá-lo como adulto ou atribuir posologia adulta automaticamente.

## Revisão clínica humana

- Os **100 rascunhos** estão em `anvisa/rascunhos_catalogo/`; os **20 prioritários** em `anvisa/rascunhos/`.
- `anvisa/candidatos_para_revisao.json` oferece números de registro do CSV para **conferência**, sem atribuir apresentações ou doses.
- Escolha o produto e a bula oficial correspondente, revise a seção de posologia e preencha a ficha; um profissional habilitado deve conferir antes da aprovação, conforme `anvisa/GUIA_ANVISA.md`.
- Nenhuma dose ou informação obtida por IA é considerada aprovada sem essa etapa.
