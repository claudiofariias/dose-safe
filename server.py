from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import unicodedata
import sqlite3
import time
import traceback
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend" / "dist"
DB_PATH = Path(os.environ.get("DOSE_SAFE_DB_PATH", str(ROOT / "dose_safe.db")))
SESSION_TTL_SECONDS = 60 * 60 * 8
RULE_VERSION = "2.3-academico-condicoes-parcial"
APP_VERSION = "1.5.0"
SCHEMA_VERSION = "1"


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(key).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, salt_b64, key_b64 = encoded.split("$", 2)
        if algo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(key_b64)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def jdump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def jload(value, default=None):
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def age_from_birth(birth_date: str) -> int | None:
    try:
        born = datetime.strptime(birth_date, "%Y-%m-%d").date()
        today = datetime.now().date()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except Exception:
        return None


def audit(conn, user_id, action, target_type, target_id=None, details=None):
    conn.execute(
        "INSERT INTO audit(user_id, action, target_type, target_id, created_at, details) VALUES(?,?,?,?,?,?)",
        (user_id, action, target_type, target_id, now_iso(), jdump(details or {})),
    )


def init_db():
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          email TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('student','professional','admin')),
          specialty TEXT,
          crm TEXT,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          token TEXT PRIMARY KEY,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS patients (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          owner_user_id INTEGER NOT NULL REFERENCES users(id),
          code TEXT NOT NULL UNIQUE,
          name TEXT NOT NULL,
          birth_date TEXT,
          sex TEXT,
          weight_kg REAL,
          height_cm REAL,
          weight_date TEXT,
          allergies TEXT NOT NULL DEFAULT '[]',
          conditions TEXT NOT NULL DEFAULT '[]',
          active_medications TEXT NOT NULL DEFAULT '[]',
          active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS medications (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          generic_name TEXT NOT NULL,
          brand_name TEXT,
          form TEXT NOT NULL,
          concentration_mg_ml REAL,
          route TEXT NOT NULL,
          drug_class TEXT,
          source TEXT NOT NULL,
          source_version TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS interactions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          med_a_generic TEXT NOT NULL,
          med_b_generic TEXT NOT NULL,
          severity TEXT NOT NULL,
          effect TEXT NOT NULL,
          recommendation TEXT NOT NULL,
          source TEXT NOT NULL,
          review_date TEXT NOT NULL,
          rule_version TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS prescriptions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          patient_id INTEGER NOT NULL REFERENCES patients(id),
          user_id INTEGER NOT NULL REFERENCES users(id),
          version INTEGER NOT NULL,
          status TEXT NOT NULL,
          items_json TEXT NOT NULL,
          alerts_json TEXT NOT NULL,
          justification TEXT,
          rule_version TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS adherence_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          patient_id INTEGER NOT NULL REFERENCES patients(id),
          prescription_id INTEGER REFERENCES prescriptions(id),
          scheduled_at TEXT NOT NULL,
          recorded_at TEXT,
          status TEXT NOT NULL CHECK(status IN ('taken','late','missed','planned')),
          note TEXT,
          created_by INTEGER NOT NULL REFERENCES users(id),
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER REFERENCES users(id),
          action TEXT NOT NULL,
          target_type TEXT NOT NULL,
          target_id INTEGER,
          created_at TEXT NOT NULL,
          details TEXT NOT NULL
        );
        """
    )

    # Migração não destrutiva para distinguir alergia não investigada da ausência relatada.
    patient_columns = {row["name"] for row in conn.execute("PRAGMA table_info(patients)")}
    if "allergy_status" not in patient_columns:
        conn.execute("ALTER TABLE patients ADD COLUMN allergy_status TEXT NOT NULL DEFAULT 'nao_informada'")
        conn.execute("UPDATE patients SET allergy_status='informada' WHERE allergies != '[]'")

    if conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0:
        if os.environ.get("DOSE_SAFE_PRODUCTION") == "1":
            email = os.environ.get("DOSE_SAFE_ADMIN_EMAIL", "").strip().lower()
            password = os.environ.get("DOSE_SAFE_ADMIN_PASSWORD", "")
            if not email or len(password) < 12:
                raise RuntimeError("Configure DOSE_SAFE_ADMIN_EMAIL e DOSE_SAFE_ADMIN_PASSWORD (12+ caracteres) na Railway.")
            conn.execute(
                "INSERT INTO users(name,email,password_hash,role,specialty,crm,created_at) VALUES(?,?,?,?,?,?,?)",
                ("Administrador Dose Safe", email, hash_password(password), "admin", "Administração", None, now_iso()),
            )
        else:
            conn.execute(
                "INSERT INTO users(name,email,password_hash,role,specialty,crm,created_at) VALUES(?,?,?,?,?,?,?)",
                ("Claudio Farias", "claudio@dosesafe.local", hash_password("DoseSafe123!"), "professional", "Infectologia Clínica", "CRM 123456-SP", now_iso()),
            )
            conn.execute(
                "INSERT INTO users(name,email,password_hash,role,specialty,crm,created_at) VALUES(?,?,?,?,?,?,?)",
                ("Administrador Dose Safe", "admin@dosesafe.local", hash_password("Admin123!"), "admin", "Administração", None, now_iso()),
            )

    if conn.execute("SELECT COUNT(*) c FROM medications").fetchone()["c"] == 0:
        meds = [
            ("Dipirona", "Novalgina", "Comprimido", None, "oral", "analgésico", "Base acadêmica Dose Safe / referência de demonstração", RULE_VERSION),
            ("Ibuprofeno", "Advil", "Comprimido", None, "oral", "AINE", "Base acadêmica Dose Safe / referência de demonstração", RULE_VERSION),
            ("Sertralina", "Zoloft", "Comprimido", None, "oral", "ISRS", "Base acadêmica Dose Safe / referência de demonstração", RULE_VERSION),
            ("Varfarina", "Marevan", "Comprimido", None, "oral", "anticoagulante", "Base acadêmica Dose Safe / referência de demonstração", RULE_VERSION),
            ("Fluconazol", "Zoltec", "Cápsula", None, "oral", "antifúngico azólico", "Base acadêmica Dose Safe / referência de demonstração", RULE_VERSION),
            ("Sinvastatina", "Zocor", "Comprimido", None, "oral", "estatina", "Base acadêmica Dose Safe / referência de demonstração", RULE_VERSION),
            ("Anlodipino", "Norvasc", "Comprimido", None, "oral", "bloqueador de canal de cálcio", "Base acadêmica Dose Safe / referência de demonstração", RULE_VERSION),
            ("Amoxicilina", "Amoxil", "Suspensão", 50.0, "oral", "penicilina", "Base acadêmica Dose Safe / referência de demonstração", RULE_VERSION),
            ("Paracetamol", "Tylenol", "Solução", 32.0, "oral", "analgésico", "Base acadêmica Dose Safe / referência de demonstração", RULE_VERSION),
            ("Losartana", "Cozaar", "Comprimido", None, "oral", "BRA", "Base acadêmica Dose Safe / referência de demonstração", RULE_VERSION),
            ("Metformina", "Glifage", "Comprimido", None, "oral", "biguanida", "Base acadêmica Dose Safe / referência de demonstração", RULE_VERSION),
        ]
        conn.executemany(
            "INSERT INTO medications(generic_name,brand_name,form,concentration_mg_ml,route,drug_class,source,source_version) VALUES(?,?,?,?,?,?,?,?)",
            meds,
        )

    if conn.execute("SELECT COUNT(*) c FROM interactions").fetchone()["c"] == 0:
        rules = [
            ("Varfarina", "Fluconazol", "grave", "Pode elevar o efeito anticoagulante e aumentar o risco de sangramento.", "Revisar a combinação e a necessidade de monitorização conforme a fonte clínica aplicável.", "Regra acadêmica demonstrativa; validar em fonte clínica oficial/licenciada", "2026-07-31", RULE_VERSION),
            ("Sertralina", "Ibuprofeno", "moderado", "Pode aumentar o risco de sangramento gastrointestinal.", "Revisar risco individual e monitorização conforme a fonte clínica aplicável.", "Regra acadêmica demonstrativa; validar em fonte clínica oficial/licenciada", "2026-07-31", RULE_VERSION),
            ("Sinvastatina", "Anlodipino", "moderado", "Pode elevar exposição à sinvastatina e risco de miopatia.", "Revisar dose e conduta conforme a fonte clínica aplicável.", "Regra acadêmica demonstrativa; validar em fonte clínica oficial/licenciada", "2026-07-31", RULE_VERSION),
        ]
        conn.executemany(
            "INSERT INTO interactions(med_a_generic,med_b_generic,severity,effect,recommendation,source,review_date,rule_version) VALUES(?,?,?,?,?,?,?,?)",
            rules,
        )

    # Expansão idempotente: preserva os IDs e dados já cadastrados.
    catalog = json.loads((ROOT / "catalog_100.json").read_text(encoding="utf-8"))
    known = {r[0].casefold() for r in conn.execute("SELECT generic_name FROM medications")}
    for med in catalog:
        if med["generic_name"].casefold() not in known:
            conn.execute("""INSERT INTO medications(generic_name,brand_name,form,concentration_mg_ml,route,drug_class,source,source_version)
                VALUES(?,?,?,?,?,?,?,?)""", tuple(med[k] for k in ("generic_name","brand_name","form","concentration_mg_ml","route","drug_class","source","source_version")))
    # As regras são EXEMPLOS não validados, para demonstração e testes.
    known_pairs = {tuple(sorted((r[0].casefold(), r[1].casefold()))) for r in conn.execute("SELECT med_a_generic,med_b_generic FROM interactions")}
    for rule in json.loads((ROOT / "interaction_examples.json").read_text(encoding="utf-8")):
        key = tuple(sorted((rule["med_a_generic"].casefold(), rule["med_b_generic"].casefold())))
        if key not in known_pairs:
            conn.execute("""INSERT INTO interactions(med_a_generic,med_b_generic,severity,effect,recommendation,source,review_date,rule_version)
                VALUES(?,?,?,?,?,?,?,?)""", tuple(rule[k] for k in ("med_a_generic","med_b_generic","severity","effect","recommendation","source","review_date","rule_version")))
            known_pairs.add(key)

    if conn.execute("SELECT COUNT(*) c FROM patients").fetchone()["c"] == 0:
        owner = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()["id"]
        med_ids = {r["generic_name"]: r["id"] for r in conn.execute("SELECT id,generic_name FROM medications")}
        patients = [
            (owner, "L-402", "Maria Socorro Silva", "1962-03-12", "Feminino", 53.0, 158.0, "2026-06-10", ["Dipirona"], ["Diabetes"], [med_ids["Metformina"]]),
            (owner, "L-405", "Ana Rocha", "1978-08-04", "Feminino", 68.0, 166.0, "2026-06-10", [], ["Hipertensão"], [med_ids["Losartana"]]),
            (owner, "L-410", "João Pereira", "1973-01-17", "Masculino", 81.0, 174.0, "2026-06-10", [], [], [med_ids["Ibuprofeno"], med_ids["Sertralina"]]),
        ]
        for p in patients:
            conn.execute(
                """INSERT INTO patients(owner_user_id,code,name,birth_date,sex,weight_kg,height_cm,weight_date,allergies,conditions,active_medications,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*p[:8], jdump(p[8]), jdump(p[9]), jdump(p[10]), now_iso(), now_iso()),
            )
    conn.commit()
    conn.close()


