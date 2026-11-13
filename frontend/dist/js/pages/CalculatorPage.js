import { AppShell } from '../components/AppShell.js';
import { AcademicNotice } from '../components/AcademicNotice.js';
export class CalculatorPage extends React.Component {
    render() {
        return React.createElement(AppShell, { route: this.props.route, onNavigate: this.props.onNavigate, tall: true },
            React.createElement('div', { className: 'calculator' },
                React.createElement('button', { className: 'back', type: 'button', onClick: () => this.props.onNavigate('profile') }, '‹'),
                React.createElement('h1', { className: 'title' }, 'Cálculo posológico'),
                React.createElement('div', { className: 'calculator-notice' }, React.createElement(AcademicNotice, null)),
                React.createElement('div', { className: 'card panel stack calculator-form' },
                    React.createElement('strong', null, 'Cálculo somente por medicamento e indicação'),
                    React.createElement('p', { className: 'clinical-help' }, 'A antiga calculadora geral de mg/kg foi desativada. Em adultos, a dose costuma ser definida pelo medicamento, indicação clínica, apresentação e características do paciente.'),
                    React.createElement('p', { className: 'clinical-help' }, 'Na prescrição, referências de dose por peso aparecem exclusivamente quando existe regra específica documentada, faixa etária aplicável e dados clínicos disponíveis. Não são aplicadas automaticamente.'),
                    React.createElement('button', { className: 'btn btn-primary', type: 'button', onClick: () => this.props.onNavigate('prescription') }, 'Abrir prescrição'))));
    }
}
