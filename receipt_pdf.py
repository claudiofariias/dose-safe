"""PDF de demonstração acadêmica - biblioteca padrão do Python."""
import textwrap
from datetime import datetime

PAGE_W, PAGE_H = 595, 842

def _clean(value):
    value = str(value if value is not None else '').replace('\r', ' ').replace('\n', ' ')
    return value.encode('cp1252', 'replace').decode('cp1252')

def _esc(value):
    return _clean(value).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

def build_receipt_pdf(prescription, patient, professional, medicines):
    """Generates a multi-page, readable PDF; never an electronically signed prescription."""
    pages = []
    commands = []
    y = 0
    page_num = 0

    def draw(txt, x, py, size=10, bold=False, color=(0.11, 0.18, 0.31)):
        r,g,b = color
        commands.append(f'BT /{("F2" if bold else "F1")} {size} Tf {r:.3f} {g:.3f} {b:.3f} rg 1 0 0 1 {x} {py:.2f} Tm ({_esc(txt)}) Tj ET')

    def line(ypos):
        commands.append(f'0.78 0.84 0.91 RG 0.8 w 44 {ypos:.2f} m 551 {ypos:.2f} l S')

    def new_page():
        nonlocal commands, y, page_num
        if commands:
            pages.append('\n'.join(commands).encode('cp1252', 'replace'))
        commands = []
        page_num += 1
        commands.append('0.93 0.96 1 rg 0 766 595 76 re f')
        draw('DOSE SAFE', 44, 803, 19, True, (0.02, 0.11, 0.31))
        draw('REGISTRO DE PRESCRICAO - USO ACADEMICO', 44, 783, 10, True)
        line(755)
        draw('DOCUMENTO ACADEMICO - NAO VALIDO COMO RECEITA MEDICA', 44, 740, 9, True, (0.67, 0.10, 0.10))
        draw(f'Prescricao #{prescription["id"]}  |  Versao {prescription["version"]}  |  Pagina {page_num}', 44, 32, 8)
        draw('Sem assinatura digital ou validade para dispensacao.', 44, 20, 8)
        y = 715

    def paragraph(text, size=10, bold=False, indent=44, width=88, gap=5):
        nonlocal y
        clean = _clean(text)
        lines = textwrap.wrap(clean, width=width, break_long_words=True, break_on_hyphens=False) or ['-']
        for part in lines:
            if y < 73:
                new_page()
            draw(part, indent, y, size, bold)
            y -= size + gap

    def section(title):
        nonlocal y
        if y < 125: new_page()
        y -= 10
        paragraph(title.upper(), 11, True, width=68, gap=6)
        line(y + 7)
        y -= 4

    new_page()
    section('Paciente')
    paragraph(f'Nome: {patient["name"]}')
    paragraph(f'Identificacao: {patient["code"]}')
    paragraph(f'Data de nascimento: {patient["birth_date"] or "Nao informada"}')
    section('Responsavel pelo registro')
    paragraph(f'Nome: {professional["name"]}')
    paragraph(f'CRM informado no cadastro: {professional["crm"] or "Nao informado"}')
    paragraph(f'Especialidade informada: {professional["specialty"] or "Nao informada"}')
    section('Medicamentos registrados')
    for num, item in enumerate(prescription['items'], 1):
        med = medicines.get(int(item.get('medication_id', 0) or 0), {})
        name = med.get('generic_name', 'Medicamento nao identificado')
        form = med.get('form') or 'Nao informada'
        paragraph(f'{num}. {name} - {form}', 10, True)
        dosage = f'{item.get("dose", "Nao informada")} {item.get("unit", "")}'.strip()
        paragraph(f'Dose: {dosage}  |  Via: {item.get("route") or "Nao informada"}', 9, indent=55, width=94)
        paragraph(f'Frequencia: {item.get("frequency") or "Nao informada"}  |  Duracao: {item.get("duration_days") or "Nao informada"} dia(s)', 9, indent=55, width=94)
        paragraph(f'Orientacoes: {item.get("instruction") or "Nao informadas"}', 9, indent=55, width=94)
        y -= 7
    section('Informacoes complementares')
    paragraph(f'Data do registro (UTC): {prescription["created_at"]}')
    paragraph(f'Versao da base de regras: {prescription["rule_version"]}', 9)
    paragraph(f'Alertas registrados na analise: {len(prescription["alerts"])}', 9)
    if prescription.get('justification'):
        paragraph(f'Justificativa registrada: {prescription["justification"]}', 9)
    y -= 8
    paragraph('A analise de seguranca e academica e nao substitui avaliacao clinica. Este documento nao contem assinatura valida.', 9, width=96)
    pages.append('\n'.join(commands).encode('cp1252', 'replace'))

    # PDF 1.4 with standard Helvetica/WinAnsi fonts, no runtime dependencies.
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
