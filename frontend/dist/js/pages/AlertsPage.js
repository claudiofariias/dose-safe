import { AppShell } from '../components/AppShell.js';
import { api } from '../services/api.js';

// Somente pendências informativas podem ser recolhidas nesta visualização.
// Alertas de risco clínico não podem ser ocultados nem alterados aqui.
const alertKey = alert => JSON.stringify([alert.rule_id || '',alert.title || '',alert.severity || '',alert.effect || '']);
export class AlertsPage extends React.Component {
    constructor(props) {
        super(props);
        this.state={lastSaved:null,loading:!props.analysis,error:'',hidden:[],opened:{}};
        this.mounted=false;
    }
    componentDidMount(){this.mounted=true;if(!this.props.analysis)this.loadLastSaved();}
    componentDidUpdate(prevProps){
        if(this.props.analysis !== prevProps.analysis)this.setState({hidden:[],opened:{},loading:false});
    }
    componentWillUnmount(){this.mounted=false;}
    async loadLastSaved(){
        try {
            const data=await api('/api/prescriptions');
            if(!this.mounted)return;
            const entries=Array.isArray(data.prescriptions)?data.prescriptions:[];
            this.setState({lastSaved:entries[0] || null,hidden:[],loading:false});
        }catch(error){if(this.mounted)this.setState({error:error.message || 'Não foi possível carregar os alertas.',loading:false});}
    }
    dismiss(key){
        this.setState(state=>({hidden:[...state.hidden,key]}));
    }
    render(){
        const live=this.props.analysis;
        const saved=!live?this.state.lastSaved:null;
        const alerts=Array.isArray(live?.alerts)?live.alerts:Array.isArray(saved?.alerts)?saved.alerts:[];
        const visible=alerts.filter(a=>!this.state.hidden.includes(alertKey(a)));
        const canHide=a=>String(a.severity||'').toLowerCase()==='informação insuficiente';
        const hideable=visible.filter(canHide);
        const summary=live?.summary || null;
        return React.createElement(AppShell,{route:this.props.route,onNavigate:this.props.onNavigate,tall:true},
          React.createElement('div',{className:'alerts'},
            React.createElement('h1',{className:'title alerts-title'},'Alertas de segurança'),
            summary && React.createElement('div',{className:'alert-summary-chips'},
              React.createElement('span',{className:'chip'},summary.active_medication_count ?? 0,' medicamentos ativos')),
            saved && React.createElement('p',{className:'rx-dispense-hint'},
              `Prescrição de ${saved.patient_name || 'paciente'} · versão ${saved.version || '—'}`),

            this.state.loading && React.createElement('div',{className:'card panel'},'Carregando alertas...'),
            this.state.error && React.createElement('div',{className:'notice danger'},this.state.error),
            !this.state.loading && visible.length===0 && React.createElement('div',{className:'card panel'},
              alerts.length>0?'Pendências ocultadas nesta tela. A análise continua inalterada.':
              'Nenhum alerta registrado nesta análise.'),
            visible.map((alert,index)=>{
                const key=alertKey(alert); const open=!!this.state.opened[key];
                const severity=String(alert.severity || '').toLowerCase();
                return React.createElement('article',{className:'card panel ds-alert-detail-card',key},
                  React.createElement('div',{className:'ds-alert-head'},
                    React.createElement('strong',null,alert.title || 'Aviso clínico'),
                    React.createElement('span',{className:'chip'},severity || 'informação')),
                  React.createElement('p',{className:'ds-alert-effect'},alert.effect || 'Sem descrição adicional.'),
                  React.createElement('div',{className:'ds-alert-buttons'},
                    React.createElement('button',{className:'btn btn-outline',type:'button','aria-expanded':open,
                      onClick:()=>this.setState(s=>({opened:{...s.opened,[key]:!s.opened[key]}}))},open?'Ocultar detalhes':'Ver detalhes'),
                    canHide(alert) && React.createElement('button',{className:'ds-alert-clear',type:'button',
                      onClick:()=>this.dismiss(key)},'Ocultar pendência')),
                  open && React.createElement('div',{className:'ds-alert-expanded'},
                    React.createElement('strong',null,'Recomendação'),
                    React.createElement('p',null,alert.recommendation || 'Consultar o profissional responsável.'),
                    React.createElement('small',null,`Fonte: ${alert.source || 'Não informada'} · Regra: ${alert.rule_id || '—'} · Revisão: ${alert.review_date || '—'}`)));
            }),
            hideable.length>1 && React.createElement('button',{type:'button',className:'btn btn-outline btn-full ds-alert-clear-all',
              onClick:()=>this.setState(state=>({hidden:[...state.hidden,...hideable.map(alertKey)]}))},'Ocultar pendências'),
            this.state.hidden.length>0 && React.createElement('button',{type:'button',className:'ds-alert-restore',
              onClick:()=>this.setState({hidden:[]})},'Restaurar pendências'),
            React.createElement('button',{className:'btn btn-outline btn-full alert-history-link',type:'button',onClick:()=>this.props.onNavigate('history')},'Ver histórico de prescrições')));
    }
}

