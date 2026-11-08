import { AppShell } from '../components/AppShell.js';
import { api } from '../services/api.js';

export class AlertsPage extends React.Component {
    constructor(props) {
        super(props);
        this.state = { lastSaved: null, loading: !props.analysis, error: '' };
        this.mounted = false;
    }
    componentDidMount() {
        this.mounted = true;
        if (!this.props.analysis) this.loadLastSaved();
    }
    componentDidUpdate(prevProps) {
        if (this.props.analysis && !prevProps.analysis && this.state.loading) {
            this.setState({ loading: false });
        }
    }
    componentWillUnmount() { this.mounted = false; }
    async loadLastSaved() {
        try {
            const data = await api('/api/prescriptions');
            if (!this.mounted) return;
            const prescriptions = Array.isArray(data.prescriptions) ? data.prescriptions : [];
            this.setState({ lastSaved: prescriptions[0] || null, loading: false });
        } catch (error) {
            if (this.mounted) this.setState({ error: error.message || 'Não foi possível carregar os alertas.', loading: false });
        }
    }
    render() {
        const live = this.props.analysis;
        const saved = !live ? this.state.lastSaved : null;
        const analysis = live || null;
        const alerts = Array.isArray(analysis?.alerts) ? analysis.alerts :
            (Array.isArray(saved?.alerts) ? saved.alerts : []);
        const summary = analysis?.summary || null;
        return React.createElement(AppShell, { route: this.props.route, onNavigate: this.props.onNavigate, tall: true },
            React.createElement('div', { className: 'alerts' },
                React.createElement('h1', { className: 'title alerts-title' }, 'Alertas de segurança'),
                summary && React.createElement('div', { className: 'alert-summary-chips' },
                    React.createElement('span', { className: 'chip' }, summary.active_medication_count ?? 0, ' medicamentos ativos'),
                    React.createElement('span', { className: 'chip blue' }, summary.polypharmacy || '')), 
                summary && React.createElement('div', { className: 'notice info alert-summary-notice' },
                    summary.message || 'Análise de segurança', React.createElement('br'),
                    'Base: ', summary.rule_version || '—', ' • pares avaliados: ', summary.pairs_evaluated ?? '—'),
                saved && React.createElement('div', { className: 'notice info alert-summary-notice' },
                    'Última prescrição salva: ', saved.patient_name || 'Paciente',
                    '. Os alertas abaixo pertencem a esta prescrição, não a uma nova análise.'),
                this.state.loading && !analysis && React.createElement('div', { className: 'card panel' }, 'Carregando alertas...'),
                this.state.error && React.createElement('div', { className: 'notice danger' }, this.state.error),
                !this.state.loading && alerts.length > 0
                    ? alerts.map((alert, index) => React.createElement(AlertCard, {
                        key: `${alert.rule_id || alert.title || 'alerta'}-${index}`,
                        alert, onAdjust: () => this.props.onNavigate('prescription')
                    }))
                    : (!this.state.loading && React.createElement('div', { className: 'card panel' },
                        saved ? 'A última prescrição salva não possui alertas registrados.' : 'Nenhuma análise recente. Para verificar medicamentos, crie uma prescrição.',
                        React.createElement('button', { className: 'btn btn-primary btn-full no-analysis-button', type: 'button', onClick: () => this.props.onNavigate('prescription') }, 'Ir para prescrição'))),
                React.createElement('button', { className: 'btn btn-outline btn-full alert-history-link', type: 'button', onClick: () => this.props.onNavigate('history') }, 'Ver histórico de prescrições')
            )
        );
    }
}

class AlertCard extends React.Component {
    constructor(props) {
        super(props);
        this.state = { revisado: false };
    }
    render() {
        const alert = this.props.alert || {};
        const revisado = this.state.revisado;
        const severity = String(alert.severity || '').toLowerCase();
        const severityClass = severity === 'informação insuficiente' ? 'insuficiente' : severity;
        const labelMap = {
            contraindicado: 'Contraindicado', grave: 'Grave', moderado: 'Advertência',
            leve: 'Leve', 'informação insuficiente': 'Informação insuficiente'
        };
        return React.createElement('article', { className: `card alert-card ${revisado ? 'alert-reviewed' : ''}` },
            React.createElement('div', { className: `alert-head ${severityClass}` },
                React.createElement('img', { src: '/assets/icon-alert.svg', className: 'inline-alert-icon', alt: '' }),
                React.createElement('span', null, labelMap[severity] || 'Aviso')),
            React.createElement('div', { className: 'alert-body' },
                React.createElement('div', { className: 'alert-title' }, alert.title || 'Alerta de segurança'),
                React.createElement('div', { className: 'alert-effect' }, alert.effect || ''),
                React.createElement('div', { className: 'small alert-recommendation' }, alert.recommendation || ''),
                React.createElement('div', { className: 'source' },
                    'Fonte: ', alert.source || 'Não informada', React.createElement('br'),
                    'Revisão: ', alert.review_date || '—', ' • versão ', alert.rule_version || '—', ' • ', alert.rule_id || '—'),
                React.createElement('div', { className: 'alert-actions' },
                    React.createElement('button', {
                        type: 'button', className: revisado ? 'reviewed-btn active' : 'reviewed-btn',
                        onClick: () => this.setState({ revisado: !revisado }), 'aria-pressed': revisado
                    }, revisado ? '✓ Revisado' : 'Marcar revisado'),
                    React.createElement('button', { type: 'button', className: 'adjust', onClick: this.props.onAdjust }, 'Ajustar medicação')),
                revisado && React.createElement('div', { className: 'reviewed-message', role: 'status' },
                    '✓ Alerta marcado como revisado apenas nesta visualização. Não significa autorização clínica.')
            )
        );
    }
}
