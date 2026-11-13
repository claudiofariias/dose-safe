import { assets } from '../assets.js';
import { AppShell } from '../components/AppShell.js';
import { api } from '../services/api.js';
export class ProfilePage extends React.Component {
    constructor() {
        super(...arguments);
        this.state = {
            confirmLogout: false,
            coverage: null,
        };
        this.openLogoutConfirm = () => {
            this.setState({ confirmLogout: true });
        };
        this.closeLogoutConfirm = () => {
            this.setState({ confirmLogout: false });
        };
        this.confirmLogout = () => {
            this.setState({ confirmLogout: false }, () => this.props.onLogout());
        };
    }
    componentDidMount() {
        this.coverageActive = true;
        api('/api/clinical/coverage').then(data => {
            if (this.coverageActive) this.setState({coverage:data});
        }).catch(() => {});
    }
    componentWillUnmount() { this.coverageActive = false; }
    render() {
        const roleFallback = {
            student: 'Estudante',
            admin: 'Administrador',
        };
        const specialty = this.props.user.specialty ||
            roleFallback[this.props.user.role] ||
            'Profissional de saúde';
        return (React.createElement(AppShell, { route: this.props.route, onNavigate: this.props.onNavigate },
            React.createElement("div", { className: "profile" },
                React.createElement("div", { className: "profile-avatar" },
                    React.createElement("img", { src: assets.profile, alt: "" })),
                React.createElement("h2", null, this.props.user.name),
                React.createElement("p", { className: "specialty" }, specialty),
                this.props.user.crm ? (React.createElement("div", { className: "crm" }, this.props.user.crm)) : null,
                this.state.coverage && React.createElement('section',{className:'card ds-coverage-card','aria-label':'Cobertura clínica'},
                    React.createElement('strong',null,'Cobertura clínica'),
                    React.createElement('div',{className:'ds-coverage-metrics'},
                        React.createElement('span',null,'Catálogo ',React.createElement('b',null,this.state.coverage.medicamentos_catalogo)),
                        React.createElement('span',null,'Registros candidatos ',React.createElement('b',null,this.state.coverage.medicamentos_com_candidatos)),
                        React.createElement('span',null,'Referências de dose ',React.createElement('b',null,this.state.coverage.referencias_dose_cadastradas))),
                    React.createElement('small',null,'Referências documentadas não substituem avaliação clínica. Registros de produtos não comprovam doses seguras.')),
                React.createElement("div", { className: "card prefs" },
                    React.createElement("div", { className: "pref-title" }, "Atalhos"),
                    React.createElement(Preference, { label: "Alertas de segurança", icon: assets.profileNotifications, onClick: () => this.props.onNavigate('alerts') })),
                React.createElement("button", { className: "btn btn-primary btn-full profile-logout", type: "button", onClick: this.openLogoutConfirm }, "Sair"),
                React.createElement("div", { className: "source profile-version" }, "App 1.9.0 \u2022 banco 1 \u2022 modo acadêmico")),
            this.state.confirmLogout ? (React.createElement("div", { className: "logout-modal-wrap", role: "dialog", "aria-modal": "true", "aria-labelledby": "logout-title", onClick: this.closeLogoutConfirm },
                React.createElement("div", { className: "logout-modal", onClick: (event) => event.stopPropagation() },
                    React.createElement("h2", { id: "logout-title" }, "Tem certeza que gostaria de sair?"),
                    React.createElement("button", { type: "button", className: "btn btn-primary btn-full logout-confirm-button", onClick: this.confirmLogout }, "Sair"),
                    React.createElement("button", { type: "button", className: "btn btn-outline btn-full logout-cancel-button", onClick: this.closeLogoutConfirm }, "Voltar")))) : null));
    }
}
function Preference(props) {
    return (React.createElement("button", { className: "pref pref-button", type: "button", onClick: props.onClick },
        React.createElement("span", { className: "pref-copy" },
            React.createElement("img", { className: "pref-icon", src: props.icon, alt: "" }),
            React.createElement("span", null, props.label)),
        React.createElement("span", { className: "pref-arrow", "aria-hidden": "true" }, "\u203A")));
}
