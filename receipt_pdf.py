"""PDF acadêmico de prescrição, com trilha da análise e sem validade clínica/legal.

Implementação independente de bibliotecas externas; utiliza fontes PDF padrão.
Exibe somente informações efetivamente registradas, sem inferir segurança clínica.
"""
from __future__ import annotations

import math
import textwrap
from datetime import date, datetime

PAGE_W, PAGE_H = 595, 842


def _clean(value):
    value = str(value if value is not None else '').replace('\r', ' ').replace('\n', ' ')
    return value.encode('cp1252', 'replace').decode('cp1252')


def _esc(value):
    return _clean(value).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _fmt(value):
    try:
        number = float(value)
        if not math.isfinite(number):
            return 'não informado'
        return f'{number:g}'.replace('.', ',')
    except (TypeError, ValueError, OverflowError):
        return 'não informado'


def _age_at(birth_date, created_at):
    try:
        birth = date.fromisoformat(str(birth_date))
        reference = date.fromisoformat(str(created_at)[:10])
        if birth > reference:
            return None
        return reference.year - birth.year - ((reference.month, reference.day) < (birth.month, birth.day))
    except (TypeError, ValueError):
        return None


def _total_required_liquid(item):
    """Aritmética da dispensação, não validação de dose nem sugestão terapêutica."""
    try:
        if item.get('form_kind') != 'liquid' or item.get('dose_unit') != 'mL':
            return None
        amount = float(item['dose_quantity'])
        if not math.isfinite(amount) or amount <= 0:
            return None
        if item.get('duration_mode') == 'single' and item.get('frequency') == 'dose única':
            return amount
        if item.get('duration_mode') != 'days':
            return None
        days = float(item['duration_days'])
        if not days.is_integer() or days <= 0:
            return None
        times = {'4/4h': 6, '6/6h': 4, '8/8h': 3, '12/12h': 2,
                 '24/24h': 1, '1x pela manhã': 1, '1x à noite': 1,
                 '2x ao dia': 2}
        administrations = times.get(item.get('frequency'))
        if administrations is None:
            if item.get('frequency') == '1x por semana' and int(days) % 7 == 0:
                return amount * (int(days) // 7)
            return None
        return amount * administrations * int(days)
    except (ValueError, TypeError, OverflowError, KeyError):
        return None


def _equivalent_mg(item):
    """Conversão numérica somente para apresentações suportadas no backend."""
    if item.get('form_kind') not in ('tablet', 'liquid'):
        return None
    if (item.get('form_kind'), item.get('strength_unit'), item.get('dose_unit')) not in (
            ('liquid', 'mg/mL', 'mL'), ('tablet', 'mg', 'comprimido(s)')):
        return None
    try:
        quantity = float(item['dose_quantity'])
        strength = float(item['strength_value'])
        result = quantity * strength
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError, OverflowError, KeyError):
        return None


