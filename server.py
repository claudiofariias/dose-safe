"""Dose Safe — servidor HTTP e persistência (SQLite, somente biblioteca padrão).

Arquitetura:
  config.py      constantes e caminhos
  common.py      utilitários puros (datas, JSON, normalização de texto, auditoria)
  security.py    hash de senha e limitação de tentativas de login
  validators.py  validação de entradas e aritmética de dispensação
  analysis.py    motor de análise (dose, duplicidade, alergia, condições, interações)
  clinical_rules.py / dose_reference_screening.py  motor posológico
  receipt_pdf.py PDF acadêmico
  server.py      rotas HTTP, banco e inicialização

Os nomes públicos anteriores (server.db, server.init_db, server.DB_PATH, ...) continuam
disponíveis neste módulo por compatibilidade.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import sqlite3
import time
import traceback
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from analysis import (analyze_prescription, calculate_specific_reference, dosage_alerts,  # noqa: F401
                      patient_to_dict, severity_rank)
from clinical_rules import dosage_evaluations  # noqa: F401
from common import age_from_birth, audit, fold, jdump, jload, now_iso  # noqa: F401
from config import (APP_VERSION, FRONTEND, ROOT, RULE_VERSION, SCHEMA_VERSION,  # noqa: F401
                    SESSION_TTL_SECONDS)
from errors import ApiError
from security import LoginThrottle, hash_password, verify_password, verify_password_or_dummy  # noqa: F401
from validators import (expected_dispense_quantity, next_patient_code, parse_int_id,  # noqa: F401
                        validate_adherence, validate_interaction_rule, validate_patient_fields,
                        validate_prescription_items, validate_registration)

DB_PATH = Path(os.environ.get("DOSE_SAFE_DB_PATH", str(ROOT / "dose_safe.db")))
IS_PRODUCTION = lambda: os.environ.get("DOSE_SAFE_PRODUCTION") == "1"
LOGIN_THROTTLE = LoginThrottle()


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.create_function("fold", 1, fold, deterministic=True)
    return conn


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
          dosage_evaluations_json TEXT NOT NULL DEFAULT '[]',
          patient_snapshot_json TEXT NOT NULL DEFAULT '{}',
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

    # Migração não destrutiva: preserve os dados clínicos usados na análise
    # e o resultado posológico para que o PDF nunca reavalie regras futuras.
    prescription_columns = {row["name"] for row in conn.execute("PRAGMA table_info(prescriptions)")}
    if "dosage_evaluations_json" not in prescription_columns:
        conn.execute("ALTER TABLE prescriptions ADD COLUMN dosage_evaluations_json TEXT NOT NULL DEFAULT '[]'")
    if "patient_snapshot_json" not in prescription_columns:
        conn.execute("ALTER TABLE prescriptions ADD COLUMN patient_snapshot_json TEXT NOT NULL DEFAULT '{}'")

    if conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0:
        if IS_PRODUCTION():
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

    # Pacientes fictícios apenas fora de produção: nunca semear dados demonstrativos em produção.
    if not IS_PRODUCTION() and conn.execute("SELECT COUNT(*) c FROM patients").fetchone()["c"] == 0:
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
    # Índices de apoio (idempotentes). O índice único impede duas versões iguais
    # da mesma prescrição em gravações simultâneas; se houver legado duplicado, é ignorado.
    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_patients_owner ON patients(owner_user_id)",
        "CREATE INDEX IF NOT EXISTS idx_prescriptions_patient ON prescriptions(patient_id)",
        "CREATE INDEX IF NOT EXISTS idx_prescriptions_user_created ON prescriptions(user_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_adherence_patient ON adherence_events(patient_id, scheduled_at)",
        "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_prescriptions_patient_version ON prescriptions(patient_id, version)",
    ):
        try:
            conn.execute(statement)
        except sqlite3.DatabaseError as exc:
            print(f"Aviso: índice não criado ({exc}); execução segue sem ele.")
    conn.commit()
    conn.close()


def med_to_dict(row):
    return {
        "id": row["id"], "generic_name": row["generic_name"], "brand_name": row["brand_name"],
        "form": row["form"], "concentration_mg_ml": row["concentration_mg_ml"], "route": row["route"],
        "drug_class": row["drug_class"], "source": row["source"], "source_version": row["source_version"]
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "DoseSafe/1.0"
    timeout = 30  # evita conexões ociosas presas indefinidamente (slowloris)
    CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
           "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

    def security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", self.CSP)
        if IS_PRODUCTION():
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    def log_message(self, fmt, *args):
        print(f"[{now_iso()}] {self.address_string()} {fmt % args}")

    def send_json(self, status, payload, headers=None):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.security_headers()
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0:
                raise ApiError(400, "Content-Length inválido")
            if length > 2_000_000:
                raise ApiError(413, "Payload muito grande")
            body = self.rfile.read(length) if length else b"{}"
            data = json.loads(body.decode("utf-8"))
        except ApiError:
            raise
        except Exception:
            raise ApiError(400, "JSON inválido")
        if not isinstance(data, dict):
            raise ApiError(400, "O corpo da requisição deve ser um objeto JSON")
        return data

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
        self.send_header("Allow", "GET,POST,PUT,OPTIONS")
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
                snapshot = jload(row["patient_snapshot_json"], {})
                if snapshot:
                    pdf_patient = {**snapshot, "historical_snapshot": True}
                else:
                    # Em prescrições antigas, não presumir que o peso atual foi
                    # o peso utilizado na análise originalmente registrada.
                    pdf_patient = {"name": row["patient_name"], "code": row["patient_code"],
                                   "birth_date": row["patient_birth_date"], "historical_snapshot": False}
                receipt = build_receipt_pdf(
                    {"id": row["id"], "version": row["version"], "items": items,
                     "alerts": jload(row["alerts_json"], []),
                     "dosage_evaluations": jload(row["dosage_evaluations_json"], []),
                     "justification": row["justification"],
                     "created_at": row["created_at"], "rule_version": row["rule_version"]},
                    pdf_patient,
                    {"name": row["prescriber_name"], "crm": row["prescriber_crm"],
                     "specialty": row["prescriber_specialty"]}, medicines)
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'attachment; filename="dose-safe-prescricao-{prescription_id}.pdf"')
                self.send_header("Content-Length", str(len(receipt)))
                self.send_header("Cache-Control", "private, no-store")
                self.security_headers()
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
                    today = datetime.now(timezone.utc).date().isoformat()
                    count = conn.execute("SELECT COUNT(*) c FROM prescriptions WHERE user_id=? AND substr(created_at,1,10)=?", (user["id"], today)).fetchone()["c"]
                    alerts = conn.execute("SELECT alerts_json FROM prescriptions WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (user["id"],)).fetchall()
                    alert_count = sum(len(jload(r["alerts_json"], [])) for r in alerts)
                    return self.send_json(200, {"recent_patients": [patient_to_dict(x) for x in patients], "prescriptions_today": count, "recent_alert_count": alert_count})
                if path == "/api/patients":
                    owner_clause, args = self.owner_scope(user)
                    rows = conn.execute(f"SELECT * FROM patients WHERE active=1 {owner_clause} ORDER BY updated_at DESC", args).fetchall()
                    return self.send_json(200, {"patients": [patient_to_dict(r) for r in rows]})
                if path.startswith("/api/patients/"):
                    pid = parse_int_id(path.rsplit("/", 1)[1], "Paciente")
                    row = conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
                    if not row or (user["role"] != "admin" and row["owner_user_id"] != user["id"]):
                        raise ApiError(404, "Paciente não encontrado")
                    return self.send_json(200, {"patient": patient_to_dict(row)})
                if path == "/api/clinical/coverage":
                    from clinical_rules import load_documented_rules
                    review_queue_path = ROOT / "anvisa" / "fila_prioritaria.json"
                    clinical_catalog_path = ROOT / "anvisa" / "saidas" / "catalogo_anvisa_revisao.json"
                    queue = jload(review_queue_path.read_text(encoding="utf-8"), {}) if review_queue_path.exists() else {}
                    catalog_data = jload(clinical_catalog_path.read_text(encoding="utf-8"), {}) if clinical_catalog_path.exists() else {}
                    listed = catalog_data.get("medicamentos", [])
                    documented = load_documented_rules()
                    return self.send_json(200, {
                        "medicamentos_catalogo": len(json.loads((ROOT / "catalog_100.json").read_text(encoding="utf-8"))),
                        "medicamentos_com_candidatos": sum(1 for x in listed if x.get("registros_candidatos_csv")),
                        "total_prioritarios": len(queue.get("medicamentos", [])),
                        "referencias_dose_cadastradas": len(documented),
                        "medicamentos_com_referencias_dose": len(set(r['generic_name'] for r in documented)),
                        "nota": "Registros Anvisa não validam doses. Só referências documentadas por produto, apresentação e indicação são comparadas; uso acadêmico."})
                if path == "/api/medications":
                    q = (qs.get("q", [""])[0] or "").strip()
                    if q:
                        needle = fold(q)[:100]
                        rows = conn.execute("SELECT * FROM medications WHERE active=1 AND (instr(fold(generic_name), ?) > 0 OR instr(fold(brand_name), ?) > 0) ORDER BY generic_name LIMIT 30", (needle, needle)).fetchall()
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
                    patient_id = parse_int_id(qs.get("patient_id", [0])[0] or 0, "Paciente")
                    self.assert_patient_access(conn, user, patient_id)
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
            email = str(data.get("email", "")).strip().lower()[:254]
            password = str(data.get("password", ""))[:200]
            throttle_key = f"{email}|{self.client_address[0]}"
            wait = LOGIN_THROTTLE.retry_after(throttle_key)
            if wait:
                raise ApiError(429, f"Muitas tentativas de login. Tente novamente em {max(1, wait // 60)} minuto(s).")
            conn = db()
            user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not verify_password_or_dummy(password, user["password_hash"] if user else None):
                conn.close()
                LOGIN_THROTTLE.register_failure(throttle_key)
                raise ApiError(401, "E-mail ou senha inválidos")
            LOGIN_THROTTLE.reset(throttle_key)
            token = secrets.token_urlsafe(32)
            conn.execute("DELETE FROM sessions WHERE expires_at<=?", (int(time.time()),))
            conn.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES(?,?,?)", (token, user["id"], int(time.time()) + SESSION_TTL_SECONDS))
            audit(conn, user["id"], "login", "session", None, {})
            conn.commit(); conn.close()
            secure = "; Secure" if IS_PRODUCTION() else ""
            headers = {"Set-Cookie": f"dose_safe_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL_SECONDS}{secure}"}
            return self.send_json(200, {"user": self.public_user(dict(user))}, headers)
        if path == "/api/auth/register":
            data = self.read_json()
            account = validate_registration(data)
            conn = db()
            try:
                cur = conn.execute("INSERT INTO users(name,email,password_hash,role,specialty,crm,created_at) VALUES(?,?,?,?,?,?,?)", (
                    account["name"], account["email"], hash_password(account["password"]), account["role"],
                    account["specialty"], account["crm"], now_iso()))
                audit(conn, cur.lastrowid, "create", "user", cur.lastrowid, {"role": account["role"]})
                conn.commit()
            except sqlite3.IntegrityError:
                raise ApiError(409, "E-mail já cadastrado")
            finally:
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
                fields = validate_patient_fields(conn, data)
                # Bloqueia escritas simultâneas ao selecionar o próximo código.
                conn.execute("BEGIN IMMEDIATE")
                code = str(data.get("code") or next_patient_code(conn)).strip()
                if not re.fullmatch(r'L-\d+', code):
                    raise ApiError(400, 'Identificador do paciente inválido')
                if conn.execute("SELECT 1 FROM patients WHERE code=?", (code,)).fetchone():
                    raise ApiError(409, 'Identificador do paciente já existe')
                cur = conn.execute("""INSERT INTO patients(owner_user_id,code,name,birth_date,sex,weight_kg,height_cm,weight_date,allergies,conditions,active_medications,created_at,updated_at,allergy_status)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (user["id"], code, fields["name"], fields["birth_date"], fields["sex"], fields["weight_kg"], fields["height_cm"], fields["weight_date"], jdump(fields["allergies"]), jdump(fields["conditions"]), jdump(fields["active_medications"]), now_iso(), now_iso(), fields["allergy_status"]))
                audit(conn, user["id"], "create", "patient", cur.lastrowid, {})
                conn.commit()
                row = conn.execute("SELECT * FROM patients WHERE id=?", (cur.lastrowid,)).fetchone()
                return self.send_json(201, {"patient": patient_to_dict(row)})
            if path == "/api/prescriptions/screen":
                # Triagem antecipada: apenas medicamento + ficha clínica; sem validar posologia.
                patient_id = int(data.get("patient_id") or 0)
                raw_ids = data.get("medication_ids")
                if not patient_id or not isinstance(raw_ids, list) or not (1 <= len(raw_ids) <= 30):
                    raise ApiError(400, "Informe paciente e de 1 a 30 medicamentos")
                try:
                    med_ids = [int(value) for value in raw_ids]
                except (TypeError, ValueError, OverflowError):
                    raise ApiError(400, "Identificadores de medicamentos inválidos")
                if any(i <= 0 for i in med_ids) or len(set(med_ids)) != len(med_ids):
                    raise ApiError(400, "Medicamentos inválidos ou repetidos")
                self.assert_patient_access(conn, user, patient_id)
                found = conn.execute(f"SELECT id FROM medications WHERE active=1 AND id IN ({','.join('?' for _ in med_ids)})", med_ids).fetchall()
                if len(found) != len(med_ids):
                    raise ApiError(400, "Medicamento inexistente ou inativo")
                result = analyze_prescription(conn, patient_id, [{"medication_id": i} for i in med_ids], include_dosage=False)
                result["screening_only"] = True
                return self.send_json(200, result)
            if path == "/api/prescriptions/analyze":
                patient_id = int(data.get("patient_id") or 0)
                items = data.get("items") or []
                if not patient_id or not items: raise ApiError(400, "Paciente e ao menos um medicamento são obrigatórios")
                self.assert_patient_access(conn, user, patient_id)
                items = validate_prescription_items(conn, items)
                result = analyze_prescription(conn, patient_id, items)
                audit(conn, user["id"], "analyze", "prescription_draft", None, {"patient_id": patient_id, "item_count": len(items), "alert_count": len(result["alerts"])})
                conn.commit()
                return self.send_json(200, result)
            if path == "/api/prescriptions":
                patient_id = int(data.get("patient_id") or 0)
                items = data.get("items") or []
                if not patient_id or not items: raise ApiError(400, "Paciente e itens são obrigatórios")
                self.assert_patient_access(conn, user, patient_id)
                items = validate_prescription_items(conn, items)
                result = analyze_prescription(conn, patient_id, items)
                high = [a for a in result["alerts"] if a["severity"] in ("contraindicado", "grave")]
                justification = str(data.get("justification") or "").strip()
                # A verificação de gravidade é refeita no servidor ao salvar.
                # A interface não pode ser contornada enviando reviewed/justification manualmente.
                if high:
                    raise ApiError(409, "Prescrição bloqueada: há alerta grave ou contraindicação. Revise os medicamentos e a posologia.")
                if any(a["severity"] in ("moderado", "leve") for a in result["alerts"]) and data.get("reviewed") is not True:
                    raise ApiError(409, "Revise explicitamente a análise de segurança antes de confirmar alertas.")
                # Evita duas versões iguais em gravações simultâneas do mesmo paciente.
                conn.execute("BEGIN IMMEDIATE")
                latest = conn.execute("SELECT COALESCE(MAX(version),0) v FROM prescriptions WHERE patient_id=?", (patient_id,)).fetchone()["v"]
                # Preserva o nome usado na data do registro, caso o catálogo seja alterado.
                meds_at_registration = {r["id"]: r["generic_name"] for r in conn.execute(
                    f"SELECT id,generic_name FROM medications WHERE id IN ({','.join('?' for _ in items)})",
                    [int(x['medication_id']) for x in items])}
                for item in items:
                    item['medication_name_at_registration'] = meds_at_registration[int(item['medication_id'])]
                patient_row = conn.execute("SELECT name,code,birth_date,weight_kg,weight_date FROM patients WHERE id=?", (patient_id,)).fetchone()
                created_at = now_iso()
                birth = patient_row["birth_date"]
                registration_day = datetime.fromisoformat(created_at).date()
                try:
                    born = datetime.strptime(birth, "%Y-%m-%d").date()
                    age_at_registration = (registration_day.year - born.year -
                                           ((registration_day.month, registration_day.day) < (born.month, born.day))) if born <= registration_day else None
                except (ValueError, TypeError):
                    age_at_registration = None
                patient_snapshot = {"name": patient_row["name"], "code": patient_row["code"],
                                    "birth_date": birth, "weight_kg": patient_row["weight_kg"],
                                    "weight_date": patient_row["weight_date"],
                                    "age_at_registration": age_at_registration}
                cur = conn.execute("""INSERT INTO prescriptions(
                    patient_id,user_id,version,status,items_json,alerts_json,
                    dosage_evaluations_json,patient_snapshot_json,justification,rule_version,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (
                    patient_id, user["id"], latest+1, "saved", jdump(items), jdump(result["alerts"]),
                    jdump(result["dosage_evaluations"]), jdump(patient_snapshot),
                    justification or None, RULE_VERSION, created_at))
                audit(conn, user["id"], "save", "prescription", cur.lastrowid, {"version": latest+1, "rule_version": RULE_VERSION})
                conn.commit()
                return self.send_json(201, {"id": cur.lastrowid, "version": latest+1, **result})
            if path == "/api/dose/calculate":
                raise ApiError(410, "Calculadora genérica desativada: use referência específica por medicamento na prescrição")
            if path == "/api/dose/reference":
                try:
                    patient_id = int(data.get("patient_id") or 0)
                    medication_id = int(data.get("medication_id") or 0)
                except (TypeError, ValueError):
                    raise ApiError(400, "IDs inválidos")
                self.assert_patient_access(conn, user, patient_id)
                result = calculate_specific_reference(conn, patient_id, medication_id, data.get("indication"), data.get("egfr"))
                audit(conn, user["id"], "calculate_reference", "medication", medication_id, {"patient_id": patient_id, "rule": "LOSARTAN-PED-HTN-01"})
                conn.commit()
                return self.send_json(200, result)
            if path == "/api/adherence":
                patient_id = parse_int_id(data.get("patient_id") or 0, "Paciente")
                self.assert_patient_access(conn, user, patient_id)
                event = validate_adherence(conn, data, patient_id)
                cur = conn.execute("INSERT INTO adherence_events(patient_id,prescription_id,scheduled_at,recorded_at,status,note,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)", (patient_id, event["prescription_id"], event["scheduled_at"] or now_iso(), event["recorded_at"] or now_iso(), data["status"], event["note"], user["id"], now_iso()))
                audit(conn, user["id"], "create", "adherence_event", cur.lastrowid, {"status": data["status"]})
                conn.commit()
                return self.send_json(201, {"id": cur.lastrowid})
            if path == "/api/admin/medications":
                self.require_admin()
                for key in ("generic_name", "form", "route", "source"):
                    if not str(data.get(key) or "").strip():
                        raise ApiError(400, "Campos obrigatórios ausentes")
                if any(len(str(data.get(k) or "")) > 200 for k in ("generic_name", "brand_name", "form", "route", "drug_class", "source", "source_version")):
                    raise ApiError(400, "Campo com tamanho acima do permitido")
                concentration = data.get("concentration_mg_ml")
                if concentration in ("", None):
                    concentration = None
                else:
                    try:
                        concentration = float(concentration)
                    except (TypeError, ValueError):
                        raise ApiError(400, "Concentração inválida")
                    if not (0 < concentration <= 100000):
                        raise ApiError(400, "Concentração inválida")
                name = str(data["generic_name"]).strip()
                if conn.execute("SELECT 1 FROM medications WHERE lower(generic_name)=lower(?)", (name,)).fetchone():
                    raise ApiError(409, "Medicamento já cadastrado")
                cur = conn.execute("INSERT INTO medications(generic_name,brand_name,form,concentration_mg_ml,route,drug_class,source,source_version) VALUES(?,?,?,?,?,?,?,?)", (
                    name, data.get("brand_name"), str(data["form"]).strip(), concentration, str(data["route"]).strip(),
                    data.get("drug_class"), str(data["source"]).strip(), str(data.get("source_version") or RULE_VERSION)))
                audit(conn, user["id"], "create", "medication", cur.lastrowid, {})
                conn.commit(); return self.send_json(201, {"id": cur.lastrowid})
            if path == "/api/admin/interactions":
                self.require_admin()
                rule = validate_interaction_rule(data)
                pair = tuple(sorted((fold(rule["med_a_generic"]), fold(rule["med_b_generic"]))))
                for existing in conn.execute("SELECT med_a_generic,med_b_generic FROM interactions WHERE active=1"):
                    if tuple(sorted((fold(existing[0]), fold(existing[1])))) == pair:
                        raise ApiError(409, "Já existe uma interação ativa para este par de medicamentos")
                cur = conn.execute("INSERT INTO interactions(med_a_generic,med_b_generic,severity,effect,recommendation,source,review_date,rule_version) VALUES(?,?,?,?,?,?,?,?)", (rule["med_a_generic"],rule["med_b_generic"],rule["severity"],rule["effect"],rule["recommendation"],rule["source"],rule["review_date"],RULE_VERSION))
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
                pid = parse_int_id(path.rsplit("/", 1)[1], "Paciente")
                row = conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
                if not row or (user["role"] != "admin" and row["owner_user_id"] != user["id"]): raise ApiError(404, "Paciente não encontrado")
                new = validate_patient_fields(conn, data, partial=True, existing_status=row["allergy_status"])
                merged = {f: new.get(f, row[f]) for f in ("name","birth_date","sex","weight_kg","height_cm","weight_date","allergy_status")}
                allergies = new.get("allergies", jload(row["allergies"], []))
                conditions = new.get("conditions", jload(row["conditions"], []))
                meds = new.get("active_medications", jload(row["active_medications"], []))
                conn.execute("UPDATE patients SET name=?,birth_date=?,sex=?,weight_kg=?,height_cm=?,weight_date=?,allergies=?,conditions=?,active_medications=?,allergy_status=?,updated_at=? WHERE id=?", (merged["name"],merged["birth_date"],merged["sex"],merged["weight_kg"],merged["height_cm"],merged["weight_date"],jdump(allergies),jdump(conditions),jdump(meds),merged["allergy_status"],now_iso(),pid))
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
        if path.startswith("/api/"):
            raise ApiError(404, "Endpoint não encontrado")
        if path in ("", "/"): path = "/index.html"
        candidate = (FRONTEND / path.lstrip("/")).resolve()
        if FRONTEND not in candidate.parents and candidate != FRONTEND:
            raise ApiError(403, "Acesso inválido")
        if not candidate.exists() or not candidate.is_file():
            # Rotas do SPA (sem extensão) voltam ao index; arquivo inexistente é 404 de verdade.
            if Path(path).suffix:
                raise ApiError(404, "Arquivo não encontrado")
            candidate = FRONTEND / "index.html"
        content = candidate.read_bytes()
        ctype = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if candidate.suffix == ".js":
            ctype = "application/javascript"
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype in ("application/javascript","application/json") else ""))
        self.send_header("Content-Length", str(len(content)))
        if candidate.suffix in (".png", ".svg", ".jpg", ".jpeg", ".webp", ".ico") or "vendor" in candidate.parts:
            # Imagens e bibliotecas de terceiros mudam raramente: permite cache curto.
            self.send_header("Cache-Control", "public, max-age=86400")
        else:
            # HTML/JS/CSS do app: sempre revalidar para não servir interface antiga.
            self.send_header("Cache-Control", "no-cache")
        self.security_headers()
        self.end_headers(); self.wfile.write(content)


if __name__ == "__main__":
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    init_db()
    host = os.environ.get("DOSE_SAFE_HOST", "0.0.0.0" if IS_PRODUCTION() else "127.0.0.1")
    port = int(os.environ.get("PORT", os.environ.get("DOSE_SAFE_PORT", "8000")))
    print(f"Dose Safe {APP_VERSION} em http://{host}:{port}")
    if not IS_PRODUCTION():
        print("Login demo: claudio@dosesafe.local / DoseSafe123!")
        if host not in ("127.0.0.1", "localhost", "::1"):
            print("AVISO: modo demonstração (credenciais públicas) exposto fora do localhost. "
                  "Defina DOSE_SAFE_PRODUCTION=1 e as credenciais de administrador.")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
