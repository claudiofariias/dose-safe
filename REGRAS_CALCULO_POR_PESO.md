# Cálculo por peso — regras documentadas (protótipo acadêmico)

- Não existe cálculo mg/kg geral aplicado à receita. A dose de cada medicamento é informada individualmente.
- Exemplo de referência individual disponível: **losartana**, *hipertensão pediátrica*, pacientes de **6 a 17 anos**.
- Bula DailyMed, seção 2.1: **0,7 mg/kg uma vez ao dia** como referência inicial, **até 50 mg** na dose inicial; não recomendada para menores de 6 anos ou TFGe < 30 mL/min/1,73m².
- Fonte: https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=c565e7ba-97aa-4a65-80e6-543e9af6e1c4
- O profissional informa a TFGe e confirma a indicação antes de consultar a referência. O resultado **não altera o formulário da prescrição**, **não seleciona comprimidos** e **não prova segurança**.
- Para os outros 99 medicamentos, não há calculadora genérica ativada. São necessárias regras por medicamento, indicação e grupo etário previamente fundamentadas e testadas.
- Uso acadêmico demonstrativo. Não utilizar em decisões clínicas reais.

## Seleção do modo na tela de prescrição
- Crianças abaixo de 12 anos: identificação visual de paciente pediátrico, com peso informado quando existente; não presume cálculo geral de dose.
- Adolescentes de 12 a 17 anos: aviso específico para conferir restrições etárias; a referência individual de losartana continua acessível entre 6 e 17 anos se os critérios forem cumpridos.
- A única referência mg/kg atualmente implementada é a de losartana em hipertensão pediátrica (6–17 anos), sujeita aos critérios descritos acima.
- Outros medicamentos pediátricos: o sistema informa ausência de regra validada, sem inventar doses ou calcular automaticamente.
- Adultos (18 anos ou mais): posologia por apresentação, concentração, quantidade, frequência e duração; sem cálculo mg/kg geral.
- Idade não informada: exibe solicitação de conferência cadastral, sem inferir grupo etário.
