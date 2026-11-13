import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from support import ServerCase, server  # noqa: E402


class AcessoEntreUsuariosTest(ServerCase, unittest.TestCase):
    def setUp(self):
        self.owner = self.client(); self.owner.login()
        self.other = self.client()
        self.other.post("/api/auth/register", {"name": "Outro", "email": f"o{id(self)}@x.com", "password": "12345678", "role": "student"})
        self.other.login(f"o{id(self)}@x.com", "12345678")

    def test_adesao_de_outro_usuario_nao_vaza(self):
        self.owner.post("/api/adherence", {"patient_id": 1, "status": "taken", "note": "privado"})
        status, body, _ = self.other.get("/api/adherence?patient_id=1")
        self.assertEqual(status, 404, body)
        status, _, _ = self.other.post("/api/adherence", {"patient_id": 1, "status": "taken"})
        self.assertEqual(status, 404)
        status, body, _ = self.owner.get("/api/adherence?patient_id=1")
        self.assertEqual((status, len(body["events"])), (200, 1))

    def test_adesao_exige_prescricao_do_mesmo_paciente(self):
        status, _, _ = self.owner.post("/api/adherence", {"patient_id": 1, "status": "taken", "prescription_id": 9999})
        self.assertEqual(status, 404)
        status, _, _ = self.owner.post("/api/adherence", {"patient_id": 1, "status": "taken", "scheduled_at": "ontem"})
        self.assertEqual(status, 400)

    def test_paciente_e_pdf_de_outro_usuario(self):
        self.assertEqual(self.other.get("/api/patients/1")[0], 404)
        self.assertEqual(self.other.get("/api/prescriptions/1/pdf", raw=True)[0], 404)
        self.assertEqual(self.other.get("/api/admin/audit")[0], 403)

    def test_sem_sessao(self):
        self.assertEqual(self.client().get("/api/patients")[0], 401)


class EntradasInvalidasTest(ServerCase, unittest.TestCase):
    def setUp(self):
        self.c = self.client(); self.c.login()

    def test_id_nao_numerico_nao_gera_500(self):
        self.assertEqual(self.c.get("/api/patients/abc")[0], 404)
        self.assertEqual(self.c.put("/api/patients/abc", {"name": "x"})[0], 404)
        self.assertEqual(self.c.get("/api/adherence?patient_id=abc")[0], 404)

    def test_corpo_json_nao_objeto(self):
        self.assertEqual(self.c.call("POST", "/api/patients", [1])[0], 400)

    def test_paciente_invalido(self):
        casos = [{"name": "Z", "weight_kg": "abc"}, {"name": "Z", "weight_kg": -3}, {"name": "Z", "weight_kg": 9999},
                 {"name": "Z", "birth_date": "xx"}, {"name": "Z", "birth_date": "2999-01-01"},
                 {"name": "Z", "sex": "?"}, {"name": "Z", "active_medications": ["q"]},
                 {"name": "Z", "active_medications": [999999]}, {"name": "Z", "allergies": "dipirona"},
                 {"name": "Z", "allergy_status": "informada"}, {"name": "  "}, {"name": "x" * 500}]
        for caso in casos:
            status, body, _ = self.c.post("/api/patients", caso)
            self.assertEqual(status, 400, (caso, body))

    def test_paciente_valido_e_edicao_parcial(self):
        status, body, _ = self.c.post("/api/patients", {"name": " Teste ", "birth_date": "1990-05-01", "sex": "Feminino",
            "weight_kg": "60.5", "allergies": ["Dipirona", "dipirona"], "conditions": ["Diabetes"]})
        self.assertEqual(status, 201, body)
        patient = body["patient"]
        self.assertEqual((patient["name"], patient["weight_kg"], patient["allergies"], patient["allergy_status"]),
                         ("Teste", 60.5, ["Dipirona"], "informada"))
        status, _, _ = self.c.put(f"/api/patients/{patient['id']}", {"weight_kg": 62})
        self.assertEqual(status, 200)
        updated = self.c.get(f"/api/patients/{patient['id']}")[1]["patient"]
        self.assertEqual((updated["weight_kg"], updated["name"], updated["conditions"]), (62.0, "Teste", ["Diabetes"]))
        # esvaziar alergias não pode deixar 'informada' sem alergias
        self.c.put(f"/api/patients/{patient['id']}", {"allergies": []})
        self.assertEqual(self.c.get(f"/api/patients/{patient['id']}")[1]["patient"]["allergy_status"], "nao_informada")

    def test_paciente_legado_com_dado_invalido_nao_derruba_analise(self):
        conn = server.db()
        conn.execute("UPDATE patients SET active_medications='[\"q\", null, 3]' WHERE id=2")
        conn.commit(); conn.close()
        ids = self.med_ids(self.c)
        status, body, _ = self.c.post("/api/prescriptions/screen", {"patient_id": 2, "medication_ids": [ids["Dipirona"]]})
        self.assertEqual(status, 200, body)

    def test_cadastro_de_usuario(self):
        base = {"name": "N", "email": "valido@x.com", "password": "12345678", "role": "student"}
        for mudanca in ({"email": "sem-arroba"}, {"password": "123"}, {"role": "admin"}, {"password": "x" * 300}):
            self.assertEqual(self.client().post("/api/auth/register", {**base, **mudanca})[0], 400, mudanca)
        self.assertEqual(self.client().post("/api/auth/register", base)[0], 201)
        self.assertEqual(self.client().post("/api/auth/register", base)[0], 409)


