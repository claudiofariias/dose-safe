"""Erros de domínio convertidos em respostas HTTP pelo servidor."""
from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message
