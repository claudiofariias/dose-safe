import { AppShell } from '../components/AppShell.js';
import { formatDate, initials } from '../utils/format.js';
export function PatientDetailPage(props) {
    var _a, _b;
    const patient = props.patient;
    if (!patient) {
        return (React.createElement(AppShell, { route: props.route, onNavigate: props.onNavigate },
            React.createElement("div", { className: "form-screen" },
                React.createElement("h1", { className: "title" }, "Paciente"),
                React.createElement("div", { className: "card panel" }, "Paciente n\u00E3o selecionado."),
                React.createElement("button", { className: "btn btn-primary btn-full", onClick: () => props.onNavigate('patients') }, "Ver pacientes"))));
    }
    const activeMedicationNames = patient.active_medications
        .map(id => { var _a; return (_a = props.medications.find(medication => medication.id === id)) === null || _a === void 0 ? void 0 : _a.generic_name; })
        .filter(Boolean);
    return (React.createElement(AppShell, { route: props.route, onNavigate: props.onNavigate, tall: true },
        React.createElement("div", { className: "form-screen patient-detail" },
            React.createElement("button", { className: "back", type: "button", onClick: () => props.onNavigate('patients') }, "\u2039"),
            React.createElement("h1", { className: "title patient-detail-title" }, "Paciente"),
            React.createElement("div", { className: "card panel patient-summary" },
                React.createElement("div", { className: "patient-detail-head" },
                    React.createElement("div", { className: "avatar" }, initials(patient.name)),
                    React.createElement("div", null,
                        React.createElement("div", { className: "patient-name" }, patient.name),
                        React.createElement("div", { className: "patient-meta" },
                            patient.code,
                            " \u2022 ", (_a = patient.age) !== null && _a !== void 0 ? _a : '—',
                            " anos"))),
                React.createElement("div", { className: "detail-grid" },
                    React.createElement("div", null,
                        React.createElement("span", null, "Data de nascimento"),
                        React.createElement("strong", null, formatDate(patient.birth_date))),
                    React.createElement("div", null,
                        React.createElement("span", null, "Sexo"),
                        React.createElement("strong", null, patient.sex || '—')),
                    React.createElement("div", null,
                        React.createElement("span", null, "Peso"),
                        React.createElement("strong", null, (_b = patient.weight_kg) !== null && _b !== void 0 ? _b : '—',
                            " kg")),
                    React.createElement("div", null,
                        React.createElement("span", null, "\u00DAltima medi\u00E7\u00E3o"),
                        React.createElement("strong", null, formatDate(patient.weight_date))))),
            React.createElement(DetailCard, { title: "Alergias", empty: patient.allergy_status === "nenhuma" ? "Paciente nega alergias conhecidas." : "Não investigadas — confirmar com o paciente." }, patient.allergies.map(item => (React.createElement("span", { className: "chip red", key: item }, item)))),
            React.createElement(DetailCard, { title: "Condi\u00E7\u00F5es", empty: "Nenhuma condi\u00E7\u00E3o cadastrada." }, patient.conditions.map(item => (React.createElement("span", { className: "chip", key: item }, item)))),
            React.createElement(DetailCard, { title: "Medicamentos em uso", empty: "Nenhum medicamento ativo cadastrado." }, activeMedicationNames.map(item => (React.createElement("span", { className: "chip blue", key: item }, item)))),
            React.createElement("button", { className: "btn btn-outline btn-full secondary-action", type: "button", onClick: props.onEdit }, "Editar ficha clínica"),
            React.createElement("button", { className: "btn btn-primary btn-full page-action", type: "button", onClick: props.onStartPrescription }, "Nova prescri\u00E7\u00E3o"),
            React.createElement("button", { className: "btn btn-outline btn-full secondary-action", type: "button", onClick: () => props.onNavigate('patients') }, "Voltar para pacientes"))));
}
function DetailCard(props) {
    const children = props.children;
    const hasChildren = Array.isArray(children) ? children.length > 0 : Boolean(children);
    return (React.createElement("div", { className: "card panel detail-card" },
        React.createElement("h2", null, props.title),
        React.createElement("div", { className: "tags" }, hasChildren ? props.children : React.createElement("span", { className: "muted small" }, props.empty))));
}
