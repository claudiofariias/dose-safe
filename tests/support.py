"""Infraestrutura de teste: servidor real em thread, banco temporário, cliente HTTP."""
from __future__ import annotations

import http.cookiejar
import json
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402


class Client:
    def __init__(self, base):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None, raw=False):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, method=method, data=data,
                                         headers={"Content-Type": "application/json"})
        try:
            response = self.opener.open(request)
        except urllib.error.HTTPError as error:
            payload = error.read()
            return error.code, (payload if raw else _json(payload)), error.headers
        payload = response.read()
        return response.status, (payload if raw else _json(payload)), response.headers

    def get(self, path, **kw): return self.call("GET", path, **kw)
    def post(self, path, body=None, **kw): return self.call("POST", path, {} if body is None else body, **kw)
    def put(self, path, body=None, **kw): return self.call("PUT", path, {} if body is None else body, **kw)

    def login(self, email="claudio@dosesafe.local", password="DoseSafe123!"):
        status, body, _ = self.post("/api/auth/login", {"email": email, "password": password})
        assert status == 200, (status, body)
        return body["user"]


def _json(payload):
    try:
        return json.loads(payload)
    except ValueError:
        return payload[:200]


class ServerCase:
    """Mixin para unittest.TestCase: sobe um servidor isolado por classe de teste."""

    @classmethod
    def setUpClass(cls):
        cls._quiet = patch.object(server.Handler, "log_message", lambda *args, **kwargs: None)
        cls._quiet.start()
        cls._tmp = tempfile.TemporaryDirectory()
        cls._patch = patch.object(server, "DB_PATH", Path(cls._tmp.name) / "test.db")
        cls._patch.start()
        server.LOGIN_THROTTLE.__init__()  # estado limpo
        server.init_db()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls._patch.stop()
        cls._quiet.stop()
        cls._tmp.cleanup()

    def client(self):
        return Client(self.base)

    def med_ids(self, client):
        status, body, _ = client.get("/api/medications")
        assert status == 200
        return {m["generic_name"]: m["id"] for m in body["medications"]}

    def tablet(self, med_id, **overrides):
        item = {"medication_id": med_id, "form_kind": "tablet", "dose_unit": "comprimido(s)",
                "dispense_unit": "comprimido(s)", "strength_unit": "mg", "strength_value": 500,
                "dose_quantity": 1, "dispense_quantity": 12, "route": "oral", "frequency": "6/6h",
                "duration_mode": "days", "duration_days": 3, "indication": "dor", "presentation": "p",
                "presentation_label": "p", "dispense_mode": "auto"}
        item.update(overrides)
        return item
