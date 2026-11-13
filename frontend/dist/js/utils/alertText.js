// Textos de riscos e pendências; sem mudar a classificação fornecida pela API.
const riskSeverities = new Set(['contraindicado', 'grave', 'moderado', 'leve']);
export function isRiskAlert(alert) {
    return riskSeverities.has(String(alert?.severity || '').toLowerCase());
}
export function countWord(number, singular, plural) {
    return `${number} ${number === 1 ? singular : plural}`;
}
export function summarizeAlertCounts(alerts) {
    const all = Array.isArray(alerts) ? alerts : [];
    const risks = all.filter(isRiskAlert).length;
    const pending = all.length - risks;
    if (!all.length) return 'Sem alertas';
    return [risks ? countWord(risks, 'risco', 'riscos') : '',
            pending ? countWord(pending, 'pendência', 'pendências') : '']
        .filter(Boolean).join(' · ');
}