def build_receipt_pdf(prescription, patient, professional, medicines):
    """Gera PDF com alertas e avaliação salvos, sem reavaliar com regras posteriores.

    Para registros legados, a ausência de fotografia dos dados clínicos é explícita.
    """
    pages, commands = [], []
    page_num = 0
    y = 0

    def draw(txt, x, py, size=10, bold=False, color=(0.11, 0.18, 0.31)):
        r, g, b = color
        commands.append(f'BT /{("F2" if bold else "F1")} {size} Tf {r:.3f} {g:.3f} {b:.3f} rg 1 0 0 1 {x} {py:.2f} Tm ({_esc(txt)}) Tj ET')

    def line(ypos):
        commands.append(f'0.79 0.85 0.91 RG 0.8 w 44 {ypos:.2f} m 551 {ypos:.2f} l S')

    def new_page():
        nonlocal commands, y, page_num
        if commands:
            pages.append('\n'.join(commands).encode('cp1252', 'replace'))
        commands = []
        page_num += 1
        commands.append('0.93 0.96 1 rg 0 766 595 76 re f')
        draw('DOSE SAFE', 44, 803, 19, True, (0.02, 0.11, 0.31))
        draw('RELATÓRIO DE PRESCRIÇÃO - USO ACADÊMICO', 44, 783, 10, True)
        line(755)
        draw('DOCUMENTO ACADÊMICO - NÃO VÁLIDO COMO RECEITA MÉDICA', 44, 740, 9, True, (0.67, 0.10, 0.10))
        draw(f'Prescrição #{prescription["id"]}  |  Versão {prescription["version"]}  |  Página {page_num}', 44, 32, 8)
        draw('Sem assinatura digital ou validade para dispensação.', 44, 20, 8)
        y = 712

    def reserve(height):
        if y < height + 77:
            new_page()

    def paragraph(text, size=9, bold=False, indent=44, width=None, gap=3, muted=False):
        nonlocal y
        if width is None:
            width = 92 if indent >= 55 else 97
        color = (0.37, 0.44, 0.55) if muted else (0.11, 0.18, 0.31)
        lines = textwrap.wrap(_clean(text), width=width,
                              break_long_words=True, break_on_hyphens=False) or ['-']
        for part in lines:
            reserve(size + gap)
            draw(part, indent, y, size, bold, color)
            y -= size + gap

    def section(title):
        nonlocal y
        reserve(85)
        y -= 8
        paragraph(title.upper(), 11, True, width=68, gap=6)
        line(y + 7)
        y -= 6

    new_page()
    alerts = prescription.get('alerts') or []
    evaluations = prescription.get('dosage_evaluations') or []
    has_snapshot = bool(patient.get('historical_snapshot', False))
    age = patient.get('age_at_registration') if has_snapshot else _age_at(patient.get('birth_date'), prescription.get('created_at'))
    weight = patient.get('weight_kg') if has_snapshot else None

    section('Paciente')
    paragraph(f'Nome: {patient.get("name") or "Não informado"}  |  Identificação: {patient.get("code") or "Não informada"}')
    paragraph(f'Data de nascimento: {patient.get("birth_date") or "Não informada"}  |  Idade na data do registro: {str(age) + " anos" if age is not None else "não determinada"}')
    if has_snapshot:
        paragraph(f'Peso registrado: {(_fmt(weight) + " kg") if weight is not None else "não informado"}  |  Data da pesagem: {patient.get("weight_date") or "não informada"}')
    else:
        paragraph('Registro anterior à atualização: peso utilizado na análise não preservado; idade calculada a partir do cadastro atual.', muted=True)

    section('Responsável pelo registro')
    paragraph(f'Nome: {professional.get("name") or "Não informado"}')
    paragraph(f'CRM informado no cadastro: {professional.get("crm") or "Não informado"}  |  Especialidade: {professional.get("specialty") or "não informada"}')

    section('Medicamentos registrados')
    for index, item in enumerate(prescription.get('items') or [], 1):
        reserve(110)
        med = medicines.get(int(item.get('medication_id') or 0), {})
        name = item.get('medication_name_at_registration') or med.get('generic_name') or 'Medicamento não identificado'
        paragraph(f'{index}. {name}', 10, True, width=86)
        if item.get('presentation'):
            presentation = item.get('presentation_label') or item.get('presentation')
            paragraph(f'Apresentação: {presentation}  |  Concentração: {_fmt(item.get("strength_value"))} {item.get("strength_unit") or ""}', indent=55)
            paragraph(f'Indicação clínica registrada: {item.get("indication") or "não informada"}', indent=55)
            paragraph(f'Registro Anvisa informado: {item.get("anvisa_registration") or "não informado / sem vinculação à bula"}', indent=55)
            paragraph(f'Por administração: {_fmt(item.get("dose_quantity"))} {item.get("dose_unit") or ""}  |  Via: {item.get("route") or "não informada"}', indent=55)
            equivalent_mg = _equivalent_mg(item)
            if equivalent_mg is not None:
                equivalent = f'Equivalência matemática: {_fmt(equivalent_mg)} mg por administração'
                if age is not None and age < 18 and weight is not None:
                    try:
                        kg = float(weight)
                        if math.isfinite(kg) and kg > 0:
                            equivalent += f' ({_fmt(equivalent_mg / kg)} mg/kg por dose)'
                    except (ValueError, TypeError, OverflowError):
                        pass
                paragraph(equivalent + '. NÃO representa validação clínica.', indent=55, muted=True)
            else:
                paragraph('Conversão em mg não disponível para esta apresentação.', indent=55, muted=True)
            mode = item.get('duration_mode')
            duration = ('Uso contínuo' if mode == 'continuous' else 'Dose única' if mode == 'single' else
                        f'{_fmt(item.get("duration_months"))} meses' if mode == 'months' else
                        f'{_fmt(item.get("duration_days"))} dias')
            paragraph(f'Frequência: {item.get("frequency") or "não informada"}  |  Duração: {duration}', indent=55)
            unit_dispense = item.get('dispense_unit') or ''
            if unit_dispense == 'frasco(s)':
                try:
                    unit_dispense = 'frasco' if float(item.get('dispense_quantity')) == 1 else 'frascos'
                except (TypeError, ValueError):
                    unit_dispense = 'frasco(s)'
            total = f'{_fmt(item.get("dispense_quantity"))} {unit_dispense}' 
            bottle = item.get('bottle_volume_ml')
            if item.get('dispense_unit') == 'frasco(s)' and bottle not in (None, ''):
                total += f' de {_fmt(bottle)} mL' + (' cada' if unit_dispense == 'frascos' else '')
            paragraph(f'Total a dispensar registrado: {total}', indent=55)
            if item.get('dispense_mode') == 'manual':
                paragraph(f'Dispensação ajustada manualmente: {item.get("dispense_reason") or "justificativa não registrada"}', indent=55, muted=True)
            liquid_total = _total_required_liquid(item)
            if liquid_total is not None:
                paragraph(f'Volume necessário calculado para o período: {_fmt(liquid_total)} mL.', indent=55, muted=True)
        else:
            paragraph(f'Apresentação: {med.get("form") or "não informada"}', indent=55)
            paragraph(f'Dose: {item.get("dose") or "não informada"} {item.get("unit") or ""}; via: {item.get("route") or "não informada"}', indent=55)
            paragraph(f'Frequência: {item.get("frequency") or "não informada"}; duração: {item.get("duration_days") or "não informada"} dia(s)', indent=55)
        paragraph(f'Orientações: {item.get("instruction") or "não informadas"}', indent=55)
        if index <= len(evaluations):
            evaluation = evaluations[index - 1]
            status = evaluation.get('status')
            labels = {'COMPATIVEL_COM_REFERENCIA': 'DENTRO DOS LIMITES DA REGRA',
                      'FORA_DA_REFERENCIA': 'FORA DOS LIMITES DA REFERÊNCIA',
                      'COMPARACAO_ORIENTATIVA': 'COMPARAÇÃO ORIENTATIVA (NÃO VALIDA SEGURANÇA)',
                      'NAO_VERIFICADA': 'NÃO VERIFICADA'}
            paragraph(f'Avaliação posológica salva: {labels.get(status, "NÃO DETERMINADA")}', indent=55, bold=True)
            if evaluation.get('message'):
                paragraph(f'Detalhe: {evaluation["message"]}', indent=55)
            if evaluation.get('rule_id'):
                paragraph(f'Regra: {evaluation["rule_id"]}  |  Fonte registrada: {evaluation.get("source_recorded_at") or evaluation.get("reviewed_at") or "não informada"}', indent=55, muted=True)
            if evaluation.get('source'):
                paragraph(f'Fonte da regra: {evaluation["source"]}', indent=55, muted=True)
        else:
            paragraph('Avaliação posológica individual: não preservada neste registro antigo. Consulte os alertas salvos.', indent=55, muted=True)
        y -= 7

    section('Resultado da análise registrada')
    risks = [a for a in alerts if a.get('severity') in ('contraindicado', 'grave', 'moderado', 'leve')]
    information = [a for a in alerts if a.get('severity') not in ('contraindicado', 'grave', 'moderado', 'leve')]
    risk_text = f'{len(risks)} ' + ('risco clínico identificado' if len(risks) == 1 else 'riscos clínicos identificados')
    info_text = f'{len(information)} ' + ('pendência' if len(information) == 1 else 'pendências')
    paragraph(f'{risk_text}  |  {info_text}', bold=True)
    if not alerts:
        paragraph('Nenhum alerta registrado nas regras disponíveis. Isto NÃO comprova ausência de risco.')
    for index, alert in enumerate(alerts, 1):
        reserve(75)
        paragraph(f'{index}. [{str(alert.get("severity") or "não classificada").upper()}] {alert.get("title") or "Alerta"}', bold=True, indent=55, width=90)
        if alert.get('type'):
            paragraph(f'Categoria: {alert["type"]}', indent=55, muted=True)
        if alert.get('effect'):
            paragraph(f'Detalhes: {alert["effect"]}', indent=55)
        if alert.get('recommendation'):
            paragraph(f'Orientação: {alert["recommendation"]}', indent=55)
        paragraph(f'Fonte: {alert.get("source") or "não informada"}', indent=55, muted=True)
        paragraph(f'Regra: {alert.get("rule_id") or "não identificada"}  |  Revisão: {alert.get("review_date") or "não informada"}', indent=55, muted=True)
        y -= 5

    section('Rastreabilidade')
    paragraph(f'Data do registro (UTC): {prescription.get("created_at") or "não informada"}')
    paragraph(f'Versão da base de regras: {prescription.get("rule_version") or "não informada"}')
    if prescription.get('justification'):
        paragraph(f'Justificativa registrada para alertas: {prescription["justification"]}')
    y -= 7
    paragraph('Análise automatizada de apoio acadêmico, com cobertura parcial. Uma comparação de dose não confirma segurança clínica global. Documento sem validade como receita médica.', size=9, width=95)
    pages.append('\n'.join(commands).encode('cp1252', 'replace'))

    # PDF 1.4 com fontes WinAnsi padrão, sem dependências de execução adicionais.
    objects = [None, None,
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>']
    kids = []
    for content in pages:
        content_id = len(objects) + 1
        objects.append(b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream')
        page_id = len(objects) + 1
        kids.append(page_id)
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>'.encode())
    objects[0] = b'<< /Type /Catalog /Pages 2 0 R >>'
    objects[1] = f'<< /Type /Pages /Kids [{" ".join(str(i)+" 0 R" for i in kids)}] /Count {len(kids)} >>'.encode()
    result = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = [0]
    for i, content in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f'{i} 0 obj\n'.encode() + content + b'\nendobj\n')
    start = len(result)
    result.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        result.extend(f'{offset:010d} 00000 n \n'.encode())
    result.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF'.encode())
    return bytes(result)
