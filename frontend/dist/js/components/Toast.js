export function Toast(props) {
    if (!props.message) {
        return null;
    }
    return (React.createElement("div", { className: props.error ? 'toast show error' : 'toast show', role: "status" }, props.message));
}
