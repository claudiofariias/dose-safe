"""Comparação POSOLÓGICA ORIENTATIVA para escopo estritamente limitado.

Fontes identificadas (produto/fabricante e norma). NÃO é validação clínica,
NÃO substitui bula da apresentação prescrita e NÃO estende limites a outras
formulações. Resultados preservam a diferença entre comparação e aprovação.
"""
from __future__ import annotations

import math
import re
import unicodedata

FREQUENCIES = {
    '4/4h': 6, '6/6h': 4, '8/8h': 3, '12/12h': 2, '24/24h': 1,
    '1x pela manhã': 1, '1x à noite': 1, '2x ao dia': 2, 'dose única': 1,
}

DIP_TABLETS = {
    'rule_id': 'REF-ORIENT-DIP-TAB-500-2026',
    'source': 'Sanofi Brasil, Anador 500 mg (dipirona), apresentação comprimido: '
              'https://dotcom-br.prod.accelerator.sanofi/pt/sua-saude/autocuidado/anador-sanofi-no-brasil',
    'bounds': 'Acima de 15 anos: 1 a 2 comprimidos de 500 mg por dose, até 4 administrações ao dia.',
}
DIP_LIQUID = {
    'rule_id': 'REF-ORIENT-DIP-SOL-50-2026',
    'source': 'Aché, bula do PACIENTE de dipirona monoidratada solução oral 50 mg/mL (produto '
              'Aché; registro 105730622): '
              'https://www.ache.com.br/wp-content/uploads/application/pdf/bula-paciente-dipirona-monoidratada-solucao-oral.pdf',
    'bounds': 'Tabela de doses por faixas de peso; até 4 administrações por dia.',
}
PAR_LIQUID = {
    'rule_id': 'REF-ORIENT-PARA-SOL-200-2026',
    'source': 'Anvisa, IN 106/2021, item 69, alterado pela IN 430/2026 (referência regulatória; '
              'NÃO é bula de produto): '
              'https://anvisalegis.datalegis.net/action/ActionDatalegis.php?acao=abrirTextoAto&numeroAto=00000430&orgao=DC%2FANVISA%2FMS&tipo=INM&valorAno=2026',
    'bounds': 'Solução oral 200 mg/mL; faixa pediátrica de 10 a 15 mg/kg/dose; máximo 5 administrações por dia.',
}
# Bandas da bula Aché, em mL por administração e mL por dia; não interpolar.
DIP_WEIGHT_BANDS = (
    (5, 8, 1.25, 2.5, 10),
    (9, 15, 2.5, 5, 20),
    (16, 23, 3.75, 7.5, 30),
    (24, 30, 5, 10, 40),
    (31, 45, 7.5, 15, 60),
    (46, 53, 8.75, 17.5, 70),
)


def normalize(value):
    text = unicodedata.normalize('NFKD', str(value or '').casefold())
    return ''.join(c for c in text if not unicodedata.combining(c))


def fmt(x):
    return f'{x:g}'.replace('.', ',')


def _not_checked(name, message):
    return {'medicamento': name, 'status': 'NAO_VERIFICADA', 'rule_id': None,
            'message': message}


def _profile_for(name, item):
    generic = normalize(name).strip()
    if generic not in ('dipirona', 'dipirona monoidratada', 'paracetamol'):
        return None
    kind = item.get('form_kind')
    route = item.get('route')
    unit = item.get('strength_unit')
    try:
        strength = float(item.get('strength_value'))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(strength) or route != 'oral':
        return None
    if generic.startswith('dipirona') and kind == 'tablet' and unit == 'mg' and strength == 500:
        return 'dip_tablets'
    if generic.startswith('dipirona') and kind == 'liquid' and unit == 'mg/mL' and strength == 50:
        return 'dip_liquid'
    if generic == 'paracetamol' and kind == 'liquid' and unit == 'mg/mL' and strength == 200:
        return 'par_liquid'
    return None


