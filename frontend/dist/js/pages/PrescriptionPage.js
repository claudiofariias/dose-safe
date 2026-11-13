import { countWord } from '../utils/alertText.js';
import { ClinicalAlertSummary } from '../components/ClinicalAlertSummary.js';
import { AppShell } from '../components/AppShell.js';
import { Modal } from '../components/Modal.js';
import { api } from '../services/api.js';
import { initials } from '../utils/format.js';
const FREQUENCIES = ['4/4h', '6/6h', '8/8h', '12/12h', '24/24h', '1x pela manhã', '1x à noite', '2x ao dia', '1x por semana', 'dose única'];

// Valores fechados evitam erros de digitação e mantêm a escolha como indicação
// informada pelo usuário, nunca como recomendação terapêutica do sistema.
function indicationOptions(medication, patient) {
    const name = String(medication?.generic_name || '').normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '').toLowerCase();
    const age = Number(patient?.age);
    const empty = {value:'', label:'Selecione a indicação (opcional)'};
    const other = {value:'outra', label:'Outra indicação / não contemplada'};
    const painFever = [{value:'febre', label:'Febre'}, {value:'dor', label:'Dor'}];
    if (/dipirona|paracetamol/.test(name))
        return [empty, ...painFever, other];
    if (/ibuprofeno|naproxeno|diclofenaco/.test(name))
        return [empty, ...painFever, {value:'inflamacao', label:'Inflamação'}, other];
    if (/losartana|losartan|anlodipino|amlodipino|enalapril|lisinopril|valsartana/.test(name))
        return [empty, {value:'hipertensao', label:'Hipertensão'},
            ...(Number.isFinite(age) && age >= 6 && age <= 17 && /losartana|losartan/.test(name)
                ? [{value:'hipertensao_pediatrica', label:'Hipertensão pediátrica'}] : []), other];
    if (/amoxicilina|azitromicina|claritromicina|cefalexina|cefuroxima|ceftriaxona|doxiciclina|levofloxacino/.test(name))
        return [empty, {value:'infeccao_bacteriana', label:'Infecção bacteriana'}, other];
    return [empty, ...painFever,
        {value:'infeccao_bacteriana', label:'Infecção bacteriana'},
        {value:'hipertensao', label:'Hipertensão'},
        {value:'diabetes', label:'Diabetes'},
        {value:'inflamacao', label:'Inflamação'},
        {value:'alergia', label:'Alergia'},
        {value:'convulsoes', label:'Convulsões'}, other];
}
function hasPediatricPosologyReference(medication, item, patient) {
    const name = String(medication?.generic_name || '').normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '').toLowerCase();
    const age = Number(patient?.age);
    if (item.route !== 'oral' || item.form_kind !== 'liquid' || item.strength_unit !== 'mg/mL') return false;
    if (!Number.isFinite(age) || !Number.isFinite(Number(item.strength_value))) return false;
    return (name.includes('dipirona') && Number(item.strength_value) === 50 && age >= 1 && age < 16) ||
        (name.includes('paracetamol') && Number(item.strength_value) === 200 && age >= 2 && age < 12);
}

// Quantidade dispensada: calcular somente quando a unidade por dose coincide
// com a unidade de dispensação e a frequência/duração são determinísticas.
const DAILY_FREQUENCY = {'4/4h':6,'6/6h':4,'8/8h':3,'12/12h':2,'24/24h':1,
    '1x pela manhã':1,'1x à noite':1,'2x ao dia':2};
