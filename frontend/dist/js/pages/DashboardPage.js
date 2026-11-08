import { assets } from '../assets.js';
import { AppShell } from '../components/AppShell.js';
import { PatientRow } from '../components/PatientRow.js';
import { api } from '../services/api.js';
export class DashboardPage extends React.Component {
    constructor() {
        super(...arguments);
        this.state = {
            data: null,
            loading: true,
        };
    }
    componentDidMount() {
        this.load();
    }
    async load() {
        try {
            const data = await api('/api/dashboard');
            this.setState({ data, loading: false });
        }
        catch (error) {
            this.props.onToast(error.message, true);
            this.setState({ loading: false });
        }
    }
    render() {
        var _a, _b;
        const firstName = (this.props.user.name || 'Usuário').split(' ')[0];
        const currentDate = new Intl.DateTimeFormat('pt-BR', {
            day: '2-digit',
            month: 'long',
            year: 'numeric',
        }).format(new Date());
        const data = this.state.data;
        return (React.createElement(AppShell, { route: this.props.route, onNavigate: this.props.onNavigate },
            React.createElement("div", { className: "dashboard" },
                React.createElement("p", { className: "subtitle" }, "Painel de Controle"),
                React.createElement("h1", { className: "hello" },
                    "Ol\u00E1, ",
                    firstName,
                    "!"),
                React.createElement("div", { className: "datebar" },
                    React.createElement("img", { src: assets.calendar, className: "date-icon", alt: "" }),
                    React.createElement("span", null, currentDate)),
                React.createElement("div", { className: "card metric" },
                    React.createElement("div", null,
                        React.createElement("div", { className: "strong" }, "Prescri\u00E7\u00F5es de hoje"),
                        React.createElement("div", { className: "metric-icon" },
                            React.createElement("img", { src: assets.prescriptions, alt: "" }))),
                    React.createElement("div", { className: "metric-right" },
                        React.createElement("div", { className: "count" }, (_a = data === null || data === void 0 ? void 0 : data.prescriptions_today) !== null && _a !== void 0 ? _a : '—'),
                        React.createElement("button", {
                            className: "metric-history-arrow", type: "button",
                            title: "Ver histórico de prescrições", "aria-label": "Ver histórico de prescrições",
                            onClick: () => this.props.onNavigate('history')
                        }, "›"))),
                React.createElement("div", { className: "card patients-card" },
                    React.createElement("div", { className: "strong patients-card-title" }, "Pacientes recentes"),
                    this.state.loading ? (React.createElement("div", { className: "help" }, "Carregando pacientes...")) : ((_b = data === null || data === void 0 ? void 0 : data.recent_patients) === null || _b === void 0 ? void 0 : _b.length) ? (data.recent_patients.map(patient => (React.createElement(PatientRow, { key: patient.id, patient: patient, onView: this.props.onSelectPatient })))) : (React.createElement("div", { className: "help" }, "Nenhum paciente recente.")),
                    React.createElement("button", { type: "button", className: "list-link", onClick: () => this.props.onNavigate('patients') }, "Examinar todos os pacientes")),
                React.createElement("button", { type: "button", className: "btn btn-outline btn-full add-patient", onClick: () => this.props.onNavigate('patientForm') }, "Cadastrar paciente"))));
    }
}
