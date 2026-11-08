import { AcademicNotice } from '../components/AcademicNotice.js';
import { AppShell } from '../components/AppShell.js';
import { api } from '../services/api.js';
import { formatDate } from '../utils/format.js';
export class AdherencePage extends React.Component {
    constructor(props) {
        super(props);
        this.selectPatient = (patientId) => {
            const patient = this.props.patients.find(item => item.id === patientId);
            if (patient) {
                this.props.onSelectPatient(patient);
            }
            this.setState({ patientId }, () => this.load());
        };
        this.register = async (status) => {
            if (!this.state.patientId) {
                this.props.onToast('Selecione um paciente', true);
                return;
            }
            try {
                const now = new Date().toISOString();
                await api('/api/adherence', {
                    method: 'POST',
                    body: {
                        patient_id: this.state.patientId,
                        status,
                        note: this.state.note,
                        scheduled_at: now,
                        recorded_at: now,
                    },
                });
                this.props.onToast('Evento registrado');
                this.setState({ note: '' }, () => this.load());
            }
            catch (error) {
                this.props.onToast(error.message, true);
            }
        };
        const patient = props.selectedPatient || props.patients[0] || null;
        this.state = {
            patientId: (patient === null || patient === void 0 ? void 0 : patient.id) || 0,
            note: '',
            events: [],
            loading: false,
        };
    }
    componentDidMount() {
        this.load();
    }
    async load() {
        if (!this.state.patientId) {
            return;
        }
        this.setState({ loading: true });
        try {
            const response = await api(`/api/adherence?patient_id=${this.state.patientId}`);
            this.setState({ events: response.events, loading: false });
        }
        catch (_a) {
            this.setState({ events: [], loading: false });
        }
    }
    render() {
        return (React.createElement(AppShell, { route: this.props.route, onNavigate: this.props.onNavigate, tall: true },
            React.createElement("div", { className: "form-screen" },
                React.createElement("button", { className: "back", type: "button", onClick: () => this.props.onNavigate('profile') }, "\u2039"),
                React.createElement("h1", { className: "title" }, "Ades\u00E3o"),
                React.createElement("div", { className: "adherence-notice" },
                    React.createElement(AcademicNotice, null)),
                React.createElement("div", { className: "card panel stack adherence-panel" },
                    React.createElement("div", null,
                        React.createElement("label", { className: "label" }, "Paciente"),
                        React.createElement("select", { className: "select", value: this.state.patientId, onChange: (event) => this.selectPatient(Number(event.target.value)) }, this.props.patients.map(patient => (React.createElement("option", { value: patient.id, key: patient.id }, patient.name))))),
                    React.createElement("div", { className: "row gap8 adherence-actions" },
                        React.createElement("button", { className: "btn btn-green flex1", type: "button", onClick: () => this.register('taken') }, "Tomada"),
                        React.createElement("button", { className: "btn btn-soft flex1", type: "button", onClick: () => this.register('late') }, "Atraso"),
                        React.createElement("button", { className: "btn btn-outline flex1", type: "button", onClick: () => this.register('missed') }, "Omiss\u00E3o")),
                    React.createElement("textarea", { className: "textarea", placeholder: "Observa\u00E7\u00E3o opcional", value: this.state.note, onChange: (event) => this.setState({ note: event.target.value }) }),
                    React.createElement("div", null, this.state.loading ? (React.createElement("div", { className: "help" }, "Carregando eventos...")) : this.state.events.length ? (this.state.events.map(event => (React.createElement("div", { className: "notice info adherence-event", key: event.id },
                        React.createElement("strong", null, event.status),
                        " \u2022 ",
                        formatDate(event.recorded_at || event.scheduled_at),
                        React.createElement("br", null),
                        event.note || 'Sem observação')))) : (React.createElement("div", { className: "help" }, "Sem eventos no per\u00EDodo.")))))));
    }
}
