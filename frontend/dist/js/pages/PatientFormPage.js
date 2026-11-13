import { AppShell } from '../components/AppShell.js';
import { api } from '../services/api.js';

const h = React.createElement;
const CONDITIONS = ['Diabetes', 'Doença renal', 'Hipertensão', 'Gestação', 'Asma', 'Insuficiência cardíaca', 'Doença hepática', 'Úlcera gástrica', 'Epilepsia', 'Doença cardiovascular'];
const COMMON_ALLERGIES = ['Dipirona', 'Ibuprofeno', 'Amoxicilina', 'Penicilina', 'Ácido acetilsalicílico', 'Paracetamol'];
const clean = value => String(value || '').trim();
const addUnique = (items, value) => {
  const name = clean(value);
  return name && !items.some(item => item.toLocaleLowerCase('pt-BR') === name.toLocaleLowerCase('pt-BR')) ? [...items, name] : items;
};

export class PatientFormPage extends React.Component {
  constructor(props) {
    super(props);
    const patient = props.editPatient || null;
    this.state = {
      name: patient?.name || '', birthDate: patient?.birth_date || '', sex: patient?.sex || 'Feminino',
      weightKg: patient?.weight_kg ?? '', weightDate: patient?.weight_date || '',
      allergies: [...(patient?.allergies || [])], conditions: [...(patient?.conditions || [])],
      activeMedications: [...(patient?.active_medications || [])],
      allergyInput: '', conditionInput: '', allergyStatus: patient?.allergy_status || (patient?.allergies?.length ? 'informada' : 'nao_informada'),
      busy: false
    };
  }
  updateList = (field, name) => this.setState(prev => ({ [field]: addUnique(prev[field], name), ...(field === 'allergies' ? { allergyStatus: 'informada', allergyInput: '' } : { conditionInput: '' }) }));
  removeList = (field, name) => this.setState(prev => ({ [field]: prev[field].filter(value => value !== name) }));
  handleSubmit = async event => {
    event.preventDefault();
    if (this.state.allergyInput.trim() || this.state.conditionInput.trim()) {
      this.props.onToast('Clique em Adicionar para registrar os campos de texto pendentes.', true); return;
    }
    if (this.state.allergyStatus === 'informada' && !this.state.allergies.length) {
      this.props.onToast('Informe a alergia ou selecione outra situação.', true); return;
    }
    this.setState({ busy: true });
    try {
      const body = {
        name: this.state.name.trim(), birth_date: this.state.birthDate || null, sex: this.state.sex,
        weight_kg: this.state.weightKg === '' ? null : Number(this.state.weightKg),
        weight_date: this.state.weightDate || null, allergies: this.state.allergies,
        conditions: this.state.conditions, allergy_status: this.state.allergyStatus, active_medications: this.state.activeMedications
      };
      if (this.props.editPatient) {
        await api(`/api/patients/${this.props.editPatient.id}`, { method: 'PUT', body });
        const response = await api('/api/patients');
        const updated = response.patients.find(p => p.id === this.props.editPatient.id);
        this.props.onUpdated(updated, response.patients);
        this.props.onToast('Ficha clínica atualizada.');
      } else {
        const response = await api('/api/patients', { method: 'POST', body });
        this.props.onToast('Paciente cadastrado com ficha clínica.');
        this.props.onCreated(response.patient);
      }
    } catch (error) { this.props.onToast(error.message, true); }
    finally { this.setState({ busy: false }); }
  };
  renderTags(field, empty) {
    const values = this.state[field];
    return h('div', { className: 'clinical-tags', 'aria-live': 'polite' }, values.length ? values.map(value =>
      h('span', { className: `clinical-tag ${field === 'allergies' ? 'clinical-tag-danger' : ''}`, key: value },
        value, h('button', { type: 'button', 'aria-label': `Remover ${value}`, onClick: () => this.removeList(field, value) }, '×')))
      : h('span', { className: 'clinical-empty' }, empty));
  }
  render() {
    const meds = this.props.medications || [];
    const availableAllergies = [...new Set([...COMMON_ALLERGIES, ...meds.map(m => m.generic_name)])];
    const suggestions = availableAllergies.filter(a => this.state.allergyInput && a.toLocaleLowerCase('pt-BR').includes(this.state.allergyInput.toLocaleLowerCase('pt-BR')) && !this.state.allergies.includes(a)).slice(0, 7);
    const isEdit = Boolean(this.props.editPatient);
    return h(AppShell, { route: this.props.route, onNavigate: this.props.onNavigate, tall: true },
      h('div', { className: 'form-screen clinical-form-screen' },
        h('button', { className: 'back', type: 'button', onClick: () => this.props.onNavigate(isEdit ? 'patientDetail' : 'patients') }, '‹'),
        h('h1', { className: 'title patient-form-title' }, isEdit ? 'Editar ficha do paciente' : 'Cadastrar paciente'),
        h('p', { className: 'clinical-intro' }, 'Preencha a ficha clínica para apoiar a conferência de alergias e condições durante a prescrição.'),
        h('form', { className: 'card form-card stack', onSubmit: this.handleSubmit },
          h('div', { className: 'clinical-section-title' }, h('span', { className: 'clinical-step' }, '01'), h('strong', null, 'Identificação')),
          h('div', null, h('label', { className: 'label', htmlFor: 'patient-name' }, 'Nome completo'), h('input', { id: 'patient-name', className: 'input', required: true, value: this.state.name, onChange: e => this.setState({ name: e.target.value }), placeholder: 'Nome do paciente' })),
          h('div', { className: 'clinical-two-cols' },
            h('div', null, h('label', { className: 'label' }, 'Data de nascimento'), h('input', { className: 'input', type: 'date', value: this.state.birthDate, onChange: e => this.setState({ birthDate: e.target.value }) })),
            h('div', null, h('label', { className: 'label' }, 'Sexo'), h('select', { className: 'select', value: this.state.sex, onChange: e => this.setState({ sex: e.target.value }) }, ['Feminino','Masculino','Outro'].map(v => h('option', { key: v }, v))))),
          h('div', { className: 'clinical-two-cols' },
            h('div', null, h('label', { className: 'label' }, 'Peso (kg)'), h('input', { className: 'input', type: 'number', min: '0.1', step: '0.1', value: this.state.weightKg, onChange: e => this.setState({ weightKg: e.target.value }) })),
            h('div', null, h('label', { className: 'label' }, 'Data da medição'), h('input', { className: 'input', type: 'date', value: this.state.weightDate, onChange: e => this.setState({ weightDate: e.target.value }) }))),
          h('div', { className: 'clinical-section-title' }, h('span', { className: 'clinical-step' }, '02'), h('strong', null, 'Condições preexistentes')),
          h('p', { className: 'clinical-help' }, 'Marque as condições diagnosticadas. Não selecione uma condição apenas por suspeita.'),
          h('div', { className: 'clinical-check-grid' }, CONDITIONS.map(condition => h('label', { className: 'clinical-check', key: condition },
            h('input', { type: 'checkbox', checked: this.state.conditions.includes(condition), onChange: e => e.target.checked ? this.updateList('conditions', condition) : this.removeList('conditions', condition) }), h('span', null, condition)))),
          h('div', { className: 'clinical-add-row' },
            h('input', { className: 'input', value: this.state.conditionInput, placeholder: 'Outra condição diagnosticada', 'aria-label': 'Outra condição', onChange: e => this.setState({ conditionInput: e.target.value }), onKeyDown: e => { if (e.key === 'Enter') { e.preventDefault(); this.updateList('conditions', this.state.conditionInput); } } }),
            h('button', { className: 'btn btn-outline', type: 'button', onClick: () => this.updateList('conditions', this.state.conditionInput) }, 'Adicionar')),
          this.renderTags('conditions', 'Nenhuma condição registrada — confirme a anamnese.'),
          h('div', { className: 'clinical-section-title' }, h('span', { className: 'clinical-step' }, '03'), h('strong', null, 'Alergias medicamentosas')),
          h('p', { className: 'clinical-help' }, 'Registre o nome do medicamento ou substância que causou reação. Alergia e efeito colateral não são equivalentes.'),
          h('div', { className: 'clinical-radio-grid' },
            [['nao_informada','Não investigado'],['nenhuma','Paciente nega alergias conhecidas'],['informada','Alergia informada']].map(([value,label]) => h('label', { key: value, className: 'clinical-radio' },
              h('input', { type: 'radio', name: 'allergy-status', checked: this.state.allergyStatus === value, onChange: () => this.setState({ allergyStatus: value, allergies: value === 'informada' ? this.state.allergies : [] }) }), label))),
          this.state.allergyStatus === 'informada' ? h('div', null,
            h('div', { className: 'clinical-add-row' },
              h('input', { className: 'input', value: this.state.allergyInput, placeholder: 'Buscar medicamento ou digitar outra alergia', 'aria-label': 'Alergia', onChange: e => this.setState({ allergyInput: e.target.value }), onKeyDown: e => { if (e.key === 'Enter') { e.preventDefault(); this.updateList('allergies', this.state.allergyInput); } } }),
              h('button', { className: 'btn btn-outline', type: 'button', onClick: () => this.updateList('allergies', this.state.allergyInput) }, 'Adicionar')),
            Boolean(suggestions.length) && h('div', { className: 'clinical-suggestions' }, suggestions.map(value => h('button', { type: 'button', key: value, onClick: () => this.updateList('allergies', value) }, '+ ', value))),
            this.renderTags('allergies', 'Informe ao menos uma alergia, ou altere a situação acima.')) :
            h('p', { className: 'clinical-help' }, this.state.allergyStatus === 'nenhuma' ? 'Registro de ausência relatada, não garantia de ausência de alergias.' : 'Situação desconhecida: a checagem de alergias não pode ser considerada completa.'),
          h('div', { className: 'clinical-section-title' }, h('span', { className: 'clinical-step' }, '04'), h('strong', null, 'Medicamentos em uso')),
          h('p', { className: 'clinical-help' }, 'Selecione os medicamentos que o paciente usa atualmente para incluí-los na análise.'),
          h('select', { className: 'select', multiple: true, size: 6, value: this.state.activeMedications.map(String), onChange: e => this.setState({ activeMedications: Array.from(e.target.selectedOptions, option => Number(option.value)) }) }, meds.map(m => h('option', { key: m.id, value: m.id }, m.generic_name, m.brand_name ? ` — ${m.brand_name}` : ''))),
          h('div', { className: 'clinical-section-title' }, h('span', { className: 'clinical-step' }, '✓'), h('strong', null, 'Resumo da ficha clínica')),
          h('div', { className: 'clinical-preview' },
            h('strong', null, this.state.name || 'Paciente ainda não identificado'),
            h('div', null, 'Condições: ', this.state.conditions.join(', ') || 'Não registradas'),
            h('div', null, 'Alergias: ', this.state.allergies.join(', ') || (this.state.allergyStatus === 'nenhuma' ? 'Nega alergias conhecidas' : 'Não informadas')),
            h('div', null, 'Medicamentos em uso: ', this.state.activeMedications.length, ' selecionado(s)')),
          h('p', { className: 'clinical-disclaimer' }, 'As informações são utilizadas como apoio à análise, mas a ausência de alertas não comprova segurança clínica.'),
          h('button', { className: 'btn btn-primary btn-full patient-submit', type: 'submit', disabled: this.state.busy }, this.state.busy ? 'Salvando...' : isEdit ? 'Salvar alterações' : 'Confirmar paciente')
        )
      )
    );
  }
}