class LoginThrottleTest(unittest.TestCase):
    def test_bloqueio_e_liberacao(self):
        from security import LoginThrottle
        now = [0.0]
        t = LoginThrottle(max_failures=3, window_seconds=60, clock=lambda: now[0])
        for _ in range(3):
            self.assertEqual(t.retry_after("a"), 0); t.register_failure("a")
        self.assertGreater(t.retry_after("a"), 0)
        self.assertEqual(t.retry_after("b"), 0)
        now[0] = 61
        self.assertEqual(t.retry_after("a"), 0)
        t.register_failure("a"); t.reset("a")
        self.assertEqual(t.retry_after("a"), 0)


class LoginHttpTest(ServerCase, unittest.TestCase):
    def test_429_apos_falhas_repetidas(self):
        c = self.client()
        codes = [c.post("/api/auth/login", {"email": "claudio@dosesafe.local", "password": "errada"})[0] for _ in range(7)]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5:], [429, 429])
        # mesmo com a senha certa, segue bloqueado durante a janela
        self.assertEqual(c.post("/api/auth/login", {"email": "claudio@dosesafe.local", "password": "DoseSafe123!"})[0], 429)


class EstaticosTest(ServerCase, unittest.TestCase):
    def test_cabecalhos_e_rotas(self):
        c = self.client()
        status, body, headers = c.get("/", raw=True)
        self.assertEqual(status, 200); self.assertIn(b"<main", body)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertNotIn("Clear-Site-Data", headers)
        self.assertEqual(c.get("/js/inexistente.js", raw=True)[0], 404)
        self.assertEqual(c.get("/qualquer/rota/spa", raw=True)[0], 200)
        status, body, _ = c.get("/../server.py", raw=True)  # tentativa de sair da pasta pública
        self.assertNotIn(b"hash_password", body)
        self.assertIn(status, (200, 403, 404))
        self.assertEqual(c.get("/js/App.js", raw=True)[2]["Content-Type"].split(";")[0], "application/javascript")


class ProducaoTest(unittest.TestCase):
    def test_producao_nao_semeia_pacientes_demo(self):
        import os, tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp, patch.object(server, "DB_PATH", Path(tmp) / "p.db"), \
                patch.dict(os.environ, {"DOSE_SAFE_PRODUCTION": "1", "DOSE_SAFE_ADMIN_EMAIL": "a@b.com",
                                        "DOSE_SAFE_ADMIN_PASSWORD": "senha-bem-longa-123"}):
            server.init_db()
            conn = server.db()
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0], 0)
            self.assertEqual([r[0] for r in conn.execute("SELECT email FROM users")], ["a@b.com"])
            conn.close()


if __name__ == "__main__":
    unittest.main()
