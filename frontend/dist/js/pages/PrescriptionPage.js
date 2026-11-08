import { AppShell } from '../components/AppShell.js';
import { Modal } from '../components/Modal.js';
import { api } from '../services/api.js';
import { frequencyToTimes, initials } from '../utils/format.js';
const FREQUENCIES = ['4/4h', '6/6h', '8/8h', '12/12h', '24/24h'];
export class PrescriptionPage extends React.Component {
    componentDidMount() {
        this.scheduleCheck();
    }
    componentWillUnmount() {
        if (this.checkTimer !== null)
            window.clearTimeout(this.checkTimer);
        this.checkSequence++;
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
        if (!patient || !items.length) {
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
        return !!(analysis === null || analysis === void 0 ? void 0 : analysis.alerts.some(alert => ['contraindicado', 'grave', 'moderado'].includes(alert.severity.toLowerCase())));
    }
    hasBlockingRisk(analysis) {
        return !!(analysis === null || analysis === void 0 ? void 0 : analysis.alerts.some(alert => ['contraindicado', 'grave'].includes(alert.severity.toLowerCase())));
    }
    constructor(props) {
        var _a, _b;
        super(props);
        this.checkTimer = null;
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
            const next = this.props.items.concat({
                medication_id: medication.id,
                dose: 500,
                unit: 'mg',
                route: medication.route || 'oral',
                frequency: this.state.frequency,
                duration_days: this.state.durationDays,
                instruction: 'Conforme orientação',
            });
            this.props.onItemsChange(next);
            this.props.onAnalysis(null);
            this.setState({ search: '' }, () => this.scheduleCheck());
        };
        this.updateItem = (index, patch) => {
            const next = this.props.items.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item);
            this.props.onItemsChange(next);
            this.props.onAnalysis(null);
            this.scheduleCheck();
        };
        this.removeItem = (index) => {
            this.props.onItemsChange(this.props.items.filter((_, itemIndex) => itemIndex !== index));
            this.props.onAnalysis(null);
            this.scheduleCheck();
        };
        this.calculateDose = async () => {
            try {
                const result = await api('/api/dose/calculate', {
                    method: 'POST',
                    body: {
                        weight_kg: this.state.weight,
                        dose_mg_kg: Number(this.state.doseKg),
                        times_per_day: frequencyToTimes(this.state.frequency),
                        concentration_mg_ml: this.state.concentration
                            ? Number(this.state.concentration)
                            : null,
                    },
                });
                this.setState({ calcResult: result });
            }
            catch (error) {
                this.props.onToast(error.message, true);
            }
        };
        this.analyze = async () => {
            const patient = this.patient;
            const items = this.normalizedItems();
            if (!patient || !items.length) {
                this.props.onToast('Selecione paciente e medicamento', true);
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
                this.props.onToast('Selecione paciente e medicamento', true);
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
            frequency: ((_a = props.items[0]) === null || _a === void 0 ? void 0 : _a.frequency) || '8/8h',
            durationDays: ((_b = props.items[0]) === null || _b === void 0 ? void 0 : _b.duration_days) || 7,
            weight: (patient === null || patient === void 0 ? void 0 : patient.weight_kg) || 0,
            doseKg: '10',
            concentration: '',
            calcResult: null,
            busy: false,
            saved: false,
            savedId: null,
            checking: false,
            reviewedKey: '',
            checkedKey: '',
        };
    }
    componentDidUpdate(prevProps, prevState) {
        var _a, _b, _c, _d, _e;
        if (((_a = prevProps.selectedPatient) === null || _a === void 0 ? void 0 : _a.id) !== ((_b = this.props.selectedPatient) === null || _b === void 0 ? void 0 : _b.id)) {
            this.setState({ weight: ((_c = this.props.selectedPatient) === null || _c === void 0 ? void 0 : _c.weight_kg) || 0 });
        }
        if (((_d = prevProps.selectedPatient) === null || _d === void 0 ? void 0 : _d.id) !== ((_e = this.props.selectedPatient) === null || _e === void 0 ? void 0 : _e.id) ||
            prevProps.items !== this.props.items ||
            (this.state.checkedKey && this.state.checkedKey !== this.draftKey()) ||
            prevState.frequency !== this.state.frequency ||
            prevState.durationDays !== this.state.durationDays) {
            this.scheduleCheck();
        }
    }
    get patient() {
        return this.props.selectedPatient || this.props.patients[0] || null;
    }
    normalizedItems() {
        return this.props.items.map(item => ({
            ...item,
            frequency: this.state.frequency,
            duration_days: this.state.durationDays,
        }));
    }
    render() {
        var _a;
        const patient = this.patient;
        const query = this.state.search.trim().toLowerCase();
        const matches = query
            ? this.props.medications
                .filter(medication => `${medication.generic_name} ${medication.brand_name || ''}`
                .toLowerCase()
                .includes(query))
                .slice(0, 8)
            : [];
        return (React.createElement(AppShell, { route: this.props.route, onNavigate: this.props.onNavigate, tall: true },
            React.createElement("style", null, RX_UX_STYLES),
            React.createElement("div", { className: "rx" },
                React.createElement("button", { className: "back", type: "button", onClick: () => this.props.onNavigate('dashboard') }, "\u2039"),
                React.createElement("h1", { className: "title" }, "Nova prescri\u00E7\u00E3o"),
                React.createElement("div", { className: "card section" },
                    React.createElement("label", { className: "label" }, "Paciente"),
                    React.createElement("select", { className: "select", value: (patient === null || patient === void 0 ? void 0 : patient.id) || '', onChange: (event) => this.selectPatient(Number(event.target.value)) }, this.props.patients.map(item => (React.createElement("option", { value: item.id, key: item.id },
                        item.name,
                        " \u2014 ",
                        item.code)))),
                    patient ? (React.createElement("div", { className: "selected-patient" },
                        React.createElement("div", { className: "miniavatar" }, initials(patient.name)),
                        React.createElement("div", { className: "selected-patient-copy" },
                            React.createElement("strong", null, patient.name),
                            React.createElement("div", { className: "danger-text" }, patient.allergies.length
                                ? `Alergia: ${patient.allergies.join(', ')}`
                                : patient.allergy_status === 'nenhuma' ? 'Nega alergias conhecidas' : 'Alergias não investigadas')),
                        React.createElement("span", null, (_a = patient.age) !== null && _a !== void 0 ? _a : '—',
                            " anos"))) : null,
                    patient ? React.createElement("div", { className: "clinical-rx-card" },
                        React.createElement("div", { className: "clinical-rx-title" }, "Ficha clínica do paciente"),
                        React.createElement("div", { className: "clinical-rx-line" }, React.createElement("strong", null, "Condições: "), (patient.conditions || []).join(", ") || "Não registradas"),
                        React.createElement("div", { className: "clinical-rx-line" }, React.createElement("strong", null, "Alergias: "), (patient.allergies || []).join(", ") || (patient.allergy_status === "nenhuma" ? "Paciente nega alergias conhecidas" : "Não investigadas")),
                        React.createElement("div", { className: "clinical-rx-line" }, React.createElement("strong", null, "Medicamentos em uso: "), (patient.active_medications || []).map(id => this.props.medications.find(m => m.id === id)?.generic_name).filter(Boolean).join(", ") || "Não registrados"),
                        React.createElement("div", { className: "clinical-rx-warning" }, "Confirme os dados clínicos antes de prescrever. A ausência de alerta não garante segurança.")) : null),
                React.createElement("div", { className: "card section" },
                    React.createElement("label", { className: "label" }, "Medicamento"),
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
                    React.createElement("div", { className: "stack rx-items" }, this.props.items.map((item, index) => (React.createElement(PrescriptionItemCard, { key: `${item.medication_id}-${index}`, item: item, index: index, medication: this.props.medications.find(medication => medication.id === item.medication_id), onChange: this.updateItem, onRemove: this.removeItem }))))),
                React.createElement("div", { className: "card section" },
                    React.createElement("div", { className: "strong calculation-heading" }, "Par\u00E2metros de c\u00E1lculo"),
                    React.createElement("label", { className: "label calculation-label" }, "Peso do paciente (kg)"),
                    React.createElement("div", { className: "counter" },
                        React.createElement("button", { type: "button", onClick: () => this.setState({ weight: Math.max(1, this.state.weight - 1) }) }, "\u2212"),
                        React.createElement("strong", null, this.state.weight),
                        React.createElement("button", { type: "button", onClick: () => this.setState({ weight: this.state.weight + 1 }) }, "+")),
                    React.createElement("div", { className: "row gap8 calculation-fields" },
                        React.createElement("div", { className: "flex1" },
                            React.createElement("label", { className: "label" }, "Dose (mg/kg)"),
                            React.createElement("input", { className: "input", type: "number", step: "0.1", value: this.state.doseKg, onChange: (event) => this.setState({ doseKg: event.target.value }) })),
                        React.createElement("div", { className: "flex1" },
                            React.createElement("label", { className: "label" }, "Concentra\u00E7\u00E3o (mg/mL)"),
                            React.createElement("input", { className: "input", type: "number", step: "0.1", placeholder: "opcional", value: this.state.concentration, onChange: (event) => this.setState({ concentration: event.target.value }) }))),
                    React.createElement("label", { className: "label calculation-label" }, "Frequ\u00EAncia"),
                    React.createElement("div", { className: "freqs" }, FREQUENCIES.map(frequency => (React.createElement("button", { type: "button", key: frequency, className: this.state.frequency === frequency ? 'active' : '', onClick: () => {
                            this.setState({ frequency, calcResult: null });
                            this.props.onAnalysis(null);
                        } }, frequency)))),
                    React.createElement("label", { className: "label calculation-label" }, "Dura\u00E7\u00E3o (dias)"),
                    React.createElement("input", { className: "input", type: "number", min: 1, value: this.state.durationDays, onChange: (event) => {
                            this.setState({ durationDays: Math.max(1, Number(event.target.value) || 1) });
                            this.props.onAnalysis(null);
                            this.scheduleCheck();
                        } })),
                React.createElement("div", { className: "row gap8 prescription-actions rx-ux-actions" },
                    React.createElement("button", { className: "btn btn-outline flex1", type: "button", onClick: this.calculateDose }, "Calcular dose"),
                    React.createElement("button", { className: "btn btn-primary flex1", type: "button", onClick: this.analyze, disabled: this.state.busy || this.state.checking || !patient || !this.props.items.length }, this.state.busy ? 'Analisando...' : 'Analisar segurança')),
                this.state.calcResult ? React.createElement("div", { className: "rx-ux-dose" },
                    React.createElement(DosePreview, { result: this.state.calcResult }),
                    React.createElement("div", { className: "rx-ux-dose-hint" }, "C\u00E1lculo de dose realizado. Isso n\u00E3o substitui a an\u00E1lise de seguran\u00E7a.")) : null,
                (() => {
                    const valid = !!this.props.analysis && this.state.checkedKey === this.draftKey();
                    const analysis = valid ? this.props.analysis : null;
                    const blocking = this.hasBlockingRisk(analysis);
                    const risk = this.hasRisk(analysis);
                    const reviewed = this.state.reviewedKey === this.draftKey();
                    const disabled = this.state.busy || this.state.checking || !analysis ||
                        blocking || (risk && !reviewed);
                    return (React.createElement("section", { className: "rx-ux-safety", "aria-label": "Seguran\u00E7a da prescri\u00E7\u00E3o" },
                        React.createElement("div", { className: "rx-ux-heading" },
                            React.createElement("strong", null, "Seguran\u00E7a da prescri\u00E7\u00E3o"),
                            analysis && React.createElement("span", { className: 'rx-ux-count ' + (blocking ? 'rx-ux-count-danger' : risk ? 'rx-ux-count-warning' : 'rx-ux-count-success') }, analysis.alerts.length ? `${analysis.alerts.length} alerta(s)` : 'Sem alertas')),
                        this.state.checking ? (React.createElement("div", { className: "rx-ux-status rx-ux-status-info", role: "status" }, "Verificando intera\u00E7\u00F5es automaticamente...")) : analysis ? (React.createElement("div", { className: "rx-ux-alert-list" },
                            analysis.alerts.length ? analysis.alerts.map((alert, index) => {
                                const level = alert.severity.toLowerCase();
                                const kind = ['contraindicado', 'grave'].includes(level) ? 'danger'
                                    : level === 'moderado' ? 'warning' : 'info';
                                const label = level === 'contraindicado' ? 'CONTRAINDICADO'
                                    : level === 'grave' ? 'ALERTA GRAVE'
                                        : level === 'moderado' ? 'ALERTA MODERADO'
                                            : 'INFORMAÇÃO';
                                return React.createElement("div", { className: `rx-ux-alert rx-ux-alert-${kind}`, role: "alert", key: `${alert.rule_id}-${index}` },
                                    React.createElement("div", { className: `rx-ux-alert-label rx-ux-alert-label-${kind}` }, label),
                                    React.createElement("div", { className: "rx-ux-alert-title" }, alert.title),
                                    React.createElement("div", { className: "rx-ux-alert-effect" }, alert.effect),
                                    alert.recommendation && React.createElement("div", { className: "rx-ux-recommendation" }, alert.recommendation));
                            }) : (React.createElement("div", { className: "rx-ux-status rx-ux-status-success", role: "status" },
                                React.createElement("strong", null, "\u2713 Nenhum alerta identificado"),
                                React.createElement("div", null, "N\u00E3o foram encontrados alertas nas regras dispon\u00EDveis da base."))),
                            blocking ? (React.createElement("div", { className: "rx-ux-status rx-ux-status-danger", role: "alert" },
                                React.createElement("strong", null, "Confirma\u00E7\u00E3o bloqueada"),
                                React.createElement("div", null, "H\u00E1 contraindica\u00E7\u00E3o ou alerta grave. Revise a prescri\u00E7\u00E3o e analise novamente."))) : risk && !reviewed ? (React.createElement("div", { className: "rx-ux-status rx-ux-status-warning", role: "status" }, "Existem alertas que exigem revis\u00E3o. Toque em \u201CAnalisar seguran\u00E7a\u201D antes de confirmar.")) : risk ? (React.createElement("div", { className: "rx-ux-status rx-ux-status-warning", role: "status" }, "Alertas revisados. Avalie as recomenda\u00E7\u00F5es antes de confirmar.")) : null)) : (React.createElement("div", { className: "rx-ux-status rx-ux-status-info", role: "status" }, patient && this.props.items.length ? 'Validação pendente. Aguarde a verificação automática.' : 'Selecione um paciente e adicione um medicamento para iniciar a análise.')),
                        React.createElement("button", { className: "btn btn-primary btn-full confirm-prescription rx-ux-confirm", type: "button", onClick: this.save, disabled: disabled }, this.state.busy ? 'Processando...' : blocking ? 'Confirmação bloqueada' : 'Confirmar prescrição'),
                        blocking && React.createElement("div", { className: "rx-ux-locked-help" }, "Revise os medicamentos acima para liberar a confirma\u00E7\u00E3o.")));
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
function PrescriptionItemCard(props) {
    var _a;
    return (React.createElement("div", { className: "notice info rx-item" },
        React.createElement("div", { className: "row between" },
            React.createElement("strong", null, ((_a = props.medication) === null || _a === void 0 ? void 0 : _a.generic_name) || 'Medicamento'),
            React.createElement("button", { className: "remove-rx", type: "button", onClick: () => props.onRemove(props.index) }, "\u00D7")),
        React.createElement("div", { className: "row gap8 rx-item-row" },
            React.createElement("input", { className: "input", type: "number", step: "0.1", "aria-label": "Dose", value: props.item.dose, onChange: (event) => props.onChange(props.index, { dose: Number(event.target.value) || 0 }) }),
            React.createElement("select", { className: "select", value: props.item.unit, onChange: (event) => props.onChange(props.index, { unit: event.target.value }) },
                React.createElement("option", null, "mg"),
                React.createElement("option", null, "mL"))),
        React.createElement("div", { className: "row gap8 rx-item-row" },
            React.createElement("select", { className: "select", value: props.item.route, onChange: (event) => props.onChange(props.index, { route: event.target.value }) },
                React.createElement("option", null, "oral"),
                React.createElement("option", null, "intravenosa"),
                React.createElement("option", null, "intramuscular")),
            React.createElement("input", { className: "input", value: props.item.instruction, "aria-label": "Instru\u00E7\u00E3o", onChange: (event) => props.onChange(props.index, { instruction: event.target.value }) }))));
}
function DosePreview(props) {
    return (React.createElement("div", { className: "result-box" },
        React.createElement("div", { className: "result-big" },
            props.result.dose_per_administration_mg,
            " mg/dose"),
        React.createElement("div", null,
            props.result.dose_per_day_mg,
            " mg/dia"),
        props.result.volume_per_administration_ml != null ? (React.createElement("div", null,
            React.createElement("strong", null,
                props.result.volume_per_administration_ml,
                " mL/dose"))) : null,
        React.createElement("div", { className: "small result-formula" }, props.result.formula),
        props.result.conversion_formula ? (React.createElement("div", { className: "small" }, props.result.conversion_formula)) : null));
}
// Estilos exclusivos desta página: não é necessário modificar o CSS global.
const RX_UX_STYLES = `
.rx-ux-actions { margin: 16px 0 10px; gap: 10px; }
.rx-ux-actions .btn { min-height: 46px; font-size: 14px; }
.rx-ux-dose { margin: 12px 0 14px; }
.rx-ux-dose-hint { padding: 6px 2px 0; font-size: 11px; color: #51637f; }
.rx-ux-safety { background: #fff; border: 1px solid #dbe3f0; border-radius: 12px; padding: 12px; margin: 12px 0 16px; box-shadow: 0 2px 9px rgba(11,31,70,.06); }
.rx-ux-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; color: #1c2c45; }
.rx-ux-heading strong { font-size: 13px; line-height: 1.2; }
.rx-ux-count { flex-shrink: 0; font-size: 11px; font-weight: 700; border-radius: 999px; padding: 4px 8px; white-space: nowrap; }
.rx-ux-count-danger { background: #fee2e2; color: #b91c1c; }
.rx-ux-count-warning { background: #ffedd5; color: #c2410c; }
.rx-ux-count-success { background: #dcfce7; color: #15803d; }
.rx-ux-alert-list { display: grid; gap: 8px; }
.rx-ux-alert { border: 1px solid; border-radius: 10px; padding: 10px 11px; line-height: 1.35; overflow-wrap: anywhere; font-size: 12px; }
.rx-ux-alert-label { font-size: 11px; font-weight: 800; letter-spacing: .03em; margin-bottom: 4px; }
.rx-ux-alert-label-danger { color: #b91c1c; }
.rx-ux-alert-label-warning { color: #c2410c; }
.rx-ux-alert-label-info { color: #1d4ed8; }
.rx-ux-alert-title { font-weight: 700; font-size: 13px; margin-bottom: 3px; }
.rx-ux-alert-effect { color: #334155; }
.rx-ux-recommendation { font-size: 11px; margin-top: 6px; color: #475569; }
.rx-ux-alert-danger { background: #fff7f7; border-color: #fecaca; }
.rx-ux-alert-danger .rx-ux-alert-title { color: #b91c1c; }
.rx-ux-alert-warning { background: #fffaf5; border-color: #fed7aa; }
.rx-ux-alert-warning .rx-ux-alert-title { color: #c2410c; }
.rx-ux-alert-info { background: #f8fbff; border-color: #bfdbfe; }
.rx-ux-alert-info .rx-ux-alert-title { color: #1d4ed8; }
.rx-ux-status { border: 1px solid; border-radius: 9px; padding: 9px 10px; font-size: 12px; line-height: 1.35; margin-top: 4px; }
.rx-ux-status strong { display: block; font-size: 12px; margin-bottom: 2px; }
.rx-ux-status-danger { background: #fff7f7; border-color: #fecaca; color: #991b1b; }
.rx-ux-status-warning { background: #fffaf5; border-color: #fed7aa; color: #9a3412; }
.rx-ux-status-info { background: #f8fbff; border-color: #bfdbfe; color: #1d4ed8; }
.rx-ux-status-success { background: #f0fdf4; border-color: #bbf7d0; color: #166534; }
.rx-ux-confirm { min-height: 56px; margin-top: 10px; }
.rx-ux-confirm:disabled { cursor: not-allowed; opacity: 1; background: #94a3b8 !important; border-color: #94a3b8 !important; color: #fff !important; }
.rx-ux-locked-help { text-align: center; color: #64748b; font-size: 12px; padding-top: 6px; }
`;
