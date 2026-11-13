"""Motor de análise de prescrição: dose, duplicidade, alergia, condições e interações.

Triagem acadêmica de apoio; ausência de alerta NÃO comprova segurança clínica.
"""
from __future__ import annotations

import json
import re
import unicodedata

from clinical_rules import dosage_evaluations
from common import age_from_birth, fold, jload
from config import ROOT, RULE_VERSION
from errors import ApiError


def patient_to_dict(row):
    return {
        "id": row["id"], "code": row["code"], "name": row["name"], "birth_date": row["birth_date"],
        "age": age_from_birth(row["birth_date"]), "sex": row["sex"], "weight_kg": row["weight_kg"],
        "height_cm": row["height_cm"], "weight_date": row["weight_date"],
        "allergies": jload(row["allergies"], []), "allergy_status": row["allergy_status"], "conditions": jload(row["conditions"], []),
        "active_medications": jload(row["active_medications"], []), "active": bool(row["active"])
    }


def severity_rank(value):
    return {"contraindicado": 0, "grave": 1, "moderado": 2, "leve": 3, "informação insuficiente": 4}.get(value, 5)



def dosage_alerts(conn, items, patient):
    """Triagem de dose com regras documentadas ou referências orientativas limitadas.

    Uma comparação orientativa NÃO equivale a validação clínica do medicamento.
    Interações, alergias e condições são analisadas separadamente.
    """
    evaluations = dosage_evaluations(conn, items, patient_to_dict(patient))
    alerts = []
    for i,ev in enumerate(evaluations,1):
        name = ev['medicamento']
        if ev['status'] == 'FORA_DA_REFERENCIA':
            alerts.append({
                'type':'posologia', 'severity':ev.get('severity','grave'),
                'title':(f'Possível excesso de dose: {name}' if ev.get('comparison_kind') == 'TRIAGEM_TETO_DOCUMENTAL'
                         else f"Dose fora da referência{' orientativa' if ev.get('comparison_kind') else ''}: {name}"),
                'effect':ev['message'],
                'recommendation':'Conferir a bula específica, a indicação e a dose; doses acima do teto documental bloqueiam a confirmação.',
                'source':ev.get('source','Referência documental cadastrada'),
                'review_date':ev.get('source_recorded_at',''), 'rule_version':RULE_VERSION,
                'rule_id':ev['rule_id']})
        elif ev['status'] == 'COMPARACAO_ORIENTATIVA':
            alerts.append({
                'type':'comparação orientativa', 'severity':'informação insuficiente',
                'title':f'Comparação orientativa de dose: {name}',
                'effect':ev['message'],
                'recommendation':'Conferir a bula da apresentação efetivamente utilizada. Dentro dos limites numéricos não significa prescrição segura.',
                'source':ev.get('source','Referência publicada'),
                'review_date':ev.get('source_recorded_at',''),
                'rule_version':RULE_VERSION, 'rule_id':ev['rule_id']})
        elif ev['status'] == 'NAO_VERIFICADA':
            alerts.append({
                'type':'posologia', 'severity':'informação insuficiente',
                'title':f'Posologia não verificada: {name}', 'effect':ev['message'],
                'recommendation':'Conferir a bula profissional e os dados clínicos. Ausência de alerta não comprova dose segura.',
                'source':'Referência posológica específica não cadastrada',
                'review_date':'', 'rule_version':RULE_VERSION,
                'rule_id':f'DOSE-PENDENTE-{i}'})
    # Preserva a salvaguarda pré-existente de limite parcial de anlodipino,
    # restrita a ADULTOS. Não marca a posologia como validada/compatível.
    patient_age = age_from_birth(patient['birth_date'] or '')
    if patient_age is not None and patient_age >= 18:
        for item in items:
            name = conn.execute('SELECT generic_name FROM medications WHERE id=?',
                                (item['medication_id'],)).fetchone()
            if not name or name['generic_name'].casefold() not in ('anlodipino','amlodipino'):
                continue
            if item.get('form_kind') != 'tablet' or item.get('route') != 'oral':
                continue
            try:
                mg = float(item['dose_quantity']) * float(item['strength_value'])
                times = {'24/24h':1,'1x pela manhã':1,'1x à noite':1,'12/12h':2,
                         '2x ao dia':2,'8/8h':3,'6/6h':4,'4/4h':6,'dose única':1}.get(item.get('frequency'))
                if mg > 10 or (times is not None and mg*times > 10):
                    alerts.append({'type':'posologia','severity':'grave',
                        'title':'Limite parcial de dose adulta: Anlodipino',
                        'effect':f'{mg:g} mg por administração; referência adulta usual de até 10 mg/dia. Esta checagem parcial não valida a prescrição.',
                        'recommendation':'Não confirmar. Conferir bula do produto, indicação e condições clínicas.',
                        'source':'DailyMed, Amlodipine Besylate: https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=a6fa364c-3ad6-4bf9-b9ee-5ec3b1a7eb55',
                        'review_date':'2026-11-09','rule_version':RULE_VERSION,
                        'rule_id':'DOSE-AMLODIPINO-LIMITE-ADULTO-01'})
            except (TypeError,ValueError,OverflowError):
                pass
    return alerts,evaluations


