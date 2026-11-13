# Dose Safe 1.9.0 — protótipo acadêmico (TCC)

Aplicação local de apoio **educacional** à elaboração e à análise determinística de prescrições. Contém cadastro de pacientes, catálogo de 100 medicamentos, triagem preliminar de alergias/interações/condições, posologia por apresentação, cálculo aritmético da dispensação quando possível, análise final automática, histórico e PDF acadêmico.

**Limite obrigatório:** não é dispositivo médico, não está clinicamente validado, não autoriza prescrição real e não substitui avaliação profissional. Ausência de alerta significa apenas que **nenhuma regra cadastrada identificou risco**, não que a associação ou dose seja segura.

## Iniciar no Linux, macOS ou Windows

Requer **Python 3.10 ou superior**. Não exige `npm`, bibliotecas Python externas, compilação ou internet para a execução local.

```bash
cd dose-safe
python3 server.py
```

No navegador, acesse **http://localhost:8000**. No Windows, use `py server.py` caso `python3` não esteja disponível.

**Acesso demonstrativo** (somente quando o modo produção está desativado):

- E-mail: `claudio@dosesafe.local`
- Senha: `DoseSafe123!`

Na primeira execução, o SQLite é criado automaticamente em `dose_safe.db`, com dados **fictícios** no modo demonstrativo.

### Preservar dados de uma versão anterior

Se tiver pacientes ou prescrições próprios, pare o servidor, **faça uma cópia de segurança** de `dose_safe.db` e copie esse arquivo para a nova pasta `dose-safe/` antes de iniciar. O ZIP **não inclui o banco preexistente** para evitar distribuição de informações pessoais ou sobrescrita acidental.

Configurações úteis: `DOSE_SAFE_DB_PATH`, `DOSE_SAFE_PORT` ou `PORT`, `DOSE_SAFE_HOST`. Em produção, `DOSE_SAFE_PRODUCTION=1` exige `DOSE_SAFE_ADMIN_EMAIL` e `DOSE_SAFE_ADMIN_PASSWORD` (12+ caracteres), habilita cookies seguros e HSTS e não popula dados de demonstração. Para uso em rede, implante atrás de HTTPS e revise o ambiente e a segurança operacional; este pacote não é certificação para produção clínica.

## Prescrição e alertas

1. Escolha o paciente e busque medicamentos pelo princípio ativo ou nome comercial. O contador indica quantos foram adicionados (máximo de 30).
2. A **triagem preliminar** avalia medicamentos e informações cadastrais antes do preenchimento da posologia.
3. Informe apresentação, concentração, **quantidade usando os botões − / +**, frequência, duração e dispensação. A **indicação clínica é selecionada em lista**, evitando divergências de grafia; as opções dependem do medicamento, e “Outra indicação” não ativa uma referência incompatível.
4. Quando os dados necessários estão completos, a **análise final é executada automaticamente**. Para as apresentações com teto documentado, uma dose acima do limite é sinalizada mesmo sem indicação selecionada, desde que os dados necessários ao limite estejam presentes. Sem indicação compatível, valores dentro do teto permanecem **não verificados**; não há liberação clínica por ausência de alerta. O botão **Analisar segurança** permite uma revisão explícita.
5. **Grave/contraindicado:** a confirmação fica bloqueada na interface **e na API** (não pode ser burlada por `reviewed=true`). **Moderado/leve:** exige clique em **Revisar alertas** antes de confirmar. **Pendência informativa**, como *alergias não investigadas*, aparece recolhida e não equivale a contraindicação; pode ser ocultada temporariamente apenas na tela de alertas, sem apagar o registro ou modificar a análise.

O app mantém os avisos de cobertura, mas evita duplicá-los entre triagem e resultado final. A janela de sucesso é exibida sobre a página, sem depender do posicionamento da rolagem.

## Cobertura e rastreabilidade

| Item | Situação nesta versão |
|---|---|
| Catálogo de medicamentos | 100 medicamentos genéricos inventariados |
| Interações medicamentosas de referência | 23 pares cadastrados |
| Grupos de condições clínicas | 5 grupos de regras/alertas |
| Posologia | 5 apresentações com referências documentais; 3 possuem comparação orientativa automática (dipirona comprimido 500 mg, dipirona solução oral 50 mg/mL e paracetamol solução oral 200 mg/mL) |
| Regras clínicas provenientes de revisão de bulas Anvisa | 0 ativadas em `anvisa/regras_clinicas.json` |

O projeto possui documentação, inventário e rascunhos de revisão em `anvisa/`. **Rascunho, candidato de registro e comparação orientativa não equivalem a validação clínica.** Uma referência individual de cálculo por peso de losartana, dependente de critérios clínicos explícitos, é descrita em `REGRAS_CALCULO_POR_PESO.md`.

## Testes

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s anvisa -p 'test_*.py' -v
```

Também é possível verificar a sintaxe dos arquivos JavaScript com `node --check` (Node.js é opcional, apenas para desenvolvimento/teste).

## Estrutura

- `server.py`: API HTTP, SQLite, migração/inicialização, endpoints e arquivos estáticos.
- `config.py`, `common.py`, `security.py`, `validators.py`: configuração, segurança e validações.
- `analysis.py`, `clinical_rules.py`, `dose_reference_screening.py`: avaliação de interações, condições e referências.
- `receipt_pdf.py`: PDF acadêmico sem dependências externas.
- `catalog_100.json`, `interaction_examples.json`, `condition_rules.json`: dados de demonstração do motor de triagem.
- `frontend/dist/`: SPA React servida diretamente pelo backend; não há etapa de build.
- `anvisa/`: evidências, documentação, rascunhos, testes e ferramenta de sincronização.
- `tests/`: testes automatizados do backend.

Histórico das alterações em `CHANGELOG.md`. Orientações de revisão de evidências em `anvisa/GUIA_ANVISA.md`.