def med_to_dict(row):
    return {
        "id": row["id"], "generic_name": row["generic_name"], "brand_name": row["brand_name"],
        "form": row["form"], "concentration_mg_ml": row["concentration_mg_ml"], "route": row["route"],
        "drug_class": row["drug_class"], "source": row["source"], "source_version": row["source_version"]
    }


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


def analyze_prescription(conn, patient_id: int, draft_items: list[dict]):
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    if not patient:
        raise ValueError("Paciente não encontrado")
    active_ids = [int(x) for x in jload(patient["active_medications"], [])]
    draft_ids = [int(i["medication_id"]) for i in draft_items]
    all_ids = active_ids + draft_ids
    med_rows = conn.execute(
        f"SELECT * FROM medications WHERE id IN ({','.join('?' for _ in all_ids)})" if all_ids else "SELECT * FROM medications WHERE 0",
        all_ids,
    ).fetchall() if all_ids else []
    by_id = {m["id"]: m for m in med_rows}
    sequence = [by_id[i] for i in all_ids if i in by_id]
    alerts = []

    # Duplicidade de princípio ativo
    generic_seen = {}
    for med in sequence:
        key = med["generic_name"].strip().lower()
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

    # Alergia textual demonstrativa
    allergies = [str(x).strip().lower() for x in jload(patient["allergies"], [])]
    for med in sequence:
        generic = med["generic_name"].lower()
        brand = (med["brand_name"] or "").lower()
        if any(a and (a in generic or a in brand or generic in a) for a in allergies):
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
    def normalize_condition(value):
        value = unicodedata.normalize("NFKD", str(value).casefold())
        return "".join(c for c in value if not unicodedata.combining(c))

    raw_conditions = [normalize_condition(x) for x in jload(patient["conditions"], [])]
    condition_flags = set()
    for condition in raw_conditions:
        if any(t in condition for t in ("gravid", "gestant", "gestac")):
            condition_flags.add("gravidez")
        if any(t in condition for t in ("renal", "rim", "rins", "nefropat", "dialise", "insuficiencia dos rins")):
            condition_flags.add("renal")
        if any(t in condition for t in ("diabet", "dm tipo", "dm1", "dm2")):
            condition_flags.add("diabetes")
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
        k = tuple(sorted((r["med_a_generic"].lower(), r["med_b_generic"].lower())))
        rule_map[k] = r

    unique_pairs = set()
    for i in range(len(sequence)):
        for j in range(i + 1, len(sequence)):
            a, b = sequence[i], sequence[j]
            pair_ids = tuple(sorted((a["id"], b["id"])))
            if pair_ids in unique_pairs:
                continue
            unique_pairs.add(pair_ids)
            k = tuple(sorted((a["generic_name"].lower(), b["generic_name"].lower())))
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
        "summary": {
            "active_medication_count": count,
            "polypharmacy": poly,
            "pairs_evaluated": len(unique_pairs),
            "counts": counts,
            "rule_version": RULE_VERSION,
            "message": "Nenhuma interação cadastrada/encontrada não significa combinação comprovadamente segura." if not alerts else "Alertas identificados na base acadêmica demonstrativa. Revise cada item e a fonte indicada."
        }
    }