function totalAdministrations(item) {
    if (item.frequency === 'dose única' && item.duration_mode === 'single') return 1;
    if (item.duration_mode !== 'days') return null;
    const days = Number(item.duration_days);
    if (!Number.isInteger(days) || days < 1) return null;
    if (DAILY_FREQUENCY[item.frequency]) return days * DAILY_FREQUENCY[item.frequency];
    if (item.frequency === '1x por semana' && days % 7 === 0) return days / 7;
    return null;
}
function requiredLiquidVolume(item) {
    if (item.form_kind !== 'liquid' || item.dose_unit !== 'mL') return null;
    const dose = Number(item.dose_quantity);
    const administrations = totalAdministrations(item);
    if (!Number.isFinite(dose) || dose <= 0 || administrations === null) return null;
    return Math.round(dose * administrations * 100000) / 100000;
}
function calculatedDispense(item) {
    const dose = Number(item.dose_quantity);
    const administrations = totalAdministrations(item);
    if (!Number.isFinite(dose) || dose <= 0 || administrations === null) return null;
    let result;
    if (item.form_kind === 'liquid' && item.dose_unit === 'mL' && item.dispense_unit === 'frasco(s)') {
        const volume = Number(item.bottle_volume_ml);
        if (!Number.isFinite(volume) || volume <= 0 || volume > 10000) return null;
        result = Math.ceil((dose * administrations) / volume - 1e-10);
    } else {
        if (item.dose_unit !== item.dispense_unit) return null;
        result = Math.round(dose * administrations * 100000) / 100000;
    }
    return result > 0 && result <= 100000 ? result : null;
}
function itemMissingFields(item) {
    const missing = [];
    if (!Number.isFinite(Number(item.strength_value)) || Number(item.strength_value) <= 0) missing.push('concentração');
    if (!Number.isFinite(Number(item.dose_quantity)) || Number(item.dose_quantity) <= 0) missing.push('quantidade por administração');
    if (!item.frequency) missing.push('frequência');
    if (item.duration_mode === 'days' && !(Number(item.duration_days)>0)) missing.push('número de dias');
    if (item.duration_mode === 'months' && !(Number(item.duration_months)>0)) missing.push('número de meses');
    const validDispense = Number(item.dispense_quantity)>0 && String(item.dispense_quantity||'').trim() !== '';
    if (!validDispense) missing.push('total a dispensar');
    if (validDispense && item.dispense_mode === 'manual' && calculatedDispense(item) !== null &&
        Number(item.dispense_quantity) !== calculatedDispense(item) && String(item.dispense_reason||'').trim().length < 5)
        missing.push('motivo do ajuste');
    return missing;
}
function applyDispense(item) {
    const expected = calculatedDispense(item);
    if (item.dispense_mode !== 'manual') return {...item, dispense_mode:'auto',
        dispense_quantity: expected === null ? '' : String(expected), dispense_reason:''};
    return item;
}
export class PrescriptionPage extends React.Component {
    componentDidMount() {
        this.scheduleScreen();
        this.scheduleCheck();
    }
    componentWillUnmount() {
        if (this.checkTimer !== null)
            window.clearTimeout(this.checkTimer);
        this.checkSequence++;
        if (this.screenTimer !== null) window.clearTimeout(this.screenTimer);
        this.screenSequence++;
    }
    scheduleScreen() {
        if (this.screenTimer !== null) window.clearTimeout(this.screenTimer);
        this.screenTimer = window.setTimeout(() => this.screenMedications(), 250);
    }
    async screenMedications() {
        const patient = this.patient;
        const ids = this.props.items.map(item => item.medication_id);
        const key = JSON.stringify([patient?.id, ids]);
        const sequence = ++this.screenSequence;
        if (!patient || !ids.length) {
            this.setState({ screening: null, screeningBusy: false, screeningKey: '' });
            return;
        }
        this.setState({ screeningBusy: true, screeningKey: '' });
        try {
            const result = await api('/api/prescriptions/screen', {
                method: 'POST', body: { patient_id: patient.id, medication_ids: ids }
            });
            if (sequence !== this.screenSequence || key !== JSON.stringify([this.patient?.id, this.props.items.map(item => item.medication_id)])) return;
            this.setState({ screening: result, screeningBusy: false, screeningKey: key });
        } catch (error) {
            if (sequence !== this.screenSequence) return;
            this.setState({ screening: null, screeningBusy: false, screeningKey: '' });
            this.props.onToast('Não foi possível fazer a triagem inicial: ' + error.message, true);
        }
    }
    draftKey() {
        var _a;
        return JSON.stringify({ patient: (_a = this.patient) === null || _a === void 0 ? void 0 : _a.id, items: this.normalizedItems() });
    }
    scheduleCheck() {
        if (this.checkTimer !== null)
            window.clearTimeout(this.checkTimer);
        this.checkTimer = window.setTimeout(() => this.autoCheck(), 300);
    }
    async autoCheck() {
        const patient = this.patient;
        const items = this.normalizedItems();
        const key = this.draftKey();
        const sequence = ++this.checkSequence;
        const complete = items.length && items.every(item => itemMissingFields(item).length === 0 && item.presentation && item.duration_mode);
        if (!patient || !complete) {
            this.props.onAnalysis(null);
            this.setState({ checkedKey: '', reviewedKey: '', checking: false });
            return;
        }
        this.setState({ checking: true });
        try {
            const result = await api('/api/prescriptions/analyze', {
                method: 'POST', body: { patient_id: patient.id, items },
            });
            if (sequence !== this.checkSequence || key !== this.draftKey())
                return;
            this.props.onAnalysis(result);
            this.setState({ checkedKey: key, checking: false });
        }
        catch (error) {
            if (sequence !== this.checkSequence)
                return;
            this.props.onAnalysis(null);
            this.setState({ checkedKey: '', checking: false });
            this.props.onToast(`Não foi possível validar a prescrição: ${error.message}`, true);
        }
    }
    hasRisk(analysis) {
        return !!(analysis === null || analysis === void 0 ? void 0 : analysis.alerts.some(alert => ['contraindicado', 'grave', 'moderado', 'leve'].includes(String(alert.severity).toLowerCase())));
    }
    hasBlockingRisk(analysis) {
        return !!(analysis === null || analysis === void 0 ? void 0 : analysis.alerts.some(alert => ['contraindicado', 'grave'].includes(String(alert.severity || '').toLowerCase())));
    }
    constructor(props) {
        super(props);
        this.checkTimer = null;
        this.screenTimer = null;
        this.screenSequence = 0;
        this.checkSequence = 0;
        this.selectPatient = (patientId) => {
            const patient = this.props.patients.find(item => item.id === patientId);
            if (patient) {
                this.props.onSelectPatient(patient);
                this.props.onAnalysis(null);
            }
        };
        this.addMedication = (medication) => {
            if (this.props.items.some(item => item.medication_id === medication.id)) {
                this.props.onToast('Medicamento já adicionado', true);
                return;
            }
            if (this.props.items.length >= 30) {
                this.props.onToast('Limite de 30 medicamentos por prescrição.', true);
                return;
            }
            const initial = presentationOptions(medication)[0];
            const next = this.props.items.concat({
                medication_id: medication.id,
                presentation: initial.id,
                presentation_label: initial.label,
                strength_value: initial.strength,
                strength_unit: initial.strengthUnit,
                form_kind: initial.kind,
                route: initial.route,
                dose_quantity: '',
                dose_unit: initial.doseUnit,
                dispense_quantity: '',
                dispense_mode: 'auto',
                dispense_reason: '',
                dispense_unit: initial.dispenseUnit,
                bottle_volume_ml: '',
                frequency: '',
                duration_mode: 'days',
                duration_days: 3,
                duration_months: 3,
                instruction: '',
                indication: '',
                anvisa_registration: '',
                dose: 0,
                unit: 'mg',
            });
            this.props.onItemsChange(next);
            this.props.onAnalysis(null);
            this.setState({ search: '' }, () => { this.scheduleScreen(); this.scheduleCheck(); });
        };
        this.updateItem = (index, patch) => {
            const next = this.props.items.map((item, itemIndex) => itemIndex === index ? applyDispense({ ...item, ...patch }) : item);
            this.props.onItemsChange(next);
            this.props.onAnalysis(null);
            this.scheduleCheck();
        };
        this.removeItem = (index) => {
            this.props.onItemsChange(this.props.items.filter((_, itemIndex) => itemIndex !== index));
            this.props.onAnalysis(null);
            this.scheduleScreen();
            this.scheduleCheck();
        };
        this.analyze = async () => {
            const patient = this.patient;
            const items = this.normalizedItems();
            if (!patient || !items.length) {
                this.props.onToast('Selecione paciente e preencha todos os campos de posologia de cada medicamento', true);
                return;
            }
            const incomplete = items.map((item, index) => ({index, missing:itemMissingFields(item)})).find(x => x.missing.length);
            if (incomplete) {
                this.props.onToast(`Medicamento ${incomplete.index+1}: preencher ${incomplete.missing.join(', ')}.`, true);
                return;
            }
            const key = this.draftKey();
            this.setState({ busy: true });
            try {
                const result = await api('/api/prescriptions/analyze', {
                    method: 'POST', body: { patient_id: patient.id, items },
                });
                if (key !== this.draftKey())
                    return;
                this.props.onAnalysis(result);
                this.setState({ checkedKey: key, reviewedKey: key });
                this.props.onToast(this.hasBlockingRisk(result)
                    ? 'Contraindicação impeditiva: revise a prescrição antes de continuar.'
                    : 'Análise revisada. Confira os alertas antes de confirmar.', this.hasBlockingRisk(result));
                // Alertas são apresentados nesta tela para manter o botão de confirmação acessível.
            }
            catch (error) {
                this.props.onToast(error.message, true);
            }
            finally {
                this.setState({ busy: false, checking: false });
            }
        };
        this.save = async () => {
            const patient = this.patient;
            const items = this.normalizedItems();
            if (!patient || !items.length) {
                this.props.onToast('Selecione paciente e preencha todos os campos de posologia de cada medicamento', true);
                return;
            }
            this.setState({ busy: true });
            this.props.onItemsChange(items);
            try {
                const key = this.draftKey();
                const analysis = this.props.analysis;
                if (!analysis || this.state.checkedKey !== key || this.state.checking ||
                    (this.hasRisk(analysis) && this.state.reviewedKey !== key)) {
                    this.props.onToast('Validação pendente: revise a análise antes de confirmar.', true);
                    return;
                }
                if (this.hasBlockingRisk(analysis)) {
                    this.props.onToast('Prescrição bloqueada: há contraindicação grave ou impeditiva.', true);
                    return;
                }
                const justification = '';
                const savedResponse = await api('/api/prescriptions', {
                    method: 'POST',
                    body: {
                        patient_id: patient.id,
                        items,
                        justification,
                        reviewed: this.state.reviewedKey === key,
                    },
                });
                this.setState({ saved: true, savedId: savedResponse.id });
            }
            catch (error) {
                this.props.onToast(error.message, true);
            }
            finally {
                this.setState({ busy: false });
            }
        };
        const patient = props.selectedPatient || props.patients[0] || null;
        this.state = {
            search: '',
            patientQuery: '',
            busy: false,
            saved: false,
            savedId: null,
            checking: false,
            reviewedKey: '',
            checkedKey: '',
            screening: null,
            screeningBusy: false,
            screeningKey: '',
        };
    }
    componentDidUpdate(prevProps, prevState) {
        var _a, _b, _d, _e;
        if (((_a = prevProps.selectedPatient) === null || _a === void 0 ? void 0 : _a.id) !== ((_b = this.props.selectedPatient) === null || _b === void 0 ? void 0 : _b.id)) {
            this.scheduleScreen();
        }
        if (((_d = prevProps.selectedPatient) === null || _d === void 0 ? void 0 : _d.id) !== ((_e = this.props.selectedPatient) === null || _e === void 0 ? void 0 : _e.id) ||
            prevProps.items !== this.props.items ||
            (this.state.checkedKey && this.state.checkedKey !== this.draftKey())) {
            this.scheduleCheck();
        }
    }
    get patient() {
        return this.props.selectedPatient || this.props.patients[0] || null;
    }
    normalizedItems() {
        return this.props.items.map(item => applyDispense({ ...item }));
    }
    render() {
        var _a;
        const patient = this.patient;
        const query = this.state.search.trim().normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
        const matches = query
            ? this.props.medications
                .filter(medication => `${medication.generic_name} ${medication.brand_name || ''}`
                .normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase()
                .includes(query))
                .slice(0, 8)
            : [];
        return (React.createElement(AppShell, { route: this.props.route, onNavigate: this.props.onNavigate, tall: true },
            React.createElement("div", { className: "rx" },
                React.createElement("button", { className: "back", type: "button", onClick: () => this.props.onNavigate('dashboard') }, "\u2039"),
                React.createElement("h1", { className: "title" }, "Nova prescri\u00E7\u00E3o"),
                React.createElement("div", { className: "card section" },
                    React.createElement("label", { className: "label" }, "Paciente"),
                    React.createElement('input', {
                        className:'input', type:'search', value:this.state.patientQuery || '',
                        placeholder:'Buscar paciente por nome ou código L-',
                        'aria-label':'Buscar paciente por nome ou código',
                        onChange:event=>this.setState({patientQuery:event.target.value})
                    }),
                    React.createElement('select', {
                        className:'select', value:patient?.id || '',
                        'aria-label':'Selecionar paciente',
                        onChange:event=>{this.selectPatient(Number(event.target.value));this.setState({patientQuery:''});}
                    }, this.props.patients.filter(item=>{
                        const needle=(this.state.patientQuery || '').trim().toLocaleLowerCase('pt-BR');
                        return !needle || `${item.name || ''} ${item.code || ''}`.toLocaleLowerCase('pt-BR').includes(needle) ||
                            String(item.code || '').toLowerCase().replace(/[^a-z0-9]/g,'').includes(needle.replace(/[^a-z0-9]/g,''));
                    }).map(item=>React.createElement('option',{value:item.id,key:item.id},`${item.name} — ${item.code}`))),
                    (this.state.patientQuery || '').trim() && !this.props.patients.some(item=>
                        `${item.name || ''} ${item.code || ''}`.toLowerCase().includes(this.state.patientQuery.trim().toLowerCase()) ||
                        String(item.code || '').toLowerCase().replace(/[^a-z0-9]/g,'').includes(this.state.patientQuery.trim().toLowerCase().replace(/[^a-z0-9]/g,''))) &&
                        React.createElement('small',{className:'rx-dispense-hint'},'Nenhum paciente encontrado.'),
                    patient ? (React.createElement("div", { className: "selected-patient" },
                        React.createElement("div", { className: "miniavatar" }, initials(patient.name)),
                        React.createElement("div", { className: "selected-patient-copy" },
                            React.createElement("strong", null, patient.name),
                            React.createElement("div", { className: 'rx-patient-flag ' + ((patient.allergies || []).length ? 'rx-patient-flag-danger' : patient.allergy_status === 'nenhuma' ? 'rx-patient-flag-neutral' : 'rx-patient-flag-pending') },
                                (patient.allergies || []).length ? `Alergias: ${patient.allergies.join(', ')}` :
                                patient.allergy_status === 'nenhuma' ? 'Nega alergias conhecidas' : 'Alergias não investigadas')),
                        React.createElement("span", null, (_a = patient.age) !== null && _a !== void 0 ? _a : '—',
                            " anos"))) : null,
                    patient && patient.age != null && Number(patient.age)<18 && React.createElement('div', {className:'rx-pediatric-banner'},
                        isPediatricPatient(patient) ?
                            `Paciente pediátrico · ${Number(patient.weight_kg)>0 ? patient.weight_kg+' kg' : 'peso não informado'} · confira referência específica.` :
                            'Paciente adolescente: verifique as restrições etárias da bula.'),
                    patient && React.createElement('details', {className:'clinical-rx-card rx-patient-details'},
                        React.createElement('summary', null, 'Consultar ficha clínica'),
                        React.createElement('div', {className:'clinical-rx-line'},React.createElement('strong',null,'Condições: '),(patient.conditions||[]).join(', ') || 'Não registradas'),
                        React.createElement('div', {className:'clinical-rx-line'},React.createElement('strong',null,'Alergias: '),(patient.allergies||[]).join(', ') || (patient.allergy_status === 'nenhuma'?'Negadas pelo paciente':'Não investigadas')),
                        React.createElement('div', {className:'clinical-rx-line'},React.createElement('strong',null,'Em uso: '),(patient.active_medications||[]).map(id=>this.props.medications.find(m=>m.id===id)?.generic_name).filter(Boolean).join(', ') || 'Não registrados'))),
                React.createElement("div", { className: "card section" },
                    React.createElement("div", {className:'rx-medication-heading'},
                        React.createElement("label", { className: "label" }, "Medicamentos"),
                        React.createElement("span", {className:'rx-medication-count'}, countWord(this.props.items.length,'selecionado','selecionados'))),
                    React.createElement("input", { className: "input", placeholder: "Buscar por princ\u00EDpio ativo ou nome comercial", value: this.state.search, onChange: (event) => this.setState({ search: event.target.value }) }),
                    query ? (React.createElement("div", { className: "search-results" }, matches.length ? (matches.map(medication => (React.createElement("button", { className: "search-item", type: "button", key: medication.id, onClick: () => this.addMedication(medication) },
                        React.createElement("strong", null, medication.generic_name),
                        React.createElement("span", null,
                            medication.brand_name || 'Sem nome comercial',
                            " \u2022 ",
                            medication.form,
                            " \u2022",
                            ' ',
                            medication.route))))) : (React.createElement("div", { className: "search-item" }, "Nenhum resultado")))) : null,
                // Uma triagem antecipada é mostrada enquanto a posologia ainda está sendo preenchida.
                // Quando a análise final estiver disponível, evitamos duplicar os mesmos alertas.
                !(this.props.analysis && this.state.checkedKey === this.draftKey()) && this.props.items.length > 0 &&
                    React.createElement("section", { className: "rx-early-screen rx-early-inline", "aria-label": "Triagem inicial dos medicamentos" },
                        React.createElement("strong", null, "Triagem inicial"),
                        this.state.screeningBusy ? React.createElement("p", {className:'clinical-help',role:'status'},'Verificando medicamentos...') :
                        this.state.screening && this.state.screeningKey === JSON.stringify([patient?.id, this.props.items.map(item=>item.medication_id)]) ?
                        React.createElement(ClinicalAlertSummary, {alerts:this.state.screening.alerts||[]}) :
                        React.createElement("p",{className:'clinical-help'},'Aguardando triagem...'),
                        React.createElement('small',{className:'rx-screen-hint'},'Análise preliminar: não verifica a posologia.')),
                    React.createElement("div", { className: "stack rx-items" }, this.props.items.map((item, index) => (React.createElement(PrescriptionItemCard, { key: `${item.medication_id}-${index}`, item: item, index: index, medication: this.props.medications.find(medication => medication.id === item.medication_id), patient: patient, onChange: this.updateItem, onRemove: this.removeItem }))))),
                (() => {
                    const valid = !!this.props.analysis && this.state.checkedKey === this.draftKey();
                    const analysis = valid ? this.props.analysis : null;
                    const blocking = this.hasBlockingRisk(analysis);
                    const risk = this.hasRisk(analysis);
                    const reviewed = this.state.reviewedKey === this.draftKey();
                    const incomplete = this.normalizedItems().some(item=>itemMissingFields(item).length>0);
                    const disabled = this.state.busy || this.state.checking || !analysis || blocking || (risk && !reviewed);
                    const doseChecks = analysis?.dosage_evaluations || [];
                    const unverified = doseChecks.filter(x=>x.status==='NAO_VERIFICADA').length;
                    const orientative = doseChecks.filter(x=>x.status==='COMPARACAO_ORIENTATIVA').length;
                    return React.createElement('section',{className:'rx-ux-safety','aria-label':'Segurança da prescrição'},
                        React.createElement('div',{className:'rx-ux-heading'},
                            React.createElement('strong',null,'Segurança da prescrição'),
                            analysis && React.createElement('span',{className:'rx-ux-count '+(blocking?'rx-ux-count-danger':risk?'rx-ux-count-warning':'rx-ux-count-info')},
                                blocking?'Bloqueada':risk?'Revisão necessária':'Análise concluída')),
                        this.state.checking ? React.createElement('p',{className:'rx-safety-message',role:'status'},'Analisando prescrição...') :
                        analysis ? React.createElement('div',{className:'rx-ux-alert-list'},
                            React.createElement(ClinicalAlertSummary,{alerts:analysis.alerts||[]}),
                            doseChecks.length>0 && React.createElement('details',{className:'rx-dose-details'},
                                React.createElement('summary',null,'Cobertura de posologia',
                                    React.createElement('span',null,`${orientative} orientativa(s) · ${unverified} não verificada(s)`)),
                                React.createElement('p',null,'As referências são limitadas à apresentação e indicação; não atestam segurança da dose.')),
                            blocking && React.createElement('div',{className:'rx-ux-status rx-ux-status-danger',role:'alert'},
                                'Alerta grave ou contraindicação: ajuste a prescrição.'),
                            risk && !blocking && !reviewed && React.createElement('div',{className:'rx-ux-status rx-ux-status-warning',role:'status'},
                                'Revise os alertas para liberar a confirmação.')) :
                        React.createElement('p',{className:'rx-safety-message',role:'status'},
                            !patient ? 'Selecione um paciente.' : !this.props.items.length ? 'Adicione um medicamento.' :
                            incomplete ? 'Preencha a posologia para concluir a análise.' : 'Análise pendente.'),
                        React.createElement('button',{className:analysis&&!risk?'btn btn-outline btn-full rx-review-button':'btn btn-primary btn-full rx-review-button',
                            type:'button',onClick:this.analyze,disabled:this.state.busy||this.state.checking||!patient||!this.props.items.length},
                            this.state.busy?'Analisando...':analysis&&!risk?'Analisar novamente':risk&&!reviewed?'Revisar alertas':'Analisar segurança'),
                        React.createElement('button',{className:'btn btn-primary btn-full confirm-prescription rx-ux-confirm',
                            type:'button',onClick:this.save,disabled},
                            this.state.busy?'Processando...':blocking?'Confirmação bloqueada':'Confirmar prescrição'),
                        React.createElement('small',{className:'rx-academic-note'},
                            'Protótipo acadêmico: ausência de alerta não comprova segurança clínica.'));
                })()),
            this.state.saved ? (React.createElement(Modal, { title: "Prescri\u00E7\u00E3o criada com sucesso!", onClose: () => {
                    this.setState({ saved: false });
                    this.props.onNavigate('dashboard');
                } },
                React.createElement("div", { className: "notice" }, "Documento acadêmico — sem validade como receita médica."),
                React.createElement("button", { className: "btn btn-primary btn-full modal-primary", type: "button", onClick: () => window.open(`/api/prescriptions/${this.state.savedId}/pdf`, '_blank'), disabled: !this.state.savedId }, "Baixar receita PDF"),
                React.createElement("button", { className: "btn btn-outline btn-full modal-primary", type: "button", onClick: () => this.props.onNavigate('history') }, "Ver histórico"))) : null));
    }
}
// As opções demonstram apresentações, não doses ou condutas recomendadas.
function presentationOptions(med) {
    const name = (med && med.generic_name || '').toLowerCase();
    if (name.includes('dipirona')) return [
        {id:'dip-tab-500', label:'Comprimido • 500 mg',kind:'tablet',strength:500,strengthUnit:'mg',doseUnit:'comprimido(s)',dispenseUnit:'comprimido(s)',route:'oral'},
        {id:'dip-inj-500', label:'Solução injetável • 500 mg/mL',kind:'ampoule',strength:500,strengthUnit:'mg/mL',doseUnit:'ampola(s)',dispenseUnit:'ampola(s)',route:'intramuscular'},
        {id:'dip-oral-50', label:'Solução oral • 50 mg/mL',kind:'liquid',strength:50,strengthUnit:'mg/mL',doseUnit:'mL',dispenseUnit:'frasco(s)',route:'oral'},
        {id:'dip-gotas-500', label:'Gotas orais • 500 mg/mL',kind:'drops',strength:500,strengthUnit:'mg/mL',doseUnit:'gota(s)',dispenseUnit:'frasco(s)',route:'oral'},
    ];
    if (name.includes('anlodipino') || name.includes('amlodipino')) return [
        {id:'aml-2.5',label:'Comprimido • 2,5 mg',kind:'tablet',strength:2.5,strengthUnit:'mg',doseUnit:'comprimido(s)',dispenseUnit:'comprimido(s)',route:'oral'},
        {id:'aml-5',label:'Comprimido • 5 mg',kind:'tablet',strength:5,strengthUnit:'mg',doseUnit:'comprimido(s)',dispenseUnit:'comprimido(s)',route:'oral'},
        {id:'aml-10',label:'Comprimido • 10 mg',kind:'tablet',strength:10,strengthUnit:'mg',doseUnit:'comprimido(s)',dispenseUnit:'comprimido(s)',route:'oral'},
    ];
    return [
        {id:'manual',label:'Comprimido - informar concentração',kind:'tablet',strength:'',strengthUnit:'mg',doseUnit:'comprimido(s)',dispenseUnit:'comprimido(s)',route:'oral'},
        {id:'manual-liquid',label:'Solução oral - informar concentração',kind:'liquid',strength:'',strengthUnit:'mg/mL',doseUnit:'mL',dispenseUnit:'frasco(s)',route:'oral'},
        {id:'manual-drops',label:'Gotas - informar concentração',kind:'drops',strength:'',strengthUnit:'mg/mL',doseUnit:'gota(s)',dispenseUnit:'frasco(s)',route:'oral'},
        {id:'manual-inj',label:'Injetável - informar concentração',kind:'ampoule',strength:'',strengthUnit:'mg/mL',doseUnit:'ampola(s)',dispenseUnit:'ampola(s)',route:'intramuscular'},
    ];
}
function PrescriptionItemCard(props) {
    const item = props.item;
    const options = presentationOptions(props.medication);
    const chosen = options.find(x => x.id === item.presentation) || options[0];
    const set = patch => props.onChange(props.index, patch);
    const field = (label,control) => React.createElement('label',{className:'rx-dose-field'},React.createElement('span',null,label),control);
    const input = (value, cb, type='number', extra={}) => React.createElement('input',{className:'input',type,min:type==='number'?0:undefined,step:'any',value:value == null?'':value,onChange:e=>cb(e.target.value),...extra});
    const quantityStep = item.form_kind === 'liquid' ? 0.1 : 1;
    const doseStepper = React.createElement('div',{className:'rx-quantity-stepper'},
        React.createElement('button',{type:'button',className:'rx-step-btn',
            'aria-label':'Diminuir quantidade por administração',
            disabled:!(Number(item.dose_quantity)>quantityStep),
            onClick:()=>set({dose_quantity:String(Math.round(Math.max(quantityStep,Number(item.dose_quantity)-quantityStep)*1000)/1000)})},'−'),
        React.createElement('input',{type:'text',inputMode:'decimal',className:'input rx-step-input',
            'aria-label':'Quantidade por administração',value:item.dose_quantity??'',
            onChange:event=>set({dose_quantity:event.target.value.replace(',', '.').replace(/[^0-9.]/g,'')})}),
        React.createElement('button',{type:'button',className:'rx-step-btn',
            'aria-label':'Aumentar quantidade por administração',
            onClick:()=>set({dose_quantity:String(Math.round((Number(item.dose_quantity||0)+quantityStep)*1000)/1000)})},'+'));
    const select = (value, choices, cb) => React.createElement('select',{className:'select',value,onChange:e=>cb(e.target.value)},choices.map(x=>React.createElement('option',{key:x.value,value:x.value},x.label)));
    const expectedDispense = calculatedDispense(item);
    const liquidVolume = requiredLiquidVolume(item);
    const isLiquidBottle = item.form_kind === 'liquid' && item.dispense_unit === 'frasco(s)';
    const manualDispense = item.dispense_mode === 'manual' || expectedDispense === null;
    return React.createElement('div',{className:'notice info rx-item rx-detailed-item'},
        React.createElement('div',{className:'row between'},React.createElement('strong',null,props.medication?.generic_name||'Medicamento'),React.createElement('button',{className:'remove-rx',type:'button',onClick:()=>props.onRemove(props.index),'aria-label':'Remover medicamento'},'×')),
        field('Apresentação e concentração',select(item.presentation||chosen.id, options.map(x=>({value:x.id,label:x.label})), id=>{
            const x=options.find(y=>y.id===id);
            set({presentation:x.id,presentation_label:x.label,form_kind:x.kind,strength_value:x.strength,strength_unit:x.strengthUnit,route:x.route,dose_unit:x.doseUnit,dispense_unit:x.dispenseUnit,dose_quantity:'',dispense_quantity:'',bottle_volume_ml:'',dispense_mode:'auto',dispense_reason:'',dose:0,unit:'mg'});
        })),
        chosen.id.startsWith('manual') && React.createElement('div',{className:'rx-dose-grid'},
            field('Concentração do produto',input(item.strength_value,v=>set({strength_value:v}))),
            field('Unidade da concentração',React.createElement('input',{className:'input',readOnly:true,value:item.strength_unit||chosen.strengthUnit}))),
        React.createElement('div', { className: 'rx-clinical-entry' },
            field('Indicação clínica', select(item.indication || '', indicationOptions(props.medication, props.patient),
                v => set({ indication: v }))),

            React.createElement('details', { className: 'rx-product-details', open: !!item.anvisa_registration },
                React.createElement('summary', null, 'Registro do produto (opcional)'),
                field('Número do registro Anvisa', input(item.anvisa_registration || '',
                    v => set({ anvisa_registration: v }), 'text',
                    { placeholder: 'Número presente na embalagem', inputMode: 'numeric', maxLength: 13 })),

                React.createElement('a', { className: 'rx-product-source',
                    href: 'https://consultas.anvisa.gov.br/#/bulario/',
                    target: '_blank', rel: 'noopener noreferrer' }, 'Consultar Bulário da Anvisa'))),
        React.createElement('div',{className:'rx-dose-grid'},
            React.createElement('div',{className:'rx-dose-field'},React.createElement('span',null,'Quantidade por administração'),doseStepper),
            field('Unidade por administração',React.createElement('input',{className:'input',readOnly:true,value:item.dose_unit||chosen.doseUnit}))),
        React.createElement('div',{className:'rx-dose-grid'},
            field('Via',select(item.route||chosen.route,(item.form_kind==='ampoule'?[{value:'intramuscular',label:'Intramuscular'},{value:'intravenosa',label:'Intravenosa'}]:[{value:'oral',label:'Oral'}]),v=>set({route:v}))),
            field('Frequência',select(item.frequency||'',[{value:'',label:'Selecione a frequência'},...FREQUENCIES.map(x=>({value:x,label:x}))],v=>set({frequency:v,duration_mode:v==='dose única'?'single':item.duration_mode==='single'?'days':item.duration_mode})))),
        field('Duração',select(item.duration_mode||'days',[{value:'days',label:'Por dias'},{value:'months',label:'Por meses'},{value:'continuous',label:'Uso contínuo'},{value:'single',label:'Dose única'}],v=>set({duration_mode:v,frequency:v==='single'?'dose única':item.frequency==='dose única'?'8/8h':item.frequency}))),
        item.duration_mode==='days'&&field('Número de dias',input(item.duration_days,v=>set({duration_days:v}))),
        item.duration_mode==='months'&&field('Número de meses',input(item.duration_months,v=>set({duration_months:v}))),
        React.createElement('div',{className:'rx-dispense-box'},
            isLiquidBottle && field('Volume de cada frasco (mL)',input(item.bottle_volume_ml||'',v=>set({bottle_volume_ml:v}),'number',{placeholder:'Ex.: 100'})),
            isLiquidBottle && liquidVolume !== null && React.createElement('small',{className:'rx-dispense-hint'},`Volume necessário: ${liquidVolume} mL no tratamento.`),
            React.createElement('div',{className:'rx-dispense-top'},
                React.createElement('strong',null,'Total a dispensar'),
                expectedDispense !== null && React.createElement('button',{
                    className:'rx-dispense-toggle',type:'button',
                    onClick:()=>set(manualDispense ? {dispense_mode:'auto',dispense_reason:''} : {dispense_mode:'manual',dispense_quantity:String(expectedDispense)}),
                },manualDispense?'Usar cálculo automático':'Ajustar')),
            React.createElement('div',{className:'rx-dispense-quantity'},
                input(manualDispense ? item.dispense_quantity : expectedDispense,
                    v=>set({dispense_mode:'manual',dispense_quantity:v}), 'number',
                    {readOnly:!manualDispense,'aria-label':'Quantidade total a dispensar'}),
                React.createElement('span',{className:'rx-dispense-unit'},item.dispense_unit||chosen.dispenseUnit)),
            manualDispense && expectedDispense === null && React.createElement('small',{className:'rx-dispense-hint'},
                'Cálculo indisponível: informe o total a dispensar.'),
            manualDispense && expectedDispense !== null && Number(item.dispense_quantity) !== expectedDispense &&
                field('Motivo do ajuste',input(item.dispense_reason||'',v=>set({dispense_reason:v}),'text',
                    {placeholder:'Justificativa do ajuste (mín. 5 caracteres)'}))),
        field('Orientações adicionais',input(item.instruction,v=>set({instruction:v}),'text',{placeholder:'Ex.: após refeições; conforme prescrição'})),
        isPediatricPatient(props.patient) && !isPediatricLosartan(props.medication, props.patient) &&
            !hasPediatricPosologyReference(props.medication, item, props.patient) &&
            React.createElement('div', { className: 'rx-pediatric-unavailable', role: 'note' },
                'Não há comparação pediátrica automática para esta apresentação. Confira a bula.'),
        isPediatricLosartan(props.medication, props.patient) && React.createElement(PediatricLosartanReference, {
            patient: props.patient, medication: props.medication
        }),
        (item.form_kind==='drops'||item.form_kind==='ampoule') && React.createElement('div',{className:'rx-dose-note'},
            item.form_kind==='drops'?'Gotas: conversão para mg depende do produto.':'Ampolas: verificar o volume da apresentação.'));
}
function isPediatricPatient(patient) {
    return !!patient && patient.age !== null && patient.age !== undefined &&
        Number.isFinite(Number(patient.age)) && Number(patient.age) >= 0 && Number(patient.age) < 12;
}
function isPediatricLosartan(medication, patient) {
    const name = String(medication?.generic_name || '').toLowerCase();
    const age = patient && patient.age != null ? Number(patient.age) : NaN;
    // A referência de 6–17 anos independe do limite de 12 anos usado no rótulo visual.
    return Number.isFinite(age) && age >= 6 && age <= 17 &&
        (name.includes('losartana') || name.includes('losartan'));
}
class PediatricLosartanReference extends React.Component {
    constructor(props) {
        super(props);
        this.state = { egfr: '', confirmed: false, result: null, error: '', busy: false };
    }
    async calculate() {
        this.setState({ busy: true, error: '', result: null });
        try {
            const result = await api('/api/dose/reference', {
                method: 'POST',
                body: {
                    patient_id: this.props.patient.id,
                    medication_id: this.props.medication.id,
                    indication: 'hipertensao_pediatrica',
                    egfr: Number(this.state.egfr)
                }
            });
            this.setState({ result });
        } catch (error) {
            this.setState({ error: error.message });
        } finally {
            this.setState({ busy: false });
        }
    }
    render() {
        const r = this.state.result;
        return React.createElement('div', { className: 'rx-pediatric-reference' },
            React.createElement('strong', null, 'Referência pediátrica documentada — hipertensão'),
            React.createElement('p', { className: 'clinical-help' },
                'Losartana (6–17 anos): referência de bula de 0,7 mg/kg uma vez ao dia, até 50 mg na dose inicial. Não calcula dose para prescrição automaticamente.'),
            React.createElement('label', { className: 'rx-dose-field' },
                React.createElement('span', null, 'TFGe atual (mL/min/1,73 m²)'),
                React.createElement('input', { className: 'input', type: 'number', min: '0', max: '200', step: 'any',
                    placeholder: 'Obrigatório', value: this.state.egfr,
                    onChange: e => this.setState({ egfr: e.target.value, result: null }) })),
            React.createElement('label', { className: 'rx-ped-confirm' },
                React.createElement('input', { type: 'checkbox', checked: this.state.confirmed,
                    onChange: e => this.setState({ confirmed: e.target.checked, result: null }) }),
                React.createElement('span', null, 'Confirmei a indicação de hipertensão pediátrica e conferi o dado renal informado.')),
            React.createElement('button', { className: 'btn btn-outline', type: 'button',
                disabled: this.state.busy || !this.state.confirmed || !this.state.egfr,
                onClick: () => this.calculate() }, this.state.busy ? 'Consultando...' : 'Consultar referência por peso'),
            this.state.error && React.createElement('div', { className: 'rx-ux-status rx-ux-status-danger', role: 'alert' }, this.state.error),
            r && React.createElement('div', { className: 'rx-ux-status rx-ux-status-info', role: 'status' },
                React.createElement('strong', null, `Referência teórica: ${r.reference_capped_mg_day} mg/dia (limite inicial: 50 mg)`),
                React.createElement('div', null, r.notice),
                React.createElement('a', { href: r.source_url, target: '_blank', rel: 'noopener noreferrer' }, 'Consultar bula DailyMed')));
    }
}
