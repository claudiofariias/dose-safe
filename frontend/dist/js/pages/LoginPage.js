import { assets } from '../assets.js';
import { api } from '../services/api.js';
import { BrandLogo } from '../components/BrandLogo.js';
export class LoginPage extends React.Component {
    constructor() {
        super(...arguments);
        this.state = {
            email: 'claudio@dosesafe.local',
            password: 'DoseSafe123!',
            busy: false,
            showPassword: false,
        };
        this.handleSubmit = async (event) => {
            event.preventDefault();
            this.setState({ busy: true });
            try {
                const response = await api('/api/auth/login', {
                    method: 'POST',
                    body: {
                        email: this.state.email,
                        password: this.state.password,
                    },
                });
                this.props.onToast('Login realizado');
                this.props.onLogin(response.user);
            }
            catch (error) {
                this.props.onToast(error.message, true);
            }
            finally {
                this.setState({ busy: false });
            }
        };
    }
    render() {
        return (React.createElement("div", { className: "phone auth-phone" },
            React.createElement("section", { className: "login login-figma" },
                React.createElement("img", { className: "auth-texture", src: assets.splashBackground, alt: "", "aria-hidden": "true" }),
                React.createElement(BrandLogo, { variant: "login", className: "login-logo" }),
                React.createElement("form", { onSubmit: this.handleSubmit, className: "login-form" },
                    React.createElement("div", { className: "field" },
                        React.createElement("label", { className: "label", htmlFor: "login-email" }, "E-mail"),
                        React.createElement("input", { id: "login-email", className: "input", type: "email", autoComplete: "username", value: this.state.email, onChange: (event) => this.setState({ email: event.target.value }), required: true })),
                    React.createElement("div", { className: "field" },
                        React.createElement("label", { className: "label", htmlFor: "login-password" }, "Senha"),
                        React.createElement("div", { className: "password-field" },
                            React.createElement("input", { id: "login-password", className: "input", type: this.state.showPassword ? 'text' : 'password', autoComplete: "current-password", value: this.state.password, onChange: (event) => this.setState({ password: event.target.value }), required: true }),
                            React.createElement("button", { type: "button", className: "password-toggle", "aria-label": this.state.showPassword ? 'Ocultar senha' : 'Mostrar senha', onClick: () => this.setState(state => ({ showPassword: !state.showPassword })) },
                                React.createElement("span", { "aria-hidden": "true" }, "\u25C9")))),
                    React.createElement("button", { type: "button", className: "link-button" }, "Esqueci minha senha"),
                    React.createElement("button", { className: "btn btn-green btn-full pill", disabled: this.state.busy }, this.state.busy ? 'Entrando...' : 'Entrar'),
                    React.createElement("button", { type: "button", className: "btn btn-full pill secondary login-register-button", onClick: this.props.onRegister }, "Cadastrar"),
                    React.createElement("div", { className: "or" }, "Ou"),
                    React.createElement("div", { className: "social-login", "aria-label": "Outras op\u00E7\u00F5es de acesso" },
                        React.createElement("button", { type: "button", className: "social-button", "aria-label": "Facebook" },
                            React.createElement("img", { className: "social-brand social-brand-facebook", src: assets.socialFacebook, alt: "" })),
                        React.createElement("button", { type: "button", className: "social-button", "aria-label": "Google" },
                            React.createElement("img", { className: "social-brand social-brand-google", src: assets.socialGoogle, alt: "" })),
                        React.createElement("button", { type: "button", className: "social-button", "aria-label": "Apple" },
                            React.createElement("img", { className: "social-brand social-brand-apple", src: assets.socialApple, alt: "" }))),
                    React.createElement("details", { className: "demo-details" },
                        React.createElement("summary", null, "Acesso de demonstra\u00E7\u00E3o"),
                        React.createElement("div", { className: "demo-box" },
                            "claudio@dosesafe.local",
                            React.createElement("br", null),
                            "DoseSafe123!",
                            React.createElement("br", null),
                            React.createElement("br", null),
                            "Uso acad\u00EAmico \u2014 base cl\u00EDnica apenas demonstrativa."))))));
    }
}
