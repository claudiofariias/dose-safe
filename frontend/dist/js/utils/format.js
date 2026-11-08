export function initials(name) {
    return (name || '?')
        .split(/\s+/)
        .slice(0, 2)
        .map(part => { var _a; return ((_a = part[0]) === null || _a === void 0 ? void 0 : _a.toUpperCase()) || ''; })
        .join('');
}
export function formatDate(value) {
    if (!value) {
        return '—';
    }
    try {
        const normalized = value.length === 10 ? `${value}T12:00:00` : value;
        return new Intl.DateTimeFormat('pt-BR').format(new Date(normalized));
    }
    catch (_a) {
        return value;
    }
}
export function splitTags(value) {
    return String(value || '')
        .split(',')
        .map(item => item.trim())
        .filter(Boolean);
}
export function frequencyToTimes(value) {
    const map = {
        '4/4h': 6,
        '6/6h': 4,
        '8/8h': 3,
        '12/12h': 2,
        '24/24h': 1,
    };
    return map[value] || 1;
}