def evaluate_orientative_reference(name, item, patient):
    """Exclusivamente comparação numérica orientativa; retorna None fora do escopo.

    Acima do limite = FORA_DA_REFERENCIA com sinalização de triagem.
    Dentro dos limites = COMPARACAO_ORIENTATIVA, nunca COMPATIVEL_COM_REFERENCIA.
    """
    profile = _profile_for(name, item)
    if profile is None:
        return None
    try:
        age = patient.get('age')
        if type(age) not in (int, float) or not (0 <= age <= 120):
            return _not_checked(name, 'Informe a data de nascimento para conferir a faixa etária da referência.')
        indication = normalize(item.get('indication')).strip()
        # A indicação escolhe a comparação COMPLETA; sua ausência não pode
        # ocultar uma ultrapassagem de teto numérico conhecido desta apresentação.
        indication_supported = bool(re.search(r'\b(dor|dores|febre|febril)\b', indication))
        times = FREQUENCIES.get(item.get('frequency'))
        if times is None:
            return _not_checked(name, 'Frequência não reconhecida para comparação de dose.')
        quantity = float(item.get('dose_quantity'))
        strength = float(item['strength_value'])
        if not (math.isfinite(quantity) and 0 < quantity <= 10000):
            return _not_checked(name, 'Quantidade por administração inválida para comparação.')
        mg = quantity * strength
        daily = mg * times
        weight = patient.get('weight_kg')
        reference = None
        minimum = None
        maximum = None
        max_day = None
        max_times = None
        unit = 'mg'
        val = mg
        if profile == 'dip_tablets':
            if not (16 <= age <= 120):
                return _not_checked(name, 'Referência de comprimidos de dipirona 500 mg restrita a maiores de 15 anos.')
            reference = DIP_TABLETS
            minimum, maximum, max_day, max_times = 500, 1000, 4000, 4
        elif profile == 'dip_liquid':
            reference = DIP_LIQUID
            unit, val = 'mL', quantity
            if 16 <= age <= 120:
                minimum, maximum, max_day, max_times = 10, 20, 80*50, 4
            elif 1 <= age < 16:
                if type(weight) not in (int, float) or not math.isfinite(weight):
                    return _not_checked(name, 'Peso registrado é necessário para a tabela pediátrica de dipirona.')
                band = next((b for b in DIP_WEIGHT_BANDS if b[0] <= weight <= b[1]), None)
                if not band:
                    return _not_checked(name, 'Peso fora das faixas exatas da tabela da bula; não interpolar doses.')
                minimum, maximum, max_day, max_times = band[2], band[3], band[4]*50, 4
            else:
                return _not_checked(name, 'Lactentes menores de um ano exigem verificação específica de idade em meses.')
        else:
            reference = PAR_LIQUID
            if age < 2 or (type(weight) in (int, float) and weight < 11):
                return _not_checked(name, 'A referência orienta consulta médica antes do uso abaixo de 2 anos ou 11 kg.')
            if age == 12:
                return _not_checked(name, 'Idade de 12 anos: conferir a faixa etária exata da bula do produto.')
            if age < 12:
                if type(weight) not in (int, float) or not math.isfinite(weight) or weight <= 0:
                    return _not_checked(name, 'Informe o peso para a comparação pediátrica em mg/kg.')
                if item.get('frequency') not in ('4/4h', '6/6h', 'dose única'):
                    return _not_checked(name, 'Intervalo prescrito não contempla a referência pediátrica de 4 a 6 horas.')
                unit, val = 'mg/kg', mg / weight
                minimum, maximum, max_day, max_times = 10, 15, 75*weight, 5
            else:
                if item.get('frequency') not in ('4/4h', '6/6h', 'dose única'):
                    return _not_checked(name, 'Intervalo prescrito não contemplado na referência de 4 a 6 horas.')
                maximum, max_day = 1000, 4000
        outside_above = (maximum is not None and val > maximum + 1e-8) or (max_day is not None and daily > max_day + 1e-8) or (max_times is not None and times > max_times)
        outside_below = minimum is not None and val < minimum - 1e-8
        if profile == 'dip_liquid' and age < 16:
            bounds = (f'{fmt(minimum)} a {fmt(maximum)} mL por administração, '
                      f'até {fmt(max_day / 50)} mL/dia, máximo de 4 tomadas')
        elif profile == 'par_liquid' and age < 12:
            bounds = '10 a 15 mg/kg por dose, máximo 5 tomadas e 75 mg/kg por dia'
        elif profile == 'par_liquid':
            bounds = 'até 1.000 mg por dose e 4.000 mg/dia'
        else:
            bounds = reference['bounds']
        evidence = {'medicamento': name, 'rule_id': reference['rule_id'],
                    'source': reference['source'], 'source_recorded_at': '2026-11-12',
                    'comparison_kind': 'ORIENTATIVA_NAO_ESPECIFICA_PRODUTO',
                    'amount_mg': round(mg, 5), 'amount_reference': round(val, 5),
                    'dose_basis': unit, 'daily_mg': round(daily, 5),
                    'reference_bounds': bounds,
                    'message': (f'Prescrito: {fmt(val)} {unit} por administração ({fmt(daily)} mg/dia). '
                                f'Referência consultada: {bounds}. Comparação orientativa; '
                                'não confirma segurança nem equivalência com a bula do produto prescrito.')}
        if outside_above:
            # Alerta conservador baseado APENAS em limites explícitos, após
            # conferir formulação, concentração, via, idade, peso e frequência.
            # Não significa que a indicação clínica tenha sido validada.
            if not indication_supported:
                evidence['comparison_kind'] = 'TRIAGEM_TETO_DOCUMENTAL'
                evidence['message'] += (' A indicação clínica não foi confirmada; '
                                        'o teto numérico foi usado somente para detectar possível excesso.')
            return {**evidence, 'status': 'FORA_DA_REFERENCIA',
                    'severity': 'grave',
                    'message': evidence['message'] + ' Resultado: acima do limite de dose, frequência ou total diário.'}
        if not indication_supported:
            if not indication:
                detail = 'Selecione Dor ou Febre para a comparação completa de posologia.'
            else:
                detail = 'A indicação selecionada não está contemplada na referência de Dor ou Febre.'
            return _not_checked(name, detail + ' A triagem de teto numérico não identificou excesso nos dados informados.')
        if outside_below:
            return {**evidence, 'status': 'FORA_DA_REFERENCIA', 'severity': 'moderado',
                    'message': evidence['message'] + ' Resultado: abaixo da faixa de dose descrita.'}
        return {**evidence, 'status': 'COMPARACAO_ORIENTATIVA'}
    except (ValueError, KeyError, TypeError, OverflowError, ZeroDivisionError):
        return _not_checked(name, 'Dados insuficientes para comparação posológica orientativa.')
