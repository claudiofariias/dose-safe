import { AcademicNotice } from '../components/AcademicNotice.js';
import { AppShell } from '../components/AppShell.js';
import { api } from '../services/api.js';
export class CalculatorPage extends React.Component {
    constructor() {
        super(...arguments);
        this.state = {
            weight: '20',
            dose: '10',
            times: '2',
            concentration: '20',
            result: null,
        };
        this.calculate = async (event) => {
            event.preventDefault();
            try {
                const result = await api('/api/dose/calculate', {
                    method: 'POST',
                    body: {
                        weight_kg: Number(this.state.weight),
                        dose_mg_kg: Number(this.state.dose),
                        times_per_day: Number(this.state.times),
                        concentration_mg_ml: this.state.concentration
                            ? Number(this.state.concentration)
                            : null,
                    },
                });
                this.setState({ result });
            }
            catch (error) {
                this.props.onToast(error.message, true);
            }
        };
    }
    render() {
        return (React.createElement(AppShell, { route: this.props.route, onNavigate: this.props.onNavigate, tall: true },
            React.createElement("div", { className: "calculator" },
                React.createElement("button", { className: "back", type: "button", onClick: () => this.props.onNavigate('profile') }, "\u2039"),
                React.createElement("h1", { className: "title" }, "Calculadora posol\u00F3gica"),
                React.createElement("div", { className: "calculator-notice" },
                    React.createElement(AcademicNotice, null)),
                React.createElement("form", { className: "card panel stack calculator-form", onSubmit: this.calculate },
                    React.createElement(NumberField, { label: "Peso (kg)", value: this.state.weight, onChange: value => this.setState({ weight: value }) }),
                    React.createElement(NumberField, { label: "Dose (mg/kg)", value: this.state.dose, onChange: value => this.setState({ dose: value }) }),
                    React.createElement(NumberField, { label: "Frequ\u00EAncia (vezes/dia)", value: this.state.times, onChange: value => this.setState({ times: value }), step: "1" }),
                    React.createElement(NumberField, { label: "Concentra\u00E7\u00E3o (mg/mL) \u2014 opcional", value: this.state.concentration, onChange: value => this.setState({ concentration: value }) }),
                    React.createElement("button", { className: "btn btn-primary" }, "Calcular")),
                this.state.result ? (React.createElement("div", { className: "result-box" },
                    React.createElement("div", { className: "result-big" },
                        this.state.result.dose_per_administration_mg,
                        " mg por dose"),
                    React.createElement("div", null,
                        this.state.result.dose_per_day_mg,
                        " mg/dia"),
                    this.state.result.volume_per_administration_ml != null ? (React.createElement("div", null,
                        React.createElement("strong", null,
                            this.state.result.volume_per_administration_ml,
                            " mL por dose"))) : null,
                    React.createElement("p", { className: "small" }, this.state.result.formula),
                    this.state.result.conversion_formula ? (React.createElement("p", { className: "small" }, this.state.result.conversion_formula)) : null)) : null)));
    }
}
function NumberField(props) {
    return (React.createElement("div", null,
        React.createElement("label", { className: "label" }, props.label),
        React.createElement("input", { className: "input", type: "number", step: props.step || '0.1', value: props.value, onChange: (event) => props.onChange(event.target.value), required: true })));
}
