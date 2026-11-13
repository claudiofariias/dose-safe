import { AppShell } from '../components/AppShell.js';
import { PatientRow } from '../components/PatientRow.js';
export class PatientsPage extends React.Component {
    constructor(props){super(props);this.state={query:''};}
    render(){const props=this.props; const needle=this.state.query.trim().toLocaleLowerCase('pt-BR');
    const visible=props.patients.filter(p=>!needle || `${p.name || ''} ${p.code || ''}`.toLocaleLowerCase('pt-BR').includes(needle) || String(p.code || '').toLowerCase().replace(/[^a-z0-9]/g,'').includes(needle.replace(/[^a-z0-9]/g,'')));
    return (React.createElement(AppShell, { route: props.route, onNavigate: props.onNavigate, tall: true },
        React.createElement("div", { className: "form-screen" },
            React.createElement("button", { className: "back", type: "button", onClick: () => props.onNavigate('dashboard') }, "\u2039"),
            React.createElement("h1", { className: "title" }, "Pacientes"),
            React.createElement('input',{className:'input',type:'search',placeholder:'Buscar por nome ou código L-',value:this.state.query,'aria-label':'Buscar paciente',onChange:e=>this.setState({query:e.target.value})}),
            React.createElement("div", { className: "stack patients-list" }, visible.length ? (visible.map(patient => (React.createElement("div", { className: "card panel", key: patient.id },
                React.createElement(PatientRow, { patient: patient, onView: props.onSelectPatient }),
                React.createElement("div", { className: "tags" },
                    patient.allergies.map(allergy => (React.createElement("span", { className: "chip red", key: `a-${patient.id}-${allergy}` },
                        "Alergia: ",
                        allergy))),
                    patient.conditions.map(condition => (React.createElement("span", { className: "chip", key: `c-${patient.id}-${condition}` }, condition)))))))) : (React.createElement("div", { className: "card panel" }, needle ? 'Nenhum resultado para esta busca.' : 'Nenhum paciente.'))),
            React.createElement("button", { className: "btn btn-primary btn-full page-action", type: "button", onClick: () => props.onNavigate('patientForm') }, "Cadastrar paciente"))));

}
}
