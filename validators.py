"""Validação de entrada e aritmética de dispensação (sem acesso a HTTP).

Funções levantam ApiError com mensagem em português para o cliente.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime

from common import fold
from errors import ApiError

SEXES = ("Feminino", "Masculino", "Outro")
ALLERGY_STATUSES = ("nao_informada", "nenhuma", "informada")
ADHERENCE_STATUSES = ("taken", "late", "missed", "planned")
INTERACTION_SEVERITIES = ("contraindicado", "grave", "moderado", "leve")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def expected_dispense_quantity(item):
    """Dispensing arithmetic; liquid bottles require explicitly supplied mL/bottle."""
    try:
        dose = float(item.get('dose_quantity'))
        if not (0 < dose <= 10000): return None
        daily = {'4/4h':6, '6/6h':4, '8/8h':3, '12/12h':2, '24/24h':1,
                 '1x pela manhã':1, '1x à noite':1, '2x ao dia':2}
        frequency, mode = item.get('frequency'), item.get('duration_mode')
        administrations = None
        if frequency == 'dose única' and mode == 'single':
            administrations = 1
        elif mode == 'days':
            days = float(item.get('duration_days'))
            if not days.is_integer() or days < 1: return None
            if frequency in daily: administrations = int(days) * daily[frequency]
            elif frequency == '1x por semana' and int(days) % 7 == 0: administrations = int(days) // 7
        if administrations is None: return None
        if item.get('form_kind') == 'liquid' and item.get('dose_unit') == 'mL' and item.get('dispense_unit') == 'frasco(s)':
            volume_raw = item.get('bottle_volume_ml')
            if volume_raw in (None, ''): return None
            volume = float(volume_raw)
            if not (0 < volume <= 10000): return None
            result = math.ceil(dose * administrations / volume - 1e-10)
        else:
            if item.get('dose_unit') != item.get('dispense_unit'): return None
            result = round(dose * administrations, 5)
        return result if 0 < result <= 100000 else None
    except (ValueError, TypeError, OverflowError):
        return None


def next_patient_code(conn):
    """Generate a unique sequential public identifier; SQLite UNIQUE is final defense."""
    existing = (row['code'] for row in conn.execute("SELECT code FROM patients WHERE code LIKE 'L-%'"))
    highest = max((int(match.group(1)) for code in existing
                   if (match := re.fullmatch(r'L-(\d+)', code))), default=99)
    return f'L-{highest+1}'


def validate_prescription_items(conn, items):
    """Reject incomplete/contradictory prescription entries; no inferred safe doses."""
    if not isinstance(items, list) or not (1 <= len(items) <= 30):
        raise ApiError(400, "A prescrição deve conter de 1 a 30 medicamentos")
    valid_frequencies = {"4/4h","6/6h","8/8h","12/12h","24/24h","1x pela manhã","1x à noite","2x ao dia","1x por semana","dose única"}
    valid_routes = {"oral","intramuscular","intravenosa"}
    valid_modes = {"days","months","continuous","single"}
    med_ids = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict): raise ApiError(400, f"Item {index}: formato inválido")
        try:
            med_id = int(item.get("medication_id"))
            quantity = float(item.get("dose_quantity"))
            dispense = float(item.get("dispense_quantity"))
            strength = float(item.get("strength_value"))
        except (ValueError, TypeError, OverflowError):
            raise ApiError(400, f"Item {index}: informe concentração, dose por administração e quantidade a dispensar")
        if med_id <= 0 or not (0 < quantity <= 10000) or not (0 < dispense <= 100000) or not (0 < strength <= 100000):
            raise ApiError(400, f"Item {index}: valores precisam ser positivos e dentro de limites técnicos")
        med_ids.append(med_id)
        kind = item.get("form_kind")
        unit = item.get("dose_unit")
        strength_unit = item.get("strength_unit")
        compatible = {"tablet": ("comprimido(s)","mg"), "liquid": ("mL","mg/mL"), "drops": ("gota(s)","mg/mL"), "ampoule": ("ampola(s)","mg/mL")}
        if kind not in compatible or (unit,strength_unit) != compatible[kind]:
            raise ApiError(400, f"Item {index}: apresentação, concentração e unidade incompatíveis")
        route = item.get("route")
        if route not in valid_routes or (kind in ("tablet","liquid","drops") and route != "oral") or (kind == "ampoule" and route not in ("intramuscular","intravenosa")):
            raise ApiError(400, f"Item {index}: via incompatível com a apresentação")
        frequency, mode = item.get("frequency"), item.get("duration_mode")
        if frequency not in valid_frequencies or mode not in valid_modes:
            raise ApiError(400, f"Item {index}: frequência ou duração inválida")
        if (frequency == "dose única") != (mode == "single"):
            raise ApiError(400, f"Item {index}: dose única deve ter duração dose única")
        if mode in ("days", "months"):
            try: duration = float(item.get("duration_days") if mode == "days" else item.get("duration_months"))
            except (TypeError, ValueError): raise ApiError(400, f"Item {index}: duração inválida")
            if duration <= 0 or duration > (3650 if mode == "days" else 120):
                raise ApiError(400, f"Item {index}: duração fora dos limites")
        if item.get('bottle_volume_ml') not in (None, ''):
            try: volume = float(item['bottle_volume_ml'])
            except (TypeError, ValueError, OverflowError): raise ApiError(400, f"Item {index}: volume do frasco inválido")
            if not (0 < volume <= 10000) or kind != 'liquid':
                raise ApiError(400, f"Item {index}: volume do frasco inválido para apresentação")
        expected = expected_dispense_quantity(item)
        dispense_mode = item.get('dispense_mode', 'manual')
        if dispense_mode not in ('auto', 'manual'):
            raise ApiError(400, f"Item {index}: modo de dispensação inválido")
        if dispense_mode == 'auto':
            if expected is None or abs(dispense - expected) > 0.00001:
                raise ApiError(400, f"Item {index}: quantidade calculada desatualizada; revise a dispensação")
        elif expected is not None and abs(dispense - expected) > 0.00001:
            reason = str(item.get('dispense_reason') or '').strip()
            # Prescrições antigas não traziam modo de dispensação nem justificativa.
            if 'dispense_mode' in item and len(reason) < 5:
                raise ApiError(400, f"Item {index}: justifique o ajuste manual da dispensação")
            if len(reason) > 500:
                raise ApiError(400, f"Item {index}: justificativa longa demais")
        if len(str(item.get('instruction') or '')) > 1000: raise ApiError(400, f"Item {index}: orientação muito longa")
        if len(str(item.get('indication') or '')) > 150:
            raise ApiError(400, f"Item {index}: indicação muito longa")
        if len(str(item.get('anvisa_registration') or '')) > 20:
            raise ApiError(400, f"Item {index}: registro do produto inválido")
        # Para gotas e ampolas, não se deduz mg/dose a partir de contagens sem fator validado.
        if kind in ("tablet", "liquid"):
            item["dose"] = round(quantity*strength, 5)
            item["unit"] = "mg"
        else:
            item["dose"] = None
            item["unit"] = None
    if len(set(med_ids)) != len(med_ids):
        raise ApiError(400, "Medicamento repetido: edite o item existente ou avalie a duplicidade")
    matches = conn.execute(f"SELECT id FROM medications WHERE active=1 AND id IN ({','.join('?' for _ in med_ids)})",med_ids).fetchall()
    if len(matches) != len(med_ids): raise ApiError(400, "Há medicamentos inexistentes ou inativos")
    return items


# --------------------------------------------------------------------------
# Entradas de paciente, conta e adesão
# --------------------------------------------------------------------------

def parse_int_id(value, label="Identificador", status=404):
    """Converte um ID vindo da URL/JSON; ID inválido vira 404 (URL) ou 400 (corpo), nunca 500."""
    try:
        if isinstance(value, bool):
            raise ValueError
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ApiError(status, f"{label} inválido" if status == 400 else f"{label} não encontrado")
    if number <= 0:
        raise ApiError(status, f"{label} inválido" if status == 400 else f"{label} não encontrado")
    return number


def _optional_date(value, label, allow_future=False, earliest=date(1900, 1, 1)):
    if value in (None, ""):
        return None
    try:
        parsed = datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        raise ApiError(400, f"{label} inválida: use o formato AAAA-MM-DD")
    if parsed < earliest or (not allow_future and parsed > date.today()):
        raise ApiError(400, f"{label} fora do intervalo permitido")
    return parsed.isoformat()


def _optional_number(value, label, low, high):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ApiError(400, f"{label} inválido")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ApiError(400, f"{label} inválido")
    if not math.isfinite(number) or not (low <= number <= high):
        raise ApiError(400, f"{label} deve estar entre {low:g} e {high:g}")
    return number


def _text_list(value, label, max_items=50, max_len=100):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > max_items:
        raise ApiError(400, f"{label}: formato inválido")
    seen, result = set(), []
    for entry in value:
        if not isinstance(entry, str) or not entry.strip() or len(entry.strip()) > max_len:
            raise ApiError(400, f"{label}: item inválido")
        text = entry.strip()
        if fold(text) not in seen:
            seen.add(fold(text))
            result.append(text)
    return result


def validate_patient_fields(conn, data, partial=False, existing_status=None):
    """Valida os campos de paciente presentes em `data`.

    Retorna somente as chaves validadas/normalizadas. Em `partial=True` (PUT) as
    ausentes são mantidas como estão; em POST, as ausentes recebem valor padrão.
    """
    if not isinstance(data, dict):
        raise ApiError(400, "Corpo da requisição inválido")
    out = {}
    if not partial or "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            raise ApiError(400, "Nome é obrigatório")
        if len(name) > 120:
            raise ApiError(400, "Nome muito longo")
        out["name"] = name
    if not partial or "birth_date" in data:
        out["birth_date"] = _optional_date(data.get("birth_date"), "Data de nascimento")
    if not partial or "sex" in data:
        sex = data.get("sex")
        if sex in ("", None):
            sex = None
        elif sex not in SEXES:
            raise ApiError(400, "Sexo inválido")
        out["sex"] = sex
    if not partial or "weight_kg" in data:
        out["weight_kg"] = _optional_number(data.get("weight_kg"), "Peso", 0.3, 500)
    if not partial or "height_cm" in data:
        out["height_cm"] = _optional_number(data.get("height_cm"), "Altura", 20, 272)
    if not partial or "weight_date" in data:
        out["weight_date"] = _optional_date(data.get("weight_date"), "Data da pesagem")
    if not partial or "allergies" in data:
        out["allergies"] = _text_list(data.get("allergies"), "Alergias")
    if not partial or "conditions" in data:
        out["conditions"] = _text_list(data.get("conditions"), "Condições")
    if not partial or "active_medications" in data:
        raw = data.get("active_medications")
        if raw is None:
            raw = []
        if not isinstance(raw, list) or len(raw) > 100:
            raise ApiError(400, "Medicamentos em uso: formato inválido")
        ids = []
        for entry in raw:
            ids.append(parse_int_id(entry, "Medicamento em uso", status=400) if not isinstance(entry, bool) else -1)
        ids = list(dict.fromkeys(ids))
        if ids:
            marks = ",".join("?" for _ in ids)
            found = {r[0] for r in conn.execute(f"SELECT id FROM medications WHERE id IN ({marks})", ids)}
            if len(found) != len(ids):
                raise ApiError(400, "Há medicamentos em uso inexistentes no catálogo")
        out["active_medications"] = ids
    if not partial or "allergy_status" in data or "allergies" in data:
        status = data.get("allergy_status")
        allergies = out.get("allergies")
        if status is None:
            status = "informada" if allergies else None
        if status is not None and status not in ALLERGY_STATUSES:
            raise ApiError(400, "Situação de alergias inválida")
        if allergies:
            status = "informada"  # alergia registrada nunca pode ficar como 'nenhuma'
        elif status == "informada" and allergies is not None:
            raise ApiError(400, "Informe a alergia ou selecione outra situação")
        if status is None and allergies == [] and existing_status == "informada":
            status = "nao_informada"  # a lista foi esvaziada: não manter 'informada' sem alergias
        if status is not None:
            out["allergy_status"] = status
        elif not partial:
            out["allergy_status"] = "nao_informada"
    return out


def validate_registration(data):
    if not isinstance(data, dict):
        raise ApiError(400, "Corpo da requisição inválido")
    if any(not str(data.get(k, "")).strip() for k in ("name", "email", "password", "role")):
        raise ApiError(400, "Preencha nome, e-mail, senha e tipo de perfil")
    if data["role"] not in ("student", "professional"):
        raise ApiError(400, "Tipo de perfil inválido")
    email = str(data["email"]).strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ApiError(400, "E-mail inválido")
    password = str(data["password"])
    if len(password) < 8:
        raise ApiError(400, "A senha deve ter pelo menos 8 caracteres")
    if len(password) > 200:
        raise ApiError(400, "A senha deve ter no máximo 200 caracteres")
    name = str(data["name"]).strip()
    specialty = str(data.get("specialty") or "").strip()
    crm = str(data.get("crm") or "").strip()
    if len(name) > 120 or len(specialty) > 100 or len(crm) > 60:
        raise ApiError(400, "Nome, especialidade ou CRM com tamanho acima do permitido")
    return {"name": name, "email": email, "password": password, "role": data["role"],
            "specialty": specialty or None, "crm": crm or None}


def _timestamp(value, label):
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, f"{label} inválido: use data/hora ISO 8601")
    return text


def validate_adherence(conn, data, patient_id):
    """Valida evento de adesão de um paciente cujo acesso já foi conferido."""
    if data.get("status") not in ADHERENCE_STATUSES:
        raise ApiError(400, "Evento de adesão inválido")
    prescription_id = data.get("prescription_id")
    if prescription_id in (None, ""):
        prescription_id = None
    else:
        prescription_id = parse_int_id(prescription_id, "Prescrição")
        row = conn.execute("SELECT 1 FROM prescriptions WHERE id=? AND patient_id=?",
                           (prescription_id, patient_id)).fetchone()
        if not row:
            raise ApiError(404, "Prescrição não encontrada para este paciente")
    note = data.get("note")
    if note is not None and (not isinstance(note, str) or len(note) > 500):
        raise ApiError(400, "Observação inválida ou longa demais")
    return {"prescription_id": prescription_id, "note": note or None,
            "scheduled_at": _timestamp(data.get("scheduled_at"), "Horário agendado"),
            "recorded_at": _timestamp(data.get("recorded_at"), "Horário registrado")}


def validate_interaction_rule(data):
    required = ("med_a_generic", "med_b_generic", "severity", "effect", "recommendation", "source", "review_date")
    if not isinstance(data, dict) or any(not str(data.get(k) or "").strip() for k in required):
        raise ApiError(400, "Campos obrigatórios ausentes")
    if fold(data["med_a_generic"]) == fold(data["med_b_generic"]):
        raise ApiError(400, "A interação deve envolver dois medicamentos diferentes")
    if data["severity"] not in INTERACTION_SEVERITIES:
        raise ApiError(400, "Gravidade inválida: " + ", ".join(INTERACTION_SEVERITIES))
    _optional_date(data["review_date"], "Data de revisão", allow_future=False)
    return {k: str(data[k]).strip() for k in required}
