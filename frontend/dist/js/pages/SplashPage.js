import { assets } from '../assets.js';
import { BrandLogo } from '../components/BrandLogo.js';
export function SplashPage() {
    return (React.createElement("div", { className: "phone splash-screen", "aria-label": "Dose Safe" },
        React.createElement("img", { className: "splash-texture", src: assets.splashBackground, alt: "", "aria-hidden": "true" }),
        React.createElement("div", { className: "splash-logo-wrap" },
            React.createElement(BrandLogo, { variant: "splash", className: "splash-logo" }))));
}
