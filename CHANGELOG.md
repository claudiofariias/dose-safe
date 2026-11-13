# Changelog

## 1.9.0 — 13/11/2026 (triagem independente de indicação e indicações padronizadas)

- Campo **Indicação clínica** transformado em seleção, com opções contextuais para medicamentos e faixa etária; elimina erros de digitação nas indicações de dor/febre, tanto para adultos quanto pediatria.
- Para as apresentações com limites numéricos documentados, **excesso de dose ou frequência** é sinalizado mesmo se a indicação estiver ausente ou fora da referência de dor/febre. O bloqueio é reforçado pelo backend (HTTP 409).
- A indicação ainda é necessária para a **comparação orientativa completa**. Valores numéricos dentro do teto, quando a indicação não se aplica, permanecem com `NAO_VERIFICADA`.
- Corrigido aviso pediátrico genérico indevido para soluções orais de dipirona 50 mg/mL e paracetamol 200 mg/mL, quando a faixa etária admite referência orientativa.
- Testes de regressão para limites adultos e pediátricos, ausência de indicação e gravação bloqueada.


## 1.8.0 — 12/11/2026 (UX, segurança de prescrição e pacote TCC)

- Tela de prescrição simplificada, com menos repetições e ações de confirmação visíveis; triagem preliminar perto da seleção, antes do formulário de posologia.
- Contador de medicamentos selecionados; controle de quantidade acessível com **− à esquerda** e **+ à direita**, além de entrada numérica; busca sem acentos e limite de 30 medicamentos.
- Validação final automática após preenchimento, com revisão explícita para riscos leves ou moderados; informações de cobertura e pendências recolhidas por padrão.
- Alertas **grave/contraindicado** bloqueiam salvar também no backend, independentemente de `reviewed` ou justificativa. Pendências de alergia não investigada podem ser ocultadas **temporariamente** na tela de alertas; alergia incompatível permanece impeditiva.
- Remoção de botões demonstrativos sem ação (login social, recuperação fictícia, atalhos de perfil) e assets sem uso; manutenção das páginas realmente funcionais.
- Testes de bloqueio por alergia de classe, interação grave e revisão obrigatória de alerta moderado; documentação e instruções de migração de banco atualizadas.
- Pacote ZIP sem banco de usuários, caches Python ou arquivos transitórios.

## 1.7.0 — 12/11/2026 (auditoria geral)

### Segurança
- **Corrigido vazamento entre usuários:** `GET /api/adherence` não conferia o dono do paciente;
  qualquer usuário logado lia a adesão de qualquer paciente. `POST` agora também valida a
  prescrição informada (precisa pertencer ao paciente).
- Limite de tentativas de login (5 falhas/15 min por e-mail+IP → HTTP 429) e tempo de resposta
  uniforme para e-mail inexistente.
- Cabeçalhos de segurança também nos arquivos estáticos (CSP, `X-Frame-Options`, HSTS em produção);
  removido `Clear-Site-Data` enviado a cada carregamento; cache curto para imagens/bibliotecas.
- Produção não semeia mais pacientes demonstrativos.
- Aviso ao expor o modo demonstração fora do localhost; timeout de conexão (30 s).

### Robustez (antes retornavam HTTP 500)
- ID não numérico na URL; corpo JSON que não é objeto; pacientes com peso/data/medicamentos inválidos
  (que depois quebravam toda análise do paciente); cadastro de medicamento sem `source_version`.
- Validação de paciente, cadastro de usuário (e-mail, tamanhos), adesão e regras de interação (gravidade).
- Idade nunca negativa para data de nascimento futura.
- Versões de prescrição protegidas contra gravação simultânea (`BEGIN IMMEDIATE` + índice único).
- Índices no SQLite e `busy_timeout` de 10 s.

### Lógica clínica
- Alergias comparadas sem acento/caixa, por princípio ativo, marca **e classe** do catálogo
  (alergia a "Penicilina" agora alerta Amoxicilina); sinônimo AAS/aspirina; termos < 3 letras ignorados.
- Condições por palavra inteira: "primária" não aciona mais *renal* ("rim"), "adrenal" não aciona
  *renal*, "gravidade" não aciona *gravidez*; adicionados IRC/DRC, "gestante", "gestacional".
- Interações e duplicidade comparadas sem acento/caixa. Busca de medicamentos ignora acentos.
- Administração: gravidade válida e par de medicamentos único.

### Arquitetura
- `server.py` (1.149 linhas) dividido em `config`, `common`, `security`, `validators`, `analysis`
  e `server`, sem alterar rotas, banco ou respostas (verificado por comparação de 1.056 respostas).

### Manutenção
- `ATUALIZAR_ANVISA.sh/.bat` chamavam `anvisa/revisao_humana.py` (removido): corrigidos.
- Referências a `GUIA_REVISAO_CLINICA.md` (inexistente) apontam para `GUIA_ANVISA.md`.
- Novos testes em `tests/` (31), `.gitignore`, `README.md`; `__pycache__` removido do pacote.
