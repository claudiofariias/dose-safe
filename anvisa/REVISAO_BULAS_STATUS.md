# Dose Safe — revisão de evidências farmacológicas (11/11/2026)

## Resultado

- **100 medicamentos** continuam no catálogo.
- **2 medicamentos** têm documentação de referência identificada e dados organizados para **pré-documentação técnica**: Dipirona e Paracetamol.
- **0 novas referências posológicas documentadas e ativadas**. `anvisa/regras_clinicas.json` continua `[]`.
- Os demais **98 medicamentos** aguardam bula do profissional selecionada, produto e concentração identificados.
- Interações e condições clínicas preexistentes permanecem acadêmicas/parciais, sem mudança de status.

## Fontes e confiabilidade

### Dipirona solução oral 50 mg/mL

Bula de paciente **publicada pela Aché (titular)**, registro `1.0573.0622` encontrado no CSV do usuário como `105730622` ativo. Tabela pediátrica estratificada por peso e limites diários transcritos em `anvisa/evidencias_curadas.json` para conferência. **Falta bula profissional exata**; não foi cadastrada como regra ativa. A tabela usa peso, e idade entre parênteses é apenas idade média, não regra exclusiva.

Fonte: https://www.ache.com.br/wp-content/uploads/application/pdf/bula-paciente-dipirona-monoidratada-solucao-oral.pdf (página 2, Posologia). Publicação do arquivo indica 06/2024; consultar a versão mais recente antes de cadastrar referências.

### Paracetamol solução oral 200 mg/mL

A **IN nº 106/2021 da Anvisa, com alterações posteriores incluindo IN nº 430/2026**, contém parâmetros de dose para a apresentação 200 mg/mL. Referência **regulatória genérica**, não bula do produto. Dados organizados em `evidencias_curadas.json`. **Não cabe ativar regra sem bula profissional e vínculo de registro específico.**

Fonte: https://anvisalegis-empresa.datalegis.net/action/ActionDatalegis.php?acao=detalharAto&cod_menu=8542&cod_modulo=310&desItem=&desItemFim=&nomeTitulo=codigos&numeroAto=00000106&orgao=DC%2FANVISA%2FMS&seqAto=000&tipo=INM&valorAno=2021

## Próxima etapa documental (opcional no protótipo)

Para cadastrar referência posológica no motor, é necessário escolher uma bula profissional específica, identificar registro do produto, conferir concentração/apresentação, idade, peso, indicação e via, e transcrever limites explicitamente documentados, acompanhados de URL, seção, página, hash do PDF e data de registro. **Não existe etapa de aprovação profissional no aplicativo.** Campos ausentes devem permanecer não verificados; o cadastro acadêmico não comprova segurança da prescrição.

O algoritmo é determinístico. Não há IA generativa rodando no sistema nem aprovação por IA. **Não aplicar dados da pré-revisão diretamente a pacientes.**

## Segurança do pareamento

O cruzamento CSV agora coloca candidatos com suspeita de **associação de princípios ativos** depois dos registros aparentemente monofármacos, marcando `suspeita_associacao` para revisão. Exemplo: `MIORRELAX` não pode ser aceito como Dipirona isolada apenas porque contém dipirona na composição. Pareamento textual não substitui comprovação de composição, registro e bula.
