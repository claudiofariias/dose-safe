"""Motor posológico determinístico do Dose Safe.

Status COMPATIVEL_COM_REFERENCIA significa SOMENTE comparação numérica com uma
referência documental cadastrada; NÃO equivale a prescrição clinicamente segura.
Nunca interpreta bula por IA nem deduz limites farmacológicos.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path
from dose_reference_screening import evaluate_orientative_reference

ROOT = Path(__file__).resolve().parent
RULES = ROOT / 'anvisa' / 'regras_clinicas.json'
FREQUENCIES = {'4/4h': 6, '6/6h': 4, '8/8h': 3, '12/12h': 2, '24/24h': 1,
               '1x pela manhã': 1, '1x à noite': 1, '2x ao dia': 2, 'dose única': 1}


def normalize(value):
    text = unicodedata.normalize('NFKD', str(value or '').casefold())
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).split())


def load_documented_rules(path=RULES):
    """Carrega somente regras documentadas e completas; rascunhos ficam inativos.

    Não exige aprovação de terceiro. A checagem é estrutural, NÃO clínica.
    Aceita o status legado 'aprovada' apenas para preservar instalações antigas.
    """
    if not Path(path).is_file():
        return []
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(payload, list):
        raise ValueError('Catálogo de referências inválido')
    documented = []
    ids = set()
    for rule in payload:
        if not isinstance(rule, dict):
            raise ValueError('Regra inválida no catálogo')
        if rule.get('status') not in ('documentada', 'aprovada'):
            continue
        validate_rule(rule)
        if rule['id'] in ids:
            raise ValueError('ID de regra duplicado')
        ids.add(rule['id'])
        documented.append(rule)
    return documented


def load_approved_rules(path=RULES):
    """Alias legado para compatibilidade com integrações anteriores."""
    return load_documented_rules(path)


def _positive_number(value, name, allow_zero=False):
    if type(value) not in (float, int) or not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f'Valor inválido para {name}')
    return value


def validate_rule(rule):
    required = ('id', 'generic_name', 'product_registration', 'presentation', 'form_kind',
                'strength_value', 'strength_unit', 'route', 'indication', 'age_min', 'age_max',
                'dose_basis', 'dose_min', 'dose_max', 'daily_max_mg', 'allowed_frequencies',
                'source_url', 'source_section', 'source_page', 'source_pdf_sha256',
                'status')
    if not isinstance(rule, dict) or any(rule.get(k) in (None, '') for k in required):
        raise ValueError('Regra incompleta: identificação, contexto, dose ou fonte documental ausentes')
    if not re.fullmatch(r'[A-Za-z0-9_-]{6,80}', str(rule['id'])):
        raise ValueError('ID de regra inválido')
    if not re.fullmatch(r'\d{9,13}', str(rule['product_registration'])):
        raise ValueError('Registro Anvisa inválido')
    if not all(str(rule[key]).strip() for key in ('generic_name','presentation','strength_unit','route','indication','source_section')):
        raise ValueError('Contexto da regra incompleto')
    if rule['form_kind'] not in ('tablet','liquid') or rule['dose_basis'] not in ('mg','mg/kg'):
        raise ValueError('Forma ou base de dose não suportada; sem conversões de gotas/ampolas')
    if (rule['form_kind'],rule['strength_unit']) not in (('tablet','mg'),('liquid','mg/mL')):
        raise ValueError('Concentração incompatível com forma')
    for field in ('strength_value','dose_min','dose_max','daily_max_mg'):
        _positive_number(rule[field],field)
    _positive_number(rule['age_min'],'age_min',True)
    _positive_number(rule['age_max'],'age_max',True)
    if rule['age_min'] > rule['age_max'] or rule['age_max'] > 120 or rule['dose_min'] > rule['dose_max']:
        raise ValueError('Limites clínicos inconsistentes')
    if rule['dose_basis']=='mg/kg' and (rule.get('weight_min') is None or rule.get('weight_max') is None):
        raise ValueError('Regra mg/kg requer limites de peso')
    if rule.get('weight_min') is not None or rule.get('weight_max') is not None:
        _positive_number(rule.get('weight_min'),'weight_min')
        _positive_number(rule.get('weight_max'),'weight_max')
        if rule['weight_min'] > rule['weight_max']: raise ValueError('Peso mínimo excede máximo')
    if not isinstance(rule['allowed_frequencies'],list) or not rule['allowed_frequencies'] or any(f not in FREQUENCIES for f in rule['allowed_frequencies']):
        raise ValueError('Frequências não suportadas pela regra')
    if rule.get('status') not in ('documentada','aprovada'): raise ValueError('Regra sem referência documental habilitada')
    if not re.fullmatch(r'[0-9a-f]{64}',str(rule['source_pdf_sha256'])):
        raise ValueError('PDF da bula não tem hash SHA-256')
    url = str(rule['source_url'])
    if not url.startswith('https://') or len(url) < 35:
        raise ValueError('URL da fonte clínica incompleta')
    if not isinstance(rule['source_page'],int) or rule['source_page'] < 1:
        raise ValueError('Página da fonte inválida')
    recorded_at = rule.get('source_recorded_at') or rule.get('reviewed_at')
    if not recorded_at or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(recorded_at)):
        raise ValueError('Data de registro da fonte inválida')


def evaluate_dose(med_name, item, patient, rules):
    """Compara apenas dose por administração e teto diário de regra compatível.

    Exige registro do produto, concentração, indicação, idade e peso se aplicável.
    NAO_VERIFICADA cobre regras ausentes ou dados incompletos/não coincidentes.
    """
    base = {'medicamento':med_name,'status':'NAO_VERIFICADA','rule_id':None,
            'message':'Sem referência de dose documentada para esta apresentação, registro, indicação e paciente.'}
    candidates = [r for r in rules if normalize(r['generic_name']) == normalize(med_name)]
    if not candidates:
        return base
    try:
        age = patient.get('age')
        if age is None or age < 0 or age > 120:
            return {**base,'message':'Data de nascimento necessária para avaliar a posologia.'}
        reg = str(item.get('anvisa_registration') or '').strip()
        indication = normalize(item.get('indication'))
        if not reg or not indication:
            return {**base,'message':'Informe indicação e registro Anvisa da apresentação para conferir a regra.'}
        weight = patient.get('weight_kg')
        compatible = []
        for r in candidates:
            if (str(r['product_registration']) != reg or
                normalize(r['indication']) != indication or
                normalize(r['presentation']) != normalize(item.get('presentation_label')) or
                r['form_kind'] != item.get('form_kind') or
                r['strength_unit'] != item.get('strength_unit') or
                r['route'] != item.get('route') or
                not math.isclose(float(r['strength_value']),float(item.get('strength_value')),rel_tol=1e-7,abs_tol=1e-7) or
                not (r['age_min'] <= age <= r['age_max'])):
                continue
            if r.get('weight_min') is not None or r['dose_basis'] == 'mg/kg':
                if weight is None or not (r['weight_min'] <= float(weight) <= r['weight_max']):
                    continue
            compatible.append(r)
        if len(compatible) != 1:
            return {**base,'message':'Nenhuma referência documental única corresponde à apresentação, indicação e dados clínicos.'}
        rule = compatible[0]
        amount = float(item['dose_quantity']) * float(item['strength_value'])
        if rule['dose_basis'] == 'mg/kg':
            amount_ref = amount / float(weight)
            unit = 'mg/kg'
        else:
            amount_ref = amount
            unit = 'mg'
        freq = item.get('frequency')
        if freq not in rule['allowed_frequencies'] or freq not in FREQUENCIES:
            return {**base,'message':'Frequência não contemplada pela referência cadastrada.'}
        daily = amount * FREQUENCIES[freq]
        source = f"{rule['source_url']} (seção {rule['source_section']}, página {rule['source_page']})"
        evaluated = {**base,'rule_id':rule['id'],'source':source,'source_recorded_at':rule.get('source_recorded_at') or rule.get('reviewed_at'),
                     'amount_mg':round(amount,5),'amount_reference':round(amount_ref,5),
                     'dose_basis':unit,'daily_mg':round(daily,5)}
        below = amount_ref < rule['dose_min'] - 1e-8
        above = amount_ref > rule['dose_max'] + 1e-8 or daily > rule['daily_max_mg'] + 1e-8
        if below or above:
            direction = 'acima do limite' if above else 'abaixo da faixa documentada'
            return {**evaluated,'status':'FORA_DA_REFERENCIA',
                'severity':'grave' if above else 'moderado',
                'message':f'Dose {amount_ref:g} {unit}; total diário {daily:g} mg: {direction}. Conferir a fonte original e os dados clínicos.'}
        return {**evaluated,'status':'COMPATIVEL_COM_REFERENCIA',
            'message':f'Dose dentro dos limites numéricos da referência {rule["id"]}. Comparação acadêmica; não comprova segurança clínica.'}
    except (TypeError,ValueError,OverflowError,ZeroDivisionError,KeyError):
        return {**base,'message':'Informações insuficientes para comparação posológica confiável.'}


def dosage_evaluations(conn, items, patient):
    try:
        rules = load_documented_rules()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        # Arquivo inválido não deve causar 500 na triagem da prescrição.
        rules = []
    names = {r['id']:r['generic_name'] for r in conn.execute('SELECT id,generic_name FROM medications')}
    evaluations = []
    for item in items:
        name = names.get(int(item['medication_id']), 'Medicamento')
        verified = evaluate_dose(name, item, patient, rules)
        # Compara com fontes publicadas apenas em apresentações com escopo exato.
        # Não transforma referência genérica em regra clínica aprovada do produto.
        if verified['status'] == 'NAO_VERIFICADA':
            orientative = evaluate_orientative_reference(name, item, patient)
            if orientative is not None:
                verified = orientative
        evaluations.append(verified)
    return evaluations
