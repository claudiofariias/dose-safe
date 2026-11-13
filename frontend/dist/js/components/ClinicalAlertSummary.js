import { countWord } from '../utils/alertText.js';

// Exibição somente: nunca altera a gravidade ou os alertas retornados pelo servidor.
const e = React.createElement;
const priority = {contraindicado:0, grave:1, moderado:2, leve:3};
function severityOf(alert) { return String(alert?.severity || '').toLowerCase(); }
function isRisk(alert) { return Object.prototype.hasOwnProperty.call(priority, severityOf(alert)); }
function labelOf(alert) {
  return ({contraindicado:'Contraindicado',grave:'Grave',moderado:'Advertência',leve:'Atenção'})[severityOf(alert)] || 'Informação pendente';
}
function keyOf(alert) { return [alert.rule_id || '',alert.title || '',alert.effect || '',severityOf(alert)].join('|'); }
export function splitClinicalAlerts(alerts) {
  const seen = new Set(); const risks=[]; const info=[];
  (Array.isArray(alerts) ? alerts : []).forEach(alert => {
    const key = keyOf(alert);
    if (seen.has(key)) return;
    seen.add(key);
    (isRisk(alert) ? risks : info).push(alert);
  });
  risks.sort((a,b) => priority[severityOf(a)] - priority[severityOf(b)]);
  return {risks,info};
}
export class ClinicalAlertSummary extends React.Component {
  constructor(props) { super(props); this.state={showInfo:false, expanded:{}}; }
  renderCard(alert, index, prefix) {
    const key = prefix + keyOf(alert);
    const expanded = !!this.state.expanded[key];
    const severity = severityOf(alert);
    const risk = isRisk(alert);
    const critical = severity === 'contraindicado' || severity === 'grave';
    return e('article',{className:'clinical-alert-row '+(risk?'clinical-alert-risk':'clinical-alert-info')+(critical?' clinical-alert-critical':''),key},
      e('div',{className:'clinical-alert-top'},
        e('span',{className:'clinical-alert-severity '+(risk?'severity-'+severity:'severity-info')},labelOf(alert)),
        e('button',{type:'button',className:'clinical-alert-toggle',onClick:()=>this.setState(s=>({expanded:{...s.expanded,[key]:!s.expanded[key]}})), 'aria-expanded':expanded},expanded?'Ocultar detalhes':'Ver detalhes')),
      e('strong',{className:'clinical-alert-name'},alert.title || 'Aviso clínico'),
      risk && alert.effect && e('p',{className:'clinical-alert-effect'},alert.effect),
      expanded && e('div',{className:'clinical-alert-extra'},
        !risk && alert.effect && e('p',null,alert.effect),
        alert.recommendation && e('p',null,alert.recommendation),
        e('div',{className:'clinical-alert-source'},'Fonte: ',alert.source || 'Não informada',
          ' · Regra: ',alert.rule_id || '—',' · Revisão: ',alert.review_date || '—')));
  }
  render() {
    const {risks,info} = splitClinicalAlerts(this.props.alerts);
    const infoLabel = info.length === 1 ? `1 pendência: ${info[0].title || 'dados não verificados'}` :
      countWord(info.length,'pendência','pendências') + ' de dados';
    return e('div',{className:'clinical-alert-summary'},
      e('div',{className:'clinical-alert-counts',role:'status'},
        e('strong',null,countWord(risks.length,'risco identificado','riscos identificados')),
        info.length>0 && e('span',null,' · '+countWord(info.length,'pendência','pendências'))),
      risks.length>0 && e('section',{className:'clinical-alert-group','aria-label':'Riscos clínicos'},
        risks.map((a,i)=>this.renderCard(a,i,'r'))),
      info.length>0 && e('section',{className:'clinical-alert-group clinical-alert-info-group'},
        e('button',{type:'button',className:'clinical-alert-info-button',onClick:()=>this.setState(s=>({showInfo:!s.showInfo})), 'aria-expanded':this.state.showInfo},
          e('span',null,infoLabel),e('span',{'aria-hidden':'true'},this.state.showInfo?'−':'+')),
        this.state.showInfo && info.map((a,i)=>this.renderCard(a,i,'i'))));
  }
}
