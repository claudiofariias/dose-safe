import { AppShell } from '../components/AppShell.js';
import { api } from '../services/api.js';
import { formatDate } from '../utils/format.js';
export class HistoryPage extends React.Component {
    constructor() {
        super(...arguments);
        this.state = { prescriptions: [], loading: true };
    }
    componentDidMount() {
        this.load();
    }
    async load() {
        try {
            const response = await api('/api/prescriptions');
            this.setState({ prescriptions: response.prescriptions, loading: false });
        }
        catch (error) {
            this.props.onToast(error.message, true);
            this.setState({ loading: false });
        }
    }
    render() {
        return (React.createElement(AppShell, { route: this.props.route, onNavigate: this.props.onNavigate, tall: true },
            React.createElement("div", { className: "history" },
                React.createElement("button", { className: "back", type: "button", onClick: () => this.props.onNavigate('dashboard') }, "\u2039"),
                React.createElement("h1", { className: "title" }, "Hist\u00F3rico"),
                React.createElement("div", { className: "stack history-list" }, this.state.loading ? (React.createElement("div", { className: "card panel" }, "Carregando...")) : this.state.prescriptions.length ? (this.state.prescriptions.map(prescription => (React.createElement(HistoryItem, { key: prescription.id, prescription: prescription, medications: this.props.medications })))) : (React.createElement("div", { className: "card panel" }, "Nenhuma vers\u00E3o salva."))))));
    }
}


class HistoryItem extends React.Component {
    constructor(props) {
        super(props);
        this.state = { expanded: false };
    }

    render() {
        const prescription = this.props.prescription;
        const medications = this.props.medications || [];
        const items = prescription.items || [];
        const alerts = prescription.alerts || [];
        const expanded = this.state.expanded;

        return React.createElement(
            "div",
            { className: "card history-item" },

            React.createElement(
                "div",
                {
                    className: "history-grid",
                    style: {
                        gridTemplateColumns: "1fr auto auto",
                        alignItems: "center"
                    }
                },

                React.createElement(
                    "div",
                    { style: { minWidth: 0 } },
                    React.createElement(
                        "strong",
                        null,
                        prescription.patient_name
                    ),
                    React.createElement(
                        "div",
                        { className: "small muted" },
                        prescription.patient_code,
                        " • versão ",
                        prescription.version,
                        " • ",
                        formatDate(prescription.created_at)
                    )
                ),

                React.createElement(
                    "div",
                    {
                        className: "alert-count",
                        style: { fontSize: "12px" }
                    },
                    alerts.length,
                    " alerta(s)"
                ),

                React.createElement(
                    "button",
                    {
                        type: "button",
                        onClick: () => this.setState({
                            expanded: !this.state.expanded
                        }),
                        "aria-expanded": expanded,
                        "aria-label": expanded
                            ? "Fechar detalhes"
                            : "Ver detalhes",
                        style: {
                            width: "34px",
                            height: "34px",
                            border: "0",
                            borderRadius: "8px",
                            background: "#dce8fa",
                            color: "#1e3a8a",
                            fontSize: "25px",
                            fontWeight: "800",
                            cursor: "pointer"
                        }
                    },
                    expanded ? "⌄" : "›"
                )
            ),

            !expanded && React.createElement(
                "div",
                { className: "tags history-tags" },
                items.map((item, index) => {
                    const med = medications.find(
                        m => String(m.id) === String(item.medication_id)
                    );

                    return React.createElement(
                        "span",
                        {
                            className: "chip",
                            key: index
                        },
                        med ? med.generic_name : "Medicamento"
                    );
                })
            ),

            expanded && React.createElement(
                "div",
                {
                    style: {
                        marginTop: "14px",
                        paddingTop: "12px",
                        borderTop: "1px solid #c9d5e8"
                    }
                },

                React.createElement(
                    "strong",
                    null,
                    "Medicamentos prescritos"
                ),

                items.map((item, index) => {
                    const med = medications.find(
                        m => String(m.id) === String(item.medication_id)
                    );

                    return React.createElement(
                        "div",
                        {
                            key: index,
                            style: {
                                background: "#e8f0ff",
                                padding: "10px",
                                marginTop: "8px",
                                borderRadius: "8px",
                                fontSize: "12px"
                            }
                        },
                        React.createElement(
                            "strong",
                            null,
                            med ? med.generic_name : "Medicamento"
                        ),
                        React.createElement(
                            "div",
                            null,
                            "Dose: ",
                            item.dose || "Não informada"
                        ),
                        React.createElement(
                            "div",
                            null,
                            "Frequência: ",
                            item.frequency || "Não informada"
                        )
                    );
                }),

                React.createElement(
                    "h3",
                    {
                        style: {
                            fontSize: "14px",
                            marginTop: "15px"
                        }
                    },
                    "Alertas identificados (",
                    alerts.length,
                    ")"
                ),

                alerts.length
                    ? alerts.map((alert, index) =>
                        React.createElement(
                            "div",
                            {
                                key: index,
                                style: {
                                    background: "#fff4df",
                                    padding: "10px",
                                    marginTop: "8px",
                                    borderRadius: "8px",
                                    fontSize: "12px"
                                }
                            },
                            React.createElement(
                                "strong",
                                null,
                                alert.title || "Alerta"
                            ),
                            React.createElement(
                                "div",
                                null,
                                alert.effect || ""
                            ),
                            React.createElement(
                                "div",
                                { style: { marginTop: "5px" } },
                                alert.recommendation || ""
                            )
                        )
                    )
                    : React.createElement(
                        "p",
                        { className: "small muted" },
                        "Nenhum alerta registrado."
                    ),

                React.createElement(
                    "button",
                    {
                        type: "button",
                        className: "btn btn-primary btn-full",
                        style: { marginTop: "12px" },
                        onClick: () => window.open(`/api/prescriptions/${prescription.id}/pdf`, '_blank')
                    },
                    "Baixar receita PDF"
                ),

                prescription.justification &&
                React.createElement(
                    "p",
                    { className: "small" },
                    "Justificativa: ",
                    prescription.justification
                )
            ),

            React.createElement(
                "div",
                { className: "source" },
                "Base de regras: ",
                prescription.rule_version
            )
        );
    }
}
