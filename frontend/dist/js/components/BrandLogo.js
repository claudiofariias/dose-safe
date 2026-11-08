import { assets } from '../assets.js';
export function BrandLogo(props) {
    const variant = props.variant || 'mark';
    const src = variant === 'splash'
        ? assets.logoSplash
        : variant === 'login'
            ? assets.logoLogin
            : assets.logoMark;
    return (React.createElement("img", { className: props.className || `brand-logo brand-logo-${variant}`, src: src, alt: "Dose Safe" }));
}
