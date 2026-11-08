import { assets } from '../assets.js';
import { api } from '../services/api.js';
import { BrandLogo } from '../components/BrandLogo.js';
export class RegisterPage extends React.Component {
    constructor() {
        super(...arguments);
        this.state = {
            step: 1,
            name: '',
            email: '',
            password: '',
            role: 'professional',
            crm: '',
            specialty: '',
            busy: false,
        };
        this.handleSubmit = async (event) => {
            event.preventDefault();
            this.setState({ busy: true });
            try {
                await api('/api/auth/register', {
                    method: 'POST',
                    body: {
                        name: this.state.name,
                        email: this.state.email,
                        password: this.state.password,
                        role: this.state.role,
                        crm: this.state.crm,
                        specialty: this.state.specialty,
                    },
                });
                this.props.onToast('Cadastro criado. Faça login.');
                this.props.onRegistered();
            }
            catch (error) {
                this.props.onToast(error.message, true);
            }
            finally {
                this.setState({ busy: false });
            }
        };
        this.continueToCredentials = () => {
            if (!this.state.name.trim()) {
                this.props.onToast('Informe seu nome para continuar.', true);
                return;
            }
            this.setState({ step: 2 });
        };
    }
    renderProfileStep() {
        return (React.createElement("div", { className: "register-step" },
            React.createElement("h1", { className: "register-title" },
                "Seja",
                React.createElement("br", null),
                "Bem-vindo(a)"),
            React.createElement("div", { className: "register-form register-profile-form" },
                React.createElement("div", { className: "field" },
                    React.createElement("label", { className: "label" }, "Qual o seu nome?"),
                    React.createElement("input", { className: "input", value: this.state.name, onChange: (event) => this.setState({ name: event.target.value }), required: true })),
                React.createElement("div", { className: "field" },
                    React.createElement("label", { className: "label" }, "Nos informe seu CRM"),
                    React.createElement("input", { className: "input", value: this.state.crm, onChange: (event) => this.setState({ crm: event.target.value }) })),
                React.createElement("div", { className: "field" },
                    React.createElement("label", { className: "label" }, "Qual sua especializa\u00E7\u00E3o"),
                    React.createElement("input", { className: "input register-specialty", placeholder: "Procure sua \u00E1rea", value: this.state.specialty, onChange: (event) => this.setState({ specialty: event.target.value }) })),
                React.createElement("button", { className: "btn btn-green btn-full pill register-confirm", type: "button", onClick: this.continueToCredentials }, "Confirmar"))));
    }
    renderCredentialsStep() {
        return (React.createElement("div", { className: "register-step" },
            React.createElement("h1", { className: "register-title register-access-title" }, "Dados de acesso"),
            React.createElement("form", { onSubmit: this.handleSubmit, className: "register-form register-access-form" },
                React.createElement("div", { className: "field" },
                    React.createElement("label", { className: "label" }, "E-mail"),
                    React.createElement("input", { className: "input", type: "email", value: this.state.email, onChange: (event) => this.setState({ email: event.target.value }), required: true })),
                React.createElement("div", { className: "field" },
                    React.createElement("label", { className: "label" }, "Senha"),
                    React.createElement("input", { className: "input", type: "password", minLength: 8, value: this.state.password, onChange: (event) => this.setState({ password: event.target.value }), required: true })),
                React.createElement("div", { className: "field" },
                    React.createElement("label", { className: "label" }, "Perfil"),
                    React.createElement("select", { className: "input", value: this.state.role, onChange: (event) => this.setState({ role: event.target.value }) },
                        React.createElement("option", { value: "professional" }, "Profissional de sa\u00FAde"),
                        React.createElement("option", { value: "student" }, "Estudante"))),
                React.createElement("button", { className: "btn btn-green btn-full pill register-confirm", disabled: this.state.busy }, this.state.busy ? 'Cadastrando...' : 'Criar conta'))));
    }
    render() {
        const backAction = this.state.step === 1
            ? this.props.onBack
            : () => this.setState({ step: 1 });
        return (React.createElement("div", { className: "phone auth-phone" },
            React.createElement("section", { className: "login register-screen" },
                React.createElement("img", { className: "auth-texture", src: assets.splashBackground, alt: "", "aria-hidden": "true" }),
                React.createElement("button", { className: "back back-light", type: "button", onClick: backAction, "aria-label": "Voltar" }, "\u2039"),
                React.createElement(BrandLogo, { variant: "login", className: "register-logo" }),
                this.state.step === 1 ? this.renderProfileStep() : this.renderCredentialsStep())));
    }
}
