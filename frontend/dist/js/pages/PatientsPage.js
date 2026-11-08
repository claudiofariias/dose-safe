import { AppShell } from '../components/AppShell.js';
import { PatientRow } from '../components/PatientRow.js';
export function PatientsPage(props) {
    return (React.createElement(AppShell, { route: props.route, onNavigate: props.onNavigate, tall: true },
        React.createElement("div", { className: "form-screen" },
            React.createElement("button", { className: "back", type: "button", onClick: () => props.onNavigate('dashboard') }, "\u2039"),
            React.createElement("h1", { className: "title" }, "Pacientes"),
            React.createElement("div", { className: "stack patients-list" }, props.patients.length ? (props.patients.map(patient => (React.createElement("div", { className: "card panel", key: patient.id },
                React.createElement(PatientRow, { patient: patient, onView: props.onSelectPatient }),
                React.createElement("div", { className: "tags" },
                    patient.allergies.map(allergy => (React.createElement("span", { className: "chip red", key: `a-${patient.id}-${allergy}` },
                        "Alergia: ",
                        allergy))),
                    patient.conditions.map(condition => (React.createElement("span", { className: "chip", key: `c-${patient.id}-${condition}` }, condition)))))))) : (React.createElement("div", { className: "card panel" }, "Nenhum paciente."))),
            React.createElement("button", { className: "btn btn-primary btn-full page-action", type: "button", onClick: () => props.onNavigate('patientForm') }, "Cadastrar paciente"))));
}
