import { assets } from '../assets.js';
const navItems = [
    { route: 'dashboard', label: 'Home', icon: assets.home },
    { route: 'prescription', label: 'Adicionar', icon: assets.add },
    { route: 'alerts', label: 'Alerta', icon: assets.alert },
    { route: 'profile', label: 'Perfil', icon: assets.profile },
];
export function BottomNav(props) {
    return (React.createElement("nav", { className: "nav", "aria-label": "Navega\u00E7\u00E3o principal" }, navItems.map(item => (React.createElement("button", { key: item.route, type: "button", className: props.active === item.route ? 'active' : '', onClick: () => props.onNavigate(item.route) },
        React.createElement("img", { className: "nav-icon", src: item.icon, alt: "" }),
        React.createElement("span", null, item.label))))));
}
