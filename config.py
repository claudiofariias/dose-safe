"""Configuração central e constantes do Dose Safe."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend" / "dist"
SESSION_TTL_SECONDS = 60 * 60 * 8
RULE_VERSION = "2.7-academico-triagem-teto-numerico"
APP_VERSION = "1.9.0"
SCHEMA_VERSION = "1"