def _valid_ids(values):
    """IDs inteiros positivos; entradas legadas inválidas são ignoradas (sem causar erro 500)."""
    ids = []
    for value in values if isinstance(values, list) else []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0 and not isinstance(value, bool):
            ids.append(number)
    return ids


def analyze_prescription(conn, patient_id: int, draft_items: list[dict], include_dosage: bool = True):
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    if not patient:
        raise ValueError("Paciente não encontrado")
    active_ids = _valid_ids(jload(patient["active_medications"], []))
    draft_ids = [int(i["medication_id"]) for i in draft_items]
    all_ids = active_ids + draft_ids
    med_rows = conn.execute(
        f"SELECT * FROM medications WHERE id IN ({','.join('?' for _ in all_ids)})" if all_ids else "SELECT * FROM medications WHERE 0",
        all_ids,
    ).fetchall() if all_ids else []
    by_id = {m["id"]: m for m in med_rows}
    sequence = [by_id[i] for i in all_ids if i in by_id]
    alerts, dosage_status = dosage_alerts(conn, draft_items, patient) if include_dosage else ([], [])

    # Duplicidade de princípio ativo
    generic_seen = {}
    for med in sequence:
        key = fold(med["generic_name"])
        generic_seen.setdefault(key, []).append(med)
    for meds in generic_seen.values():
        if len(meds) > 1:
            alerts.append({
                "type": "duplicidade", "severity": "grave", "title": f"Duplicidade: {meds[0]['generic_name']}",
                "effect": "O mesmo princípio ativo está presente mais de uma vez entre medicamentos ativos e o rascunho.",
                "recommendation": "Revise as apresentações e confirme se a duplicidade é intencional.",
                "source": "Regra RN-008 do protótipo acadêmico", "review_date": "2026-07-31", "rule_version": RULE_VERSION,
                "rule_id": "RN-008"
            })

    # Alergia textual: compara sem acentos/caixa com princípio ativo, marca comercial
    # e classe farmacológica (quando o catálogo a informa). Termos com menos de 3
    # letras são ignorados para evitar coincidências por substring.
    allergies = [fold(x) for x in jload(patient["allergies"], []) if len(fold(x)) >= 3]
    allergy_aliases = {"aas": "acido acetilsalicilico", "aspirina": "acido acetilsalicilico"}
    allergies = [allergy_aliases.get(a, a) for a in allergies]
    for med in sequence:
        generic = fold(med["generic_name"])
        brand = fold(med["brand_name"])
        drug_class = fold(med["drug_class"])
        if drug_class in ("", "nao classificada"):
            drug_class = ""
        if any(a in generic or generic in a or (brand and (a in brand or brand in a))
               or (drug_class and a == drug_class)
               for a in allergies):
            alerts.append({
                "type": "alergia", "severity": "contraindicado", "title": f"Alergia registrada: {med['generic_name']}",
                "effect": "O medicamento corresponde a uma alergia informada no cadastro do paciente.",
                "recommendation": "Interrompa a conclusão do rascunho e revise o cadastro/conduta com profissional habilitado.",
                "source": "Cadastro do paciente + regra RF-025", "review_date": patient["updated_at"][:10], "rule_version": RULE_VERSION,
                "rule_id": "RF-025"
            })

    if patient["allergy_status"] == "nao_informada":
        alerts.append({
            "type": "dados clínicos incompletos", "severity": "informação insuficiente",
            "title": "Alergias não investigadas",
            "effect": "A ausência de registro não significa ausência de alergia medicamentosa.",
            "recommendation": "Investigar e atualizar alergias do paciente antes de concluir a avaliação clínica.",
            "source": "Ficha clínica do paciente", "review_date": patient["updated_at"][:10],
            "rule_version": RULE_VERSION, "rule_id": "FICHA-ALERGIA"
        })

    # Motor conservador de condições preexistentes. Não confundir alerta com contraindicação automática.
    # Usa palavras inteiras: "rim" não deve casar com "primária", nem "renal" com "adrenal".
    condition_patterns = {
        "gravidez": re.compile(r"\b(gravidez|gravida|gestante|gestacao|gestacional|gestando)\b"),
        "renal": re.compile(r"\b(renal|renais|rim|rins|nefropatia|nefropatias|dialise|dialitico|irc|drc)\b"),
        "diabetes": re.compile(r"\b(diabetes|diabetico|diabetica|dm|dm1|dm2)\b|\bdm\s*tipo\b"),
    }
    raw_conditions = [fold(x) for x in jload(patient["conditions"], []) if isinstance(x, str)]
    condition_flags = {flag for condition in raw_conditions
                       for flag, pattern in condition_patterns.items() if pattern.search(condition)}
    condition_rules = json.loads((ROOT / "condition_rules.json").read_text(encoding="utf-8"))
    covered = set()
    for rule in condition_rules:
        if rule["condition"] not in condition_flags:
            continue
        for med in {m["generic_name"] for m in sequence}:
            if med not in rule["medications"]:
                continue
            covered.add((rule["condition"], med))
            alerts.append({
                "type": "condição clínica", "severity": rule["severity"],
                "title": f"{rule['title']} ({med})", "effect": rule["effect"],
                "recommendation": rule["recommendation"],
                "source": f"{rule['source']} | {rule['url']}",
                "review_date": "2026-11-08", "rule_version": RULE_VERSION,
                "rule_id": rule["id"]
            })
    # Sem cobertura não significa ausência de risco: alertar explicitamente por medicamento e condição.
    for condition in sorted(condition_flags):
        for med in {m["generic_name"] for m in sequence}:
            if (condition, med) in covered:
                continue
            alerts.append({
                "type": "lacuna de cobertura", "severity": "informação insuficiente",
                "title": f"Sem regra validada: {med} / {condition}",
                "effect": "Não há, nesta versão, regra específica revisada para esta combinação medicamento-condição. Isso NÃO indica segurança.",
                "recommendation": "Conferir bula específica (ANVISA) e dados clínicos antes de avaliar a prescrição.",
                "source": "Inventário de lacunas Dose Safe 2.3; consultar Bulário ANVISA: https://www.gov.br/anvisa/pt-br/sistemas/bulario-eletronico",
                "review_date": "2026-11-08", "rule_version": RULE_VERSION,
                "rule_id": "COND-PENDENTE"
            })

    rules = conn.execute("SELECT * FROM interactions WHERE active=1").fetchall()
    rule_map = {}
    for r in rules:
        k = tuple(sorted((fold(r["med_a_generic"]), fold(r["med_b_generic"]))))
        rule_map[k] = r

    unique_pairs = set()
    for i in range(len(sequence)):
        for j in range(i + 1, len(sequence)):
            a, b = sequence[i], sequence[j]
            pair_ids = tuple(sorted((a["id"], b["id"])))
            if pair_ids in unique_pairs:
                continue
            unique_pairs.add(pair_ids)
            k = tuple(sorted((fold(a["generic_name"]), fold(b["generic_name"]))))
            r = rule_map.get(k)
            if r:
                alerts.append({
                    "type": "interação", "severity": r["severity"],
                    "title": f"{a['generic_name']} + {b['generic_name']}", "effect": r["effect"],
                    "recommendation": r["recommendation"], "source": r["source"], "review_date": r["review_date"],
                    "rule_version": r["rule_version"], "rule_id": f"INT-{r['id']:03d}"
                })

    distinct_med_ids = set(all_ids)
    count = len(distinct_med_ids)
    if count >= 10:
        poly = "hiperpolifarmácia"
    elif count >= 5:
        poly = "polifarmácia"
    else:
        poly = "abaixo do limiar de polifarmácia"

    alerts.sort(key=lambda x: (severity_rank(x["severity"]), x["title"]))
    counts = {k: 0 for k in ["contraindicado", "grave", "moderado", "leve", "informação insuficiente"]}
    for a in alerts:
        counts[a["severity"]] = counts.get(a["severity"], 0) + 1
    return {
        "alerts": alerts,
        "dosage_evaluations": dosage_status,
        "summary": {
            "active_medication_count": count,
            "polypharmacy": poly,
            "pairs_evaluated": len(unique_pairs),
            "counts": counts,
            "rule_version": RULE_VERSION,
            "posology_coverage": {status: sum(1 for item in dosage_status if item['status'] == status)
                 for status in ('COMPATIVEL_COM_REFERENCIA','COMPARACAO_ORIENTATIVA','FORA_DA_REFERENCIA','NAO_VERIFICADA')},
            "message": "Nenhuma interação cadastrada/encontrada não significa combinação comprovadamente segura." if not alerts else "Alertas identificados na base acadêmica demonstrativa. Revise cada item e a fonte indicada."
        }
    }