def calculate_dose(weight_kg, dose_mg_kg, times_per_day, concentration_mg_ml=None):
    vals = [weight_kg, dose_mg_kg, times_per_day]
    if any(v is None for v in vals):
        raise ValueError("Peso, dose por kg e frequência são obrigatórios")
    weight_kg, dose_mg_kg, times_per_day = float(weight_kg), float(dose_mg_kg), float(times_per_day)
    if weight_kg <= 0 or weight_kg > 350 or dose_mg_kg <= 0 or times_per_day <= 0 or times_per_day > 24:
        raise ValueError("Valores fora dos limites suportados pelo protótipo")
    per_dose = weight_kg * dose_mg_kg
    per_day = per_dose * times_per_day
    if per_dose > 5000:
        raise ValueError("Resultado fora do intervalo demonstrativo suportado; consulte protocolo/fonte apropriada")
    result = {
        "dose_per_administration_mg": round(per_dose, 3),
        "dose_per_day_mg": round(per_day, 3),
        "formula": f"{dose_mg_kg:g} mg/kg × {weight_kg:g} kg = {per_dose:g} mg por administração; × {times_per_day:g}/dia = {per_day:g} mg/dia",
        "rounding": "Sem arredondamento adicional"
    }
    if concentration_mg_ml not in (None, ""):
        c = float(concentration_mg_ml)
        if c <= 0 or c > 5000:
            raise ValueError("Concentração inválida")
        ml = per_dose / c
        result["volume_per_administration_ml"] = round(ml, 3)
        result["conversion_formula"] = f"{per_dose:g} mg ÷ {c:g} mg/mL = {ml:g} mL por administração"
    return result


