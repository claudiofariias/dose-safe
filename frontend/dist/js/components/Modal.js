export function Modal(props) {
    return ReactDOM.createPortal(React.createElement("div", { className: "modal-wrap", role: "dialog", "aria-modal": "true" },
        React.createElement("div", { className: "modal" },
            React.createElement("h2", null, props.title),
            props.children,
            React.createElement("button", { type: "button", className: "btn btn-outline btn-full", onClick: props.onClose }, "Voltar"))), document.body);
}
