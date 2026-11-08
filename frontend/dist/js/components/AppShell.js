import { BrandLogo } from './BrandLogo.js';
import { BottomNav } from './BottomNav.js';
export function AppShell(props) {
    const nav = props.nav !== false;
    const classes = ['screen'];
    if (props.className) {
        classes.push(props.className);
    }
    return (React.createElement("div", { className: "phone app-phone" },
        React.createElement("section", { className: classes.join(' ') },
            React.createElement("div", { className: "logo-mini", "aria-label": "Dose Safe" },
                React.createElement(BrandLogo, { variant: "mark" })),
            props.children),
        nav ? (React.createElement(BottomNav, { active: props.route, onNavigate: props.onNavigate })) : null));
}