class ApiError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


class Handler(BaseHTTPRequestHandler):
    server_version = "DoseSafe/1.0"

    def log_message(self, fmt, *args):
        print(f"[{now_iso()}] {self.address_string()} {fmt % args}")

    def send_json(self, status, payload, headers=None):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 2_000_000:
                raise ApiError(413, "Payload muito grande")
            body = self.rfile.read(length) if length else b"{}"
            return json.loads(body.decode("utf-8"))
        except ApiError:
            raise
        except Exception:
            raise ApiError(400, "JSON inválido")

    def session_user(self, required=True):
        cookie = SimpleCookie(self.headers.get("Cookie"))
        morsel = cookie.get("dose_safe_session")
        if not morsel:
            if required:
                raise ApiError(401, "Sessão não autenticada")
            return None
        token = morsel.value
        conn = db()
        row = conn.execute(
            """SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
               WHERE s.token=? AND s.expires_at>?""", (token, int(time.time()))
        ).fetchone()
        conn.close()
        if not row and required:
            raise ApiError(401, "Sessão expirada")
        return dict(row) if row else None

    def require_admin(self):
        user = self.session_user()
        if user["role"] != "admin":
            raise ApiError(403, "Acesso restrito ao administrador")
        return user

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET,POST,PUT,DELETE,OPTIONS")
        self.end_headers()

    def do_GET(self):
        try:
            self.handle_get()
        except ApiError as e:
            self.send_json(e.status, {"error": e.message})
        except Exception:
            traceback.print_exc()
            self.send_json(500, {"error": "Erro interno", "technical_id": secrets.token_hex(4)})

    def do_POST(self):
        try:
            self.handle_post()
        except ApiError as e:
            self.send_json(e.status, {"error": e.message})
        except Exception:
            traceback.print_exc()
            self.send_json(500, {"error": "Erro interno", "technical_id": secrets.token_hex(4)})

    def do_PUT(self):
        try:
            self.handle_put()
        except ApiError as e:
            self.send_json(e.status, {"error": e.message})
        except Exception:
            traceback.print_exc()
            self.send_json(500, {"error": "Erro interno", "technical_id": secrets.token_hex(4)})

    def handle_get(self):
        p = urlparse(self.path)
        path, qs = p.path, parse_qs(p.query)
        if path == "/api/health":
            return self.send_json(200, {"ok": True, "app_version": APP_VERSION, "schema_version": SCHEMA_VERSION, "rule_version": RULE_VERSION})
        if path == "/api/auth/me":
            user = self.session_user(False)
            return self.send_json(200, {"user": self.public_user(user) if user else None})
        if path.startswith("/api/prescriptions/") and path.endswith("/pdf"):
            user = self.session_user()
            parts = path.strip("/").split("/")
            if len(parts) != 4 or parts[:2] != ["api", "prescriptions"] or not parts[2].isdigit():
                raise ApiError(404, "Prescrição não encontrada")
            prescription_id = int(parts[2])
            conn = db()
            try:
                where_user = "" if user["role"] == "admin" else " AND p.user_id=?"
                args = (prescription_id,) if user["role"] == "admin" else (prescription_id, user["id"])
                row = conn.execute("""SELECT p.*, pa.name patient_name, pa.code patient_code,
                    pa.birth_date patient_birth_date, u.name prescriber_name,
                    u.crm prescriber_crm, u.specialty prescriber_specialty
                    FROM prescriptions p JOIN patients pa ON pa.id=p.patient_id
                    JOIN users u ON u.id=p.user_id
                    WHERE p.id=?""" + where_user, args).fetchone()
                if not row:
                    raise ApiError(404, "Prescrição não encontrada")
                from receipt_pdf import build_receipt_pdf
                items = jload(row["items_json"], [])
                medication_ids = [int(x.get("medication_id") or 0) for x in items]
                medicines = {}
                if medication_ids:
                    marks = ",".join("?" for _ in medication_ids)
                    medicines = {r["id"]: dict(r) for r in conn.execute(
                        f"SELECT * FROM medications WHERE id IN ({marks})", medication_ids)}
                receipt = build_receipt_pdf(
                    {"id": row["id"], "version": row["version"], "items": items,
                     "alerts": jload(row["alerts_json"], []), "justification": row["justification"],
                     "created_at": row["created_at"], "rule_version": row["rule_version"]},
                    {"name": row["patient_name"], "code": row["patient_code"],
                     "birth_date": row["patient_birth_date"]},
                    {"name": row["prescriber_name"], "crm": row["prescriber_crm"],
                     "specialty": row["prescriber_specialty"]}, medicines)
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'attachment; filename="dose-safe-prescricao-{prescription_id}.pdf"')
                self.send_header("Content-Length", str(len(receipt)))
                self.send_header("Cache-Control", "private, no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(receipt)
                return
            finally:
                conn.close()
        if path.startswith("/api/"):
            user = self.session_user()
            conn = db()
            try:
                if path == "/api/dashboard":
                    owner_clause, args = self.owner_scope(user)
                    patients = conn.execute(f"SELECT * FROM patients WHERE active=1 {owner_clause} ORDER BY updated_at DESC LIMIT 3", args).fetchall()
                    today = datetime.now().date().isoformat()
                    count = conn.execute("SELECT COUNT(*) c FROM prescriptions WHERE user_id=? AND substr(created_at,1,10)=?", (user["id"], today)).fetchone()["c"]
                    alerts = conn.execute("SELECT alerts_json FROM prescriptions WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (user["id"],)).fetchall()
                    alert_count = sum(len(jload(r["alerts_json"], [])) for r in alerts)
                    return self.send_json(200, {"recent_patients": [patient_to_dict(x) for x in patients], "prescriptions_today": count, "recent_alert_count": alert_count})
                if path == "/api/patients":
                    owner_clause, args = self.owner_scope(user)
                    rows = conn.execute(f"SELECT * FROM patients WHERE active=1 {owner_clause} ORDER BY updated_at DESC", args).fetchall()
                    return self.send_json(200, {"patients": [patient_to_dict(r) for r in rows]})
                if path.startswith("/api/patients/"):
                    pid = int(path.rsplit("/", 1)[1])
                    row = conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
                    if not row or (user["role"] != "admin" and row["owner_user_id"] != user["id"]):
                        raise ApiError(404, "Paciente não encontrado")
                    return self.send_json(200, {"patient": patient_to_dict(row)})
                if path == "/api/medications":
                    q = (qs.get("q", [""])[0] or "").strip()
                    if q:
                        rows = conn.execute("SELECT * FROM medications WHERE active=1 AND (generic_name LIKE ? OR brand_name LIKE ?) ORDER BY generic_name LIMIT 30", (f"%{q}%", f"%{q}%")).fetchall()
                    else:
                        rows = conn.execute("SELECT * FROM medications WHERE active=1 ORDER BY generic_name").fetchall()
                    return self.send_json(200, {"medications": [med_to_dict(r) for r in rows], "rule_version": RULE_VERSION})
                if path == "/api/prescriptions":
                    owner_clause = "" if user["role"] == "admin" else "WHERE p.user_id=?"
                    args = () if user["role"] == "admin" else (user["id"],)
                    rows = conn.execute(f"""SELECT p.*, pa.name patient_name, pa.code patient_code FROM prescriptions p
                        JOIN patients pa ON pa.id=p.patient_id {owner_clause} ORDER BY p.created_at DESC LIMIT 100""", args).fetchall()
                    out = []
                    for r in rows:
                        out.append({"id": r["id"], "patient_id": r["patient_id"], "patient_name": r["patient_name"], "patient_code": r["patient_code"], "version": r["version"], "status": r["status"], "items": jload(r["items_json"], []), "alerts": jload(r["alerts_json"], []), "justification": r["justification"], "rule_version": r["rule_version"], "created_at": r["created_at"]})
                    return self.send_json(200, {"prescriptions": out})
                if path == "/api/adherence":
                    patient_id = int(qs.get("patient_id", [0])[0] or 0)
                    rows = conn.execute("SELECT * FROM adherence_events WHERE patient_id=? ORDER BY scheduled_at DESC", (patient_id,)).fetchall()
                    return self.send_json(200, {"events": [dict(r) for r in rows]})
                if path == "/api/admin/audit":
                    self.require_admin()
                    rows = conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 200").fetchall()
                    return self.send_json(200, {"events": [{**dict(r), "details": jload(r["details"], {})} for r in rows]})
            finally:
                conn.close()
            raise ApiError(404, "Endpoint não encontrado")
        return self.serve_static(path)

    def handle_post(self):
        path = urlparse(self.path).path
        if path == "/api/auth/login":
            data = self.read_json()
            email = str(data.get("email", "")).strip().lower()
            password = str(data.get("password", ""))
            conn = db()
            user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not user or not verify_password(password, user["password_hash"]):
                conn.close()
                raise ApiError(401, "E-mail ou senha inválidos")
            token = secrets.token_urlsafe(32)
            conn.execute("DELETE FROM sessions WHERE expires_at<=?", (int(time.time()),))
            conn.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES(?,?,?)", (token, user["id"], int(time.time()) + SESSION_TTL_SECONDS))
            audit(conn, user["id"], "login", "session", None, {})
            conn.commit(); conn.close()
            secure = "; Secure" if os.environ.get("DOSE_SAFE_PRODUCTION") == "1" else ""
            headers = {"Set-Cookie": f"dose_safe_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL_SECONDS}{secure}"}
            return self.send_json(200, {"user": self.public_user(dict(user))}, headers)
        if path == "/api/auth/register":
            data = self.read_json()
            required = ["name", "email", "password", "role"]
            if any(not str(data.get(k, "")).strip() for k in required):
                raise ApiError(400, "Preencha nome, e-mail, senha e tipo de perfil")
            if data["role"] not in ("student", "professional"):
                raise ApiError(400, "Tipo de perfil inválido")
            if len(str(data["password"])) < 8:
                raise ApiError(400, "A senha deve ter pelo menos 8 caracteres")
            conn = db()
            try:
                cur = conn.execute("INSERT INTO users(name,email,password_hash,role,specialty,crm,created_at) VALUES(?,?,?,?,?,?,?)", (
                    str(data["name"]).strip(), str(data["email"]).strip().lower(), hash_password(str(data["password"])), data["role"],
                    str(data.get("specialty") or "").strip() or None, str(data.get("crm") or "").strip() or None, now_iso()))
                audit(conn, cur.lastrowid, "create", "user", cur.lastrowid, {"role": data["role"]})
                conn.commit()
            except sqlite3.IntegrityError:
                conn.close(); raise ApiError(409, "E-mail já cadastrado")
            conn.close()
            return self.send_json(201, {"ok": True})
        user = self.session_user()
        data = self.read_json()
        conn = db()
        try:
            if path == "/api/auth/logout":
                cookie = SimpleCookie(self.headers.get("Cookie")); morsel = cookie.get("dose_safe_session")
                if morsel: conn.execute("DELETE FROM sessions WHERE token=?", (morsel.value,))
                audit(conn, user["id"], "logout", "session", None, {})
                conn.commit()
                return self.send_json(200, {"ok": True}, {"Set-Cookie": "dose_safe_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"})
            if path == "/api/patients":
                name = str(data.get("name", "")).strip()
                if not name: raise ApiError(400, "Nome é obrigatório")
                code = str(data.get("code") or f"L-{secrets.randbelow(900)+100}")
                cur = conn.execute("""INSERT INTO patients(owner_user_id,code,name,birth_date,sex,weight_kg,height_cm,weight_date,allergies,conditions,active_medications,created_at,updated_at,allergy_status)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (user["id"], code, name, data.get("birth_date"), data.get("sex"), data.get("weight_kg"), data.get("height_cm"), data.get("weight_date"), jdump(data.get("allergies", [])), jdump(data.get("conditions", [])), jdump(data.get("active_medications", [])), now_iso(), now_iso(), data.get("allergy_status", "nao_informada")))
                audit(conn, user["id"], "create", "patient", cur.lastrowid, {})
                conn.commit()
                row = conn.execute("SELECT * FROM patients WHERE id=?", (cur.lastrowid,)).fetchone()
                return self.send_json(201, {"patient": patient_to_dict(row)})
            if path == "/api/prescriptions/analyze":
                patient_id = int(data.get("patient_id") or 0)
                items = data.get("items") or []
                if not patient_id or not items: raise ApiError(400, "Paciente e ao menos um medicamento são obrigatórios")
                self.assert_patient_access(conn, user, patient_id)
                result = analyze_prescription(conn, patient_id, items)
                audit(conn, user["id"], "analyze", "prescription_draft", None, {"patient_id": patient_id, "item_count": len(items), "alert_count": len(result["alerts"])})
                conn.commit()
                return self.send_json(200, result)
            if path == "/api/prescriptions":
                patient_id = int(data.get("patient_id") or 0)
                items = data.get("items") or []
                if not patient_id or not items: raise ApiError(400, "Paciente e itens são obrigatórios")
                self.assert_patient_access(conn, user, patient_id)
                result = analyze_prescription(conn, patient_id, items)
                high = [a for a in result["alerts"] if a["severity"] in ("contraindicado", "grave")]
                justification = str(data.get("justification") or "").strip()
                if high and not data.get("reviewed"):
                    raise ApiError(409, "Análise explícita obrigatória antes de confirmar alertas graves/contraindicados.")
                if high and not justification:
                    raise ApiError(409, "Há alerta contraindicado/grave. Registre justificativa ou altere o rascunho antes de salvar.")
                latest = conn.execute("SELECT COALESCE(MAX(version),0) v FROM prescriptions WHERE patient_id=?", (patient_id,)).fetchone()["v"]
                cur = conn.execute("INSERT INTO prescriptions(patient_id,user_id,version,status,items_json,alerts_json,justification,rule_version,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (patient_id, user["id"], latest+1, "saved", jdump(items), jdump(result["alerts"]), justification or None, RULE_VERSION, now_iso()))
                audit(conn, user["id"], "save", "prescription", cur.lastrowid, {"version": latest+1, "rule_version": RULE_VERSION})
                conn.commit()
                return self.send_json(201, {"id": cur.lastrowid, "version": latest+1, **result})
            if path == "/api/dose/calculate":
                result = calculate_dose(data.get("weight_kg"), data.get("dose_mg_kg"), data.get("times_per_day"), data.get("concentration_mg_ml"))
                audit(conn, user["id"], "calculate", "dose", None, {"inputs": {k: data.get(k) for k in ("weight_kg","dose_mg_kg","times_per_day","concentration_mg_ml")}})
                conn.commit()
                return self.send_json(200, result)
            if path == "/api/adherence":
                patient_id = int(data.get("patient_id") or 0)
                if not patient_id or data.get("status") not in ("taken","late","missed","planned"):
                    raise ApiError(400, "Evento de adesão inválido")
                self.assert_patient_access(conn, user, patient_id)
                cur = conn.execute("INSERT INTO adherence_events(patient_id,prescription_id,scheduled_at,recorded_at,status,note,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)", (patient_id, data.get("prescription_id"), data.get("scheduled_at") or now_iso(), data.get("recorded_at") or now_iso(), data["status"], data.get("note"), user["id"], now_iso()))
                audit(conn, user["id"], "create", "adherence_event", cur.lastrowid, {"status": data["status"]})
                conn.commit()
                return self.send_json(201, {"id": cur.lastrowid})
            if path == "/api/admin/medications":
                self.require_admin()
                fields = ["generic_name","brand_name","form","concentration_mg_ml","route","drug_class","source","source_version"]
                if not data.get("generic_name") or not data.get("form") or not data.get("route") or not data.get("source"):
                    raise ApiError(400, "Campos obrigatórios ausentes")
                cur = conn.execute("INSERT INTO medications(generic_name,brand_name,form,concentration_mg_ml,route,drug_class,source,source_version) VALUES(?,?,?,?,?,?,?,?)", tuple(data.get(f) for f in fields))
                audit(conn, user["id"], "create", "medication", cur.lastrowid, {})
                conn.commit(); return self.send_json(201, {"id": cur.lastrowid})
            if path == "/api/admin/interactions":
                self.require_admin()
                req = ["med_a_generic","med_b_generic","severity","effect","recommendation","source","review_date"]
                if any(not data.get(k) for k in req): raise ApiError(400, "Campos obrigatórios ausentes")
                cur = conn.execute("INSERT INTO interactions(med_a_generic,med_b_generic,severity,effect,recommendation,source,review_date,rule_version) VALUES(?,?,?,?,?,?,?,?)", (data["med_a_generic"],data["med_b_generic"],data["severity"],data["effect"],data["recommendation"],data["source"],data["review_date"],RULE_VERSION))
                audit(conn,user["id"],"create","interaction",cur.lastrowid,{})
                conn.commit(); return self.send_json(201,{"id":cur.lastrowid})
            raise ApiError(404, "Endpoint não encontrado")
        finally:
            conn.close()

    def handle_put(self):
        path = urlparse(self.path).path
        user = self.session_user(); data = self.read_json(); conn = db()
        try:
            if path.startswith("/api/patients/"):
                pid = int(path.rsplit("/", 1)[1])
                row = conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
                if not row or (user["role"] != "admin" and row["owner_user_id"] != user["id"]): raise ApiError(404, "Paciente não encontrado")
                fields = ["name","birth_date","sex","weight_kg","height_cm","weight_date"]
                vals = [data.get(f, row[f]) for f in fields]
                allergies = data.get("allergies", jload(row["allergies"], [])); conditions = data.get("conditions", jload(row["conditions"], [])); meds = data.get("active_medications", jload(row["active_medications"], []))
                conn.execute("UPDATE patients SET name=?,birth_date=?,sex=?,weight_kg=?,height_cm=?,weight_date=?,allergies=?,conditions=?,active_medications=?,allergy_status=?,updated_at=? WHERE id=?", (*vals,jdump(allergies),jdump(conditions),jdump(meds),data.get("allergy_status", row["allergy_status"]),now_iso(),pid))
                audit(conn,user["id"],"update","patient",pid,{})
                conn.commit(); return self.send_json(200,{"ok":True})
            raise ApiError(404,"Endpoint não encontrado")
        finally:
            conn.close()

    def assert_patient_access(self, conn, user, patient_id):
        row = conn.execute("SELECT owner_user_id FROM patients WHERE id=?", (patient_id,)).fetchone()
        if not row or (user["role"] != "admin" and row["owner_user_id"] != user["id"]):
            raise ApiError(404, "Paciente não encontrado")

    def owner_scope(self, user):
        if user["role"] == "admin": return "", ()
        return "AND owner_user_id=?", (user["id"],)

    def public_user(self, u):
        if not u: return None
        return {"id":u["id"],"name":u["name"],"email":u["email"],"role":u["role"],"specialty":u.get("specialty") if isinstance(u,dict) else u["specialty"],"crm":u.get("crm") if isinstance(u,dict) else u["crm"]}

    def serve_static(self, path):
        if path in ("", "/"): path = "/index.html"
        candidate = (FRONTEND / path.lstrip("/")).resolve()
        if FRONTEND not in candidate.parents and candidate != FRONTEND:
            raise ApiError(403, "Acesso inválido")
        if not candidate.exists() or not candidate.is_file():
            candidate = FRONTEND / "index.html"
        content = candidate.read_bytes()
        ctype = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype in ("application/javascript","application/json") else ""))
        self.send_header("Content-Length", str(len(content)))
        # Protótipo em desenvolvimento: evita servir CSS/JS antigos do cache do navegador.
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        if candidate.name == "index.html":
            self.send_header("Clear-Site-Data", '"cache"')
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers(); self.wfile.write(content)


if __name__ == "__main__":
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    init_db()
    host = os.environ.get("DOSE_SAFE_HOST", "0.0.0.0" if os.environ.get("DOSE_SAFE_PRODUCTION") == "1" else "127.0.0.1")
    port = int(os.environ.get("PORT", os.environ.get("DOSE_SAFE_PORT", "8000")))
    print(f"Dose Safe {APP_VERSION} em http://{host}:{port}")
    if os.environ.get("DOSE_SAFE_PRODUCTION") != "1":
        print("Login demo: claudio@dosesafe.local / DoseSafe123!")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
