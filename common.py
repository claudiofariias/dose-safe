"""Utilitários puros compartilhados (sem dependência de banco ou HTTP)."""
from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timezone


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fold(value) -> str:
    """Minúsculas, sem acentos e sem espaços nas pontas: chave de comparação textual."""
    text = unicodedata.normalize("NFKD", str(value if value is not None else "").casefold())
    return "".join(c for c in text if not unicodedata.combining(c)).strip()


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
        if born > today:  # data futura é inválida; não gerar idade negativa
            return None
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except Exception:
        return None


def audit(conn, user_id, action, target_type, target_id=None, details=None):
    conn.execute(
        "INSERT INTO audit(user_id, action, target_type, target_id, created_at, details) VALUES(?,?,?,?,?,?)",
        (user_id, action, target_type, target_id, now_iso(), jdump(details or {})),
    )
