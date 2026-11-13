"""Hash de senha e proteção simples contra tentativa repetida de login."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time

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


# Hash fictício usado para gastar o mesmo tempo quando o e-mail não existe,
# evitando enumeração de contas por diferença de tempo de resposta.
_DUMMY_HASH = hash_password("dose-safe-dummy-password")


def verify_password_or_dummy(password: str, encoded: str | None) -> bool:
    if encoded is None:
        verify_password(password, _DUMMY_HASH)
        return False
    return verify_password(password, encoded)


class LoginThrottle:
    """Bloqueio temporário em memória após falhas consecutivas (por e-mail + IP).

    Simples e sem dependências: reinicia com o processo, o que é aceitável para o
    escopo acadêmico. Para vários processos/instâncias, use um armazenamento compartilhado.
    """

    def __init__(self, max_failures=5, window_seconds=15 * 60, clock=time.monotonic):
        self.max_failures = max_failures
        self.window = window_seconds
        self.clock = clock
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key):
        now = self.clock()
        recent = [t for t in self._failures.get(key, []) if now - t < self.window]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def retry_after(self, key) -> int:
        """Segundos até nova tentativa permitida (0 = liberado)."""
        with self._lock:
            recent = self._recent(key)
            if len(recent) < self.max_failures:
                return 0
            return max(1, int(self.window - (self.clock() - recent[0])))

    def register_failure(self, key):
        with self._lock:
            self._recent(key)
            self._failures.setdefault(key, []).append(self.clock())
            if len(self._failures) > 10_000:  # limite de memória
                self._failures.pop(next(iter(self._failures)))

    def reset(self, key):
        with self._lock:
            self._failures.pop(key, None)
