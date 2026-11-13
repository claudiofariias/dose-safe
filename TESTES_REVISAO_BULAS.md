# Dose Safe — testes de cobertura clínica e revisão (11/11/2026)

## 1. Criança / Dipirona / dispensação

Paciente de TESTE: 5 anos, 25 kg. Prescrição FICTÍCIA: Dipirona solução oral 50 mg/mL, indicação "febre", 5 mL, a cada 8 h, por 3 dias, frasco 100 mL.

**Matemática:** 5 mL = 250 mg; 5 mL × 3 administrações/dia × 3 dias = 45 mL; dispensação = 1 frasco de 100 mL. A ficha de pré-revisão cita uma tabela por peso para 24–30 kg, mas **isso não é validação clínica do caso**.

**Esperado na versão entregue:** `Posologia não verificada` enquanto não houver uma referência documental específica cadastrada para o produto e indicação.

## 2. Dose fora da faixa da fonte (não usar em paciente)

Repetir apenas em paciente fictício e ambiente de teste alterando a quantidade para 12 mL. A pré-revisão da bula Aché de 50 mg/mL mostra máximo **10 mL por dose na faixa de 24 a 30 kg**. Antes do cadastro de referência específica, o software continuará informando **não verificada**, sem necessariamente detectar excesso. **Não usar a ausência de alerta como autorização clínica.**

## 3. Produto associado não é monofármaco

Execute:

```bash
python anvisa/sincronizar_anvisa.py --csv anvisa/DADOS_ABERTOS_MEDICAMENTOS.csv
```

Consulte `anvisa/candidatos_para_revisao.json`: se a composição do produto listar outros princípios ativos, deve aparecer `suspeita_associacao: true`, ou ele deve ficar fora da amostra prioritária de 5 candidatos. O nome do princípio ativo isolado não aprova apresentação ou bula de associação.

## 4. Testes automáticos

```bash
python -m unittest discover -s anvisa -p "test_*.py" -v
```

O motor não carrega dados em `evidencias_curadas.json` como regras ativas. Somente `regras_clinicas.json` com status `documentada` (ou `aprovada` legado) e metadados completos é utilizado no comparador numérico. Os testes usam dados fictícios.

## 5. Modo acadêmico

Não é necessária aprovação externa para executar o aplicativo. Para inserir nova referência, conferir a bula específica, registrar contexto e limites em `anvisa/regras_clinicas.json` com `status: "documentada"` e metadados completos. Sem isso o sistema continuará exibindo “Posologia não verificada”. A análise não autoriza uso clínico.
