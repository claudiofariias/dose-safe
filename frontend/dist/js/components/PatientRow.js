import { initials } from '../utils/format.js';
export function PatientRow(props) {
    var _a;
    const patient = props.patient;
    return (React.createElement("div", { className: "patient-row" },
        React.createElement("div", { className: "avatar" }, initials(patient.name)),
        React.createElement("div", { className: "patient-row-copy" },
            React.createElement("div", { className: "patient-name" }, patient.name),
            React.createElement("div", { className: "patient-meta" },
                patient.code,
                " \u2022 ", (_a = patient.age) !== null && _a !== void 0 ? _a : '—',
                " Anos")),
        React.createElement("button", { type: "button", className: "btn btn-soft patient-view-button", onClick: () => props.onView(patient) }, "Ver")));
}
