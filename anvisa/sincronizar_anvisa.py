#!/usr/bin/env python3
"""Dose Safe — preparação auditável de dados Anvisa.

1. Indexa todos os medicamentos de catalog_100.json.
2. Opcionalmente cruza a base pública de registros de medicamentos (CSV oficial).
3. Opcionalmente extrai trechos de PDFs profissionais fornecidos localmente.

NUNCA transforma a extração bruta em regra clínica ativa.
NÃO acessa nem rastreia o Bulário Eletrônico por crawler.

Uso:
  python anvisa/sincronizar_anvisa.py
  python anvisa/sincronizar_anvisa.py --baixar-csv
  python anvisa/sincronizar_anvisa.py --csv /caminho/DADOS_ABERTOS_MEDICAMENTOS.csv
  python anvisa/sincronizar_anvisa.py --extrair-bulas
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
ANVISA_DIR = Path(__file__).resolve().parent
OUTPUT = ANVISA_DIR / "saidas"
CATALOG = ROOT / "catalog_100.json"
CSV_URL = "https://dados.anvisa.gov.br/dados/DADOS_ABERTOS_MEDICAMENTOS.csv"
BULARIO = "https://consultas.anvisa.gov.br/#/bulario/"


def norm(s: object) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.casefold())).strip()


def canonical(s: object) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(s))


def csv_value(row: dict, *names: str):
    cols = {canonical(k): v for k, v in row.items() if k is not None}
    for name in names:
        value = cols.get(canonical(name))
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def med_matches(med_name: str, active: str) -> bool:
    """Conservador: não associa substrings arbitrárias nem marcas a princípios ativos."""
    med = norm(med_name)
    act = norm(active)
    if not med or not act:
        return False
    parts = [p.strip() for p in re.split(r"\s*\+\s*", med_name)]
    if len(parts) > 1:
        return all(bool(re.search(r"(?<![a-z0-9])" + re.escape(norm(p)) + r"(?![a-z0-9])", act)) for p in parts)
    # Nomes em sais/formulações compostas (ex.: cloridrato de sertralina).
    # Exigir palavra/frase completa, para evitar correlacionar "lítio" com outras palavras.
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(med) + r"(?![a-z0-9])", act))


def download_public_csv(target: Path):
    """Baixa UMA cópia de dados abertos. Não consulta o Bulário."""
    target.parent.mkdir(parents=True, exist_ok=True)
    req = Request(CSV_URL, headers={"User-Agent": "DoseSafe-TCC/1.0 (dados abertos; download unico)"})
    temp = target.with_suffix(target.suffix + '.part')
    try:
        with urlopen(req, timeout=90) as stream, temp.open('wb') as out:
            total = 0
            while True:
                block = stream.read(1024*1024)
                if not block: break
                total += len(block)
                if total > 200*1024*1024:
                    raise ValueError('Arquivo excedeu limite de segurança de 200 MB')
                out.write(block)
        if total < 100:
            raise ValueError('Arquivo recebido é muito pequeno')
        temp.replace(target)
    finally:
        if temp.exists(): temp.unlink()


def read_csv_rows(path: Path):
    """Suporta CSV oficial em Latin-1 ou UTF-8, separado por ; ou vírgula."""
    with path.open('rb') as f:
        header = f.read(8192)
    enc = 'utf-8-sig'
    try: header.decode(enc)
    except UnicodeDecodeError: enc='cp1252'
    sample = header.decode(enc, errors='replace')
    sep = ';' if sample.partition('\n')[0].count(';') >= sample.partition('\n')[0].count(',') else ','
    with path.open('r', encoding=enc, errors='replace', newline='') as f:
        reader = csv.DictReader(f, delimiter=sep)
        if not reader.fieldnames:
            raise ValueError('CSV sem cabeçalho')
        normalized = {canonical(c) for c in reader.fieldnames}
        if 'principioativo' not in normalized:
            raise ValueError('Coluna PRINCIPIO_ATIVO não encontrada no CSV (formato inesperado)')
        yield from reader


def suspected_combination(med_name: str, ingredient_list: str) -> bool:
    """Marcador CONSERVADOR: principio ativo composto exige conferencia de bula.

    Virgulas podem separar sinonimos do MESMO farmaco. Portanto, apenas
    indica possivel associacao quando ha componentes que nao citam o
    principio ativo do catalogo. Nao substitui conferência da composicao.
    """
    if '+' in med_name:
        return False  # Catalogo ja nomeia uma associacao; exige conferencia separada.
    chunks = [norm(part) for part in re.split(r'\s*[,;+]\s*', ingredient_list) if norm(part)]
    if len(chunks) <= 1:
        return False
    target = norm(med_name)
    whole_word = re.compile(r'(?<![a-z0-9])' + re.escape(target) + r'(?![a-z0-9])')
    return any(not whole_word.search(part) for part in chunks)


def aggregate_csv(path: Path, catalog: list[dict], limit: int = 30):
    """Indexação por token do princípio ativo; não associa marcas por aproximação.

    Um token âncora reduz candidatos antes da comparação completa. Priorizamos
    registros Ativos na amostra sem ocultar o número total de inativos.
    """
    from collections import defaultdict
    anchors = defaultdict(list)
    matched = {norm(x['generic_name']): [] for x in catalog}
    counts = {key: {'ativos': 0, 'inativos': 0, 'outros': 0} for key in matched}
    dedup = {key: set() for key in matched}
    for med in catalog:
        name = med['generic_name']
        key = norm(name)
        words = [w for w in key.split() if w not in {'de', 'do', 'da', 'e', 'acido'}]
        anchor = max(words, key=len)
        if '+' in name:
            parts = [norm(p) for p in name.split('+')]
            expr = re.compile(''.join(r'(?=.*(?<![a-z0-9])'+re.escape(part)+r'(?![a-z0-9]))' for part in parts))
        else:
            expr = re.compile(r'(?<![a-z0-9])' + re.escape(key) + r'(?![a-z0-9])')
        anchors[anchor].append((key, expr))
    total = 0
    active_selected = {key: [] for key in matched}
    combination_selected = {key: [] for key in matched}
    other_selected = {key: [] for key in matched}
    for row in read_csv_rows(path):
        total += 1
        active = (row.get('PRINCIPIO_ATIVO') or '').strip()
        if not active:
            continue
        normalized = norm(active)
        candidates = set()
        for word in normalized.split():
            candidates.update(anchors.get(word, ()))
        for key, expr in candidates:
            if not expr.search(normalized):
                continue
            record = {
                'principio_ativo_publicado': active,
                'nome_produto': (row.get('NOME_PRODUTO') or '').strip(),
                'numero_registro': (row.get('NUMERO_REGISTRO_PRODUTO') or row.get('NUMERO_REGISTRO') or '').strip(),
                'situacao_registro': (row.get('SITUACAO_REGISTRO') or '').strip(),
                'categoria_regulatoria': (row.get('CATEGORIA_REGULATORIA') or '').strip(),
                'empresa_detentora': (row.get('EMPRESA_DETENTORA_REGISTRO') or '').strip(),
                'numero_processo': (row.get('NUMERO_PROCESSO') or '').strip(),
                'vencimento_registro': (row.get('DATA_VENCIMENTO_REGISTRO') or row.get('VENCIMENTO_REGISTRO') or '').strip(),
                'suspeita_associacao': suspected_combination(next((x['generic_name'] for x in catalog if norm(x['generic_name']) == key), key), active),
            }
            signature = (record['numero_registro'], record['numero_processo'], record['nome_produto'])
            if signature in dedup[key]:
                continue
            dedup[key].add(signature)
            state = norm(record['situacao_registro'])
            category = 'ativos' if state == 'ativo' else 'inativos' if state == 'inativo' else 'outros'
            counts[key][category] += 1
            selection = (combination_selected[key] if record['suspeita_associacao']
                         else active_selected[key] if category == 'ativos'
                         else other_selected[key])
            if len(selection) < limit:
                selection.append(record)
    for key in matched:
        matched[key] = (active_selected[key] + other_selected[key] + combination_selected[key])[:limit]
    return matched, total, counts


def load_binding_map():
    f = ANVISA_DIR / 'vinculos_bulas.json'
    bindings = json.loads(f.read_text(encoding='utf-8'))
    if not isinstance(bindings,list):
        raise ValueError('vinculos_bulas.json deve conter uma lista')
    return bindings


def extracted_sections(text: str):
    """Obtém excertos candidatos; índice ou layout de PDF podem confundir a captura."""
    clean = re.sub(r"[ \t]+", " ", text).replace('\r', '')
    headings = {
        'posologia': [r'(?im)^\s*8\s*[.\-–)]\s*POSOLOGIA\s+E\s+MODO\s+DE\s+USAR'],
        'contraindicacoes': [r'(?im)^\s*4\s*[.\-–)]\s*CONTRAINDICA[CÇ][OÕ]ES'],
        'interacoes': [r'(?im)^\s*6\s*[.\-–)]\s*INTERA[CÇ][OÕ]ES\s+MEDICAMENTOSAS'],
    }
    heading_all = re.compile(r'(?im)^\s*(?:[1-9]|10)\s*[.\-–)]\s*[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ][^\n]{5,120}$')
    results={}
    for key, patterns in headings.items():
        matches = [m for pat in patterns for m in re.finditer(pat, clean)]
        if not matches:
            results[key]={'status': 'nao_localizada', 'texto': ''}
            continue
        # Pega a última ocorrência: reduz chance de escolher entrada do sumário.
        start = matches[-1]
        next_titles = [m.start() for m in heading_all.finditer(clean, start.end()) if m.start() > start.end()+20]
        end = next_titles[0] if next_titles else len(clean)
        excerpt = clean[start.start():end].strip()
        results[key]={'status': 'trecho_candidato_revisar', 'texto': excerpt[:60000]}
    return results


def extract_pdfs(catalog: list[dict]):
    try: from pypdf import PdfReader
    except ImportError:
        return [], ['Extração de PDF não executada: instale pypdf (python -m pip install pypdf).']
    names = {norm(x['generic_name']): x['generic_name'] for x in catalog}
    extracted=[]
    problems=[]
    folder = (ANVISA_DIR / 'bulas_profissional').resolve()
    for item in load_binding_map():
        name = str(item.get('medicamento') or '').strip()
        fname = str(item.get('arquivo') or '').strip()
        pdf = (folder / fname).resolve()
        if norm(name) not in names:
            problems.append(f'Medicamento inexistente no catálogo: {name}')
            continue
        if not fname or not pdf.is_relative_to(folder) or pdf.suffix.lower()!='.pdf':
            problems.append(f'Nome de PDF inválido: {fname}')
            continue
        if not pdf.exists():
            problems.append(f'Bula ainda não disponível: {fname}')
            continue
        if item.get('tipo_bula') != 'profissional':
            problems.append(f'Bula não identificada como profissional: {fname}')
            continue
        if not item.get('numero_registro') or not item.get('data_consulta') or not item.get('fonte_url'):
            problems.append(f'Metadados obrigatórios ausentes (registro, data ou fonte): {fname}')
            continue
        try:
            content = pdf.read_bytes()
            reader = PdfReader(io.BytesIO(content))
            txt = '\n'.join(page.extract_text() or '' for page in reader.pages)
            sections=extracted_sections(txt)
            extracted.append({
                'medicamento': names[norm(name)],
                'registro': item['numero_registro'],
                'arquivo': fname,
                'sha256_pdf': hashlib.sha256(content).hexdigest(),
                'fonte_url': item['fonte_url'],
                'data_consulta': item['data_consulta'],
                'fabricante': item.get('fabricante',''),
                'apresentacao': item.get('apresentacao',''),
                'tipo_bula': 'profissional',
                'versao_ou_expediente': item.get('versao_ou_expediente',''),
                'paginas': len(reader.pages),
                'secoes': sections,
                'status': 'EXTRAIDO_PENDENTE_CADASTRO_DOCUMENTAL',
                'regra_ativada': False,
            })
        except Exception as exc:
            problems.append(f'Falha na extração de {fname}: {type(exc).__name__}: {str(exc)[:150]}')
    return extracted, problems


def write_json(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n',encoding='utf-8')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--csv',type=Path,help='Arquivo oficial DADOS_ABERTOS_MEDICAMENTOS.csv já baixado')
    ap.add_argument('--baixar-csv',action='store_true',help='Baixa uma cópia do CSV público oficial, sem rastrear Bulário')
    ap.add_argument('--extrair-bulas',action='store_true',help='Lê PDFs locais vinculados explicitamente (não baixa PDFs)')
    ap.add_argument('--limite-registros',type=int,default=30,help='Máximo de candidatos por medicamento (padrão: 30)')
    args = ap.parse_args(argv)
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    if not isinstance(catalog,list) or not catalog or len({norm(x['generic_name']) for x in catalog}) != len(catalog):
        ap.error('Catálogo inválido: lista vazia ou medicamentos duplicados')
    if not 1 <= args.limite_registros <= 1000: ap.error('Limite de registros deve estar entre 1 e 1000')
    csv_path = args.csv or ANVISA_DIR / 'DADOS_ABERTOS_MEDICAMENTOS.csv'
    problems=[]
    if args.baixar_csv:
        if csv_path.exists():
            print(f'CSV existente reutilizado: {csv_path}')
        else:
            try:
                download_public_csv(csv_path)
                print(f'CSV oficial obtido: {csv_path}')
            except Exception as exc:
                problems.append(f'Não foi possível baixar o CSV público: {exc}')
    matches={}
    match_counts={}
    csv_rows=0
    if csv_path.exists():
        try:
            matches,csv_rows, match_counts=aggregate_csv(csv_path,catalog,args.limite_registros)
        except Exception as exc:
            problems.append(f'CSV não processado: {exc}')
    entries=[]
    for med in catalog:
        name=med['generic_name']
        found=matches.get(norm(name),[])
        entries.append({
            'medicamento_catalogo':name,
            'consulta_manual_bulario':BULARIO,
            'termo_pesquisa':name,
            'registros_candidatos_csv':found,
            'contagem_registros_candidatos':match_counts.get(norm(name),{'ativos':0,'inativos':0,'outros':0}),
            'status_bula':'PENDENTE_VINCULO_BULA_PROFISSIONAL',
            'status_posologia':'NAO_VALIDADA',
            'status_apresentacoes':'NAO_VALIDADAS_PELA_BULA',
            'observacao':'Registro coincidente em dados abertos NÃO comprova apresentação, posologia ou registro ativo. Produtos com suspeita de associação são priorizados por último e devem ser conferidos.',
        })
    extracted=[]
    if args.extrair_bulas:
        extracted,errors=extract_pdfs(catalog)
        problems.extend(errors)
        done={norm(x['medicamento']) for x in extracted}
        for row in entries:
            if norm(row['medicamento_catalogo']) in done:
                row['status_bula']='EXTRAIDA_PENDENTE_CADASTRO_DOCUMENTAL'
    generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    metadata={
        'gerado_em_utc':generated_at,
        'origem_catalogo':'catalog_100.json',
        'total_catalogo':len(entries),
        'base_registros_url':CSV_URL,
        'registros_csv_processados':csv_rows,
        'observacao':'Dados de registro são candidatos de pareamento, não regras clínicas. PDFs extraídos não ativam validação de dose.',
        'problemas':problems,
    }
    write_json(OUTPUT/'catalogo_anvisa_revisao.json',{'metadados':metadata,'medicamentos':entries})
    # A shortlist é regenerada a partir do mesmo cruzamento: nunca manter
    # candidatos antigos que incluam associações priorizadas como monofármacos.
    shortlist=[]
    for entry in entries:
        chosen=entry['registros_candidatos_csv'][:5]
        counts=entry['contagem_registros_candidatos']
        shortlist.append({
            'medicamento':entry['medicamento_catalogo'],
            'tem_candidatos_ativos':counts['ativos'] > 0,
            'total_candidatos_ativos_na_amostra':sum(r['situacao_registro'].casefold()=='ativo' for r in chosen),
            'candidatos_para_conferencia':[
                {'produto':r['nome_produto'], 'principio_ativo_publicado':r['principio_ativo_publicado'],
                 'registro':r['numero_registro'], 'situacao':r['situacao_registro'],
                 'titular':r['empresa_detentora'], 'suspeita_associacao':r['suspeita_associacao'],
                 'observacao':('SUSPEITA DE ASSOCIAÇÃO: não tratar como produto monofármaco sem comprovação da composição e bula.'
                   if r['suspeita_associacao'] else 'Candidato textual: confirmar princípio ativo, forma, concentração e bula profissional.')}
                for r in chosen],
            'fonte':'DADOS_ABERTOS_MEDICAMENTOS.csv',
            'status':'PENDENTE_BULA_ESPECIFICA',
            'total_candidatos_ativos_no_csv':counts['ativos'],
            'total_candidatos_inativos_no_csv':counts['inativos'],
        })
    write_json(ANVISA_DIR/'candidatos_para_revisao.json',{
        'origem':'CSV oficial cruzado por texto; ordenação conservadora',
        'restricao':'Nenhuma correspondência comprova posologia ou apresentação. Associações exigem validação clínica separada.',
        'medicamentos':shortlist})
    priority = [{
        'ordem':i+1,'medicamento_catalogo':r['medicamento_catalogo'],
        'contagem_registros_candidatos':r['contagem_registros_candidatos'],
        'status':'PENDENTE_BULA_ESPECIFICA',
        'observacao':'Selecione produto e bula; não há aprovação automática por dados cadastrais.'
    } for i,r in enumerate(entries[:20])]
    write_json(ANVISA_DIR/'fila_prioritaria.json',{
        'descricao':'Primeiros 20 medicamentos do catálogo para documentação acadêmica. Ordem não representa ranking de risco.',
        'total':len(priority),'status':'PENDENTE_FONTE_ESPECIFICA',
        'medicamentos':priority})
    write_json(OUTPUT/'extracoes_bulas_pendentes.json', {'metadados':metadata,'bulas':extracted})
    n_matches=sum(bool(x['registros_candidatos_csv']) for x in entries)
    report=[
        '# Inventário de verificação — Dose Safe × Anvisa', '',
        f'- Medicamentos no catálogo: **{len(entries)}**',
        f'- Medicamentos com candidato(s) em dados abertos: **{n_matches}**',
        f'- Bulas profissionais locais extraídas para documentação: **{len(extracted)}**',
        '- Referências de dose automaticamente ativadas: **0**',
        f'- Linhas de CSV processadas: **{csv_rows}**','',
        'Nenhuma bula foi varrida automaticamente no portal da Anvisa.','',
        '| Medicamento | Ativos / Total candidatos | Status da bula |', '|---|---:|---|',
    ]
    for row in entries:
        counts = row['contagem_registros_candidatos']
        report.append(f"| {row['medicamento_catalogo']} | {counts['ativos']} / {sum(counts.values())} | {row['status_bula']} |")
    if problems:
        report.extend(['','## Pendências técnicas','']+['- '+problem.replace('\n',' ') for problem in problems])
    (OUTPUT/'RELATORIO_REVISAO.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    print(f'{len(entries)} medicamentos inventariados; {n_matches} com registro(s) candidato(s); {len(extracted)} bulas extraídas; 0 regras clínicas ativadas.')
    for problem in problems: print('AVISO:', problem, file=sys.stderr)
    print('Saídas:',OUTPUT)
    return 0 if not problems else 2


if __name__=='__main__':
    raise SystemExit(main())