def calculate_specific_reference(conn, patient_id, medication_id, indication, egfr):
    """Academic reference calculation; never returns an automatic prescription dose."""
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    medication = conn.execute("SELECT generic_name FROM medications WHERE id=? AND active=1", (medication_id,)).fetchone()
    if not patient or not medication:
        raise ApiError(404, "Paciente ou medicamento não encontrado")
    med_name = unicodedata.normalize('NFKD', medication['generic_name'].casefold())
    med_name = ''.join(c for c in med_name if not unicodedata.combining(c))
    if 'losartana' not in med_name and 'losartan' not in med_name:
        raise ApiError(422, "Não existe regra de cálculo específico documentada para este medicamento")
    if indication != 'hipertensao_pediatrica':
        raise ApiError(422, "Cálculo disponível somente para hipertensão pediátrica")
    age = age_from_birth(patient['birth_date'] or '')
    try:
        weight = float(patient['weight_kg'])
        kidney = float(egfr)
    except (TypeError, ValueError, OverflowError):
        raise ApiError(422, "Peso registrado e TFGe atual são obrigatórios")
    if age is None or not (6 <= age < 18):
        raise ApiError(422, "A referência de losartana se aplica apenas a pacientes de 6 a 17 anos")
    if not (0 < weight <= 200) or not (30 <= kidney <= 200):
        raise ApiError(422, "Peso inválido ou TFGe inferior a 30/fora do intervalo esperado; cálculo indisponível")
    # DailyMed, section 2.1: pediatric hypertension 0.7 mg/kg once/day, max initial 50 mg.
    # This is a label reference only, not selection of an actual prescription dose.
    theoretical = weight * 0.7
    return {
        'medication': medication['generic_name'],
        'indication': 'Hipertensão pediátrica (6 a 17 anos)',
        'age_years': age,
        'weight_kg': weight,
        'egfr_ml_min_1_73m2': kidney,
        'reference_mg_kg_per_day': 0.7,
        'uncapped_reference_mg_day': round(theoretical, 2),
        'label_initial_limit_mg_day': 50,
        'reference_capped_mg_day': round(min(theoretical, 50), 2),
        'frequency': 'uma vez ao dia',
        'source': 'DailyMed — Losartan potassium, seção 2.1',
        'source_url': 'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=c565e7ba-97aa-4a65-80e6-543e9af6e1c4',
        'notice': 'Referência matemática da bula, NÃO é dose prescrita. Confirmar indicação, pressão arterial, potássio, função renal, apresentação e supervisão profissional. Não aplicada automaticamente à receita.'
    }
