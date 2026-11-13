import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from support import ServerCase, server  # noqa: E402
from validators import expected_dispense_quantity  # noqa: E402


class AlergiasECondicoesTest(ServerCase, unittest.TestCase):
    def setUp(self):
        self.c = self.client(); self.c.login(); self.ids = self.med_ids(self.c)

    def paciente(self, **dados):
        status, body, _ = self.c.post("/api/patients", {"name": "T", "birth_date": "1980-01-01", "weight_kg": 70,
                                                         "allergy_status": "nenhuma", **dados})
        self.assertEqual(status, 201, body)
        return body["patient"]["id"]

    def triagem(self, pid, *nomes):
        status, body, _ = self.c.post("/api/prescriptions/screen",
                                      {"patient_id": pid, "medication_ids": [self.ids[n] for n in nomes]})
        self.assertEqual(status, 200, body)
        return body["alerts"]

    def tipos(self, alerts, tipo):
        return [a for a in alerts if a["type"] == tipo]

    def test_alergia_sem_acento_ou_caixa(self):
        pid = self.paciente(allergies=["ACIDO ACETILSALICILICO"])
        self.assertTrue(self.tipos(self.triagem(pid, "Ácido acetilsalicílico"), "alergia"))

    def test_alergia_por_classe_do_catalogo(self):
        pid = self.paciente(allergies=["Penicilina"])
        self.assertTrue(self.tipos(self.triagem(pid, "Amoxicilina"), "alergia"))
        self.assertFalse(self.tipos(self.triagem(pid, "Dipirona"), "alergia"))

    def test_alergia_alias_aas(self):
        pid = self.paciente(allergies=["AAS"])
        self.assertTrue(self.tipos(self.triagem(pid, "Ácido acetilsalicílico"), "alergia"))

    def test_termo_curto_nao_casa_por_substring(self):
        pid = self.paciente(allergies=["ar", "a"])
        self.assertFalse(self.tipos(self.triagem(pid, "Dipirona", "Paracetamol"), "alergia"))

    def test_condicoes_usam_palavra_inteira(self):
        falsos = ["Hipertensão arterial primária", "Insuficiência adrenal", "Asma de gravidade moderada", "Primeira consulta"]
        pid = self.paciente(conditions=falsos)
        alerts = self.triagem(pid, "Ibuprofeno", "Metformina", "Losartana")
        self.assertEqual(self.tipos(alerts, "condição clínica"), [])
        self.assertEqual(self.tipos(alerts, "lacuna de cobertura"), [])

    def test_condicoes_verdadeiras_continuam_detectadas(self):
        for condicao, esperado in [("Doença renal", "COND-003"), ("DRC estágio 3", "COND-003"),
                                   ("Insuficiência dos rins", "COND-003"), ("Gestação", "COND-002"),
                                   ("Paciente gestante", "COND-002"), ("Diabetes", "COND-005")]:
            med = "Levofloxacino" if esperado == "COND-005" else ("Losartana" if esperado == "COND-002" else "Metformina")
            ids = {r["rule_id"] for r in self.triagem(self.paciente(conditions=[condicao]), med)}
            self.assertIn(esperado, ids, condicao)

    def test_interacao_detectada_entre_medicamento_ativo_e_novo(self):
        status, body, _ = self.c.post("/api/prescriptions/screen",
                                      {"patient_id": 3, "medication_ids": [self.ids["Varfarina"], self.ids["Fluconazol"]]})
        self.assertIn("Varfarina + Fluconazol", [a["title"] for a in body["alerts"] if a["type"] == "interação"])

    def test_busca_de_medicamento_ignora_acento_e_curinga(self):
        achados = [m["generic_name"] for m in self.c.get("/api/medications?q=acido%20acetil")[1]["medications"]]
        self.assertIn("Ácido acetilsalicílico", achados)
        self.assertEqual(self.c.get("/api/medications?q=%25")[1]["medications"], [])


class PrescricaoTest(ServerCase, unittest.TestCase):
    def setUp(self):
        self.c = self.client(); self.c.login(); self.ids = self.med_ids(self.c)

    def test_salvar_versionar_e_gerar_pdf(self):
        item = self.tablet(self.ids["Dipirona"])
        v = []
        for _ in range(2):
            status, body, _ = self.c.post("/api/prescriptions", {"patient_id": 2, "items": [item]})
            self.assertEqual(status, 201, body); v.append(body["version"])
        self.assertEqual(v, [1, 2])
        status, pdf, headers = self.c.get(f"/api/prescriptions/{body['id']}/pdf", raw=True)
        self.assertEqual(status, 200); self.assertTrue(pdf.startswith(b"%PDF-")); self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))

    def test_dose_acima_do_teto_bloqueia(self):
        item = self.tablet(self.ids["Dipirona"], dose_quantity=3, dispense_quantity=36)
        status, body, _ = self.c.post("/api/prescriptions", {"patient_id": 2, "items": [item], "reviewed": True, "justification": "x"})
        self.assertEqual(status, 409, body)

    def test_dipirona_dose_excessiva_sem_indicacao_bloqueia_na_api(self):
        item = self.tablet(self.ids['Dipirona'], dose_quantity=3, dispense_quantity=36,
                           indication='')
        status, result, _ = self.c.post('/api/prescriptions/analyze',
            {'patient_id': 2, 'items': [item]})
        self.assertEqual(status, 200, result)
        self.assertIn('FORA_DA_REFERENCIA',
            [ev['status'] for ev in result['dosage_evaluations']])
        status, body, _ = self.c.post('/api/prescriptions',
            {'patient_id': 2, 'items': [item], 'reviewed': True})
        self.assertEqual(status, 409, body)

    def test_dipirona_pediatrica_sem_indicacao_bloqueia_na_api(self):
        status, body, _ = self.c.post('/api/patients', {
            'name':'Paciente pediátrico fictício', 'birth_date':'2018-01-01',
            'weight_kg':25, 'allergy_status':'nenhuma'})
        self.assertEqual(status, 201, body)
        patient_id = body['patient']['id']
        item = {
            'medication_id':self.ids['Dipirona'], 'presentation':'dip-oral-50',
            'presentation_label':'Solução oral • 50 mg/mL',
            'form_kind':'liquid', 'strength_value':50, 'strength_unit':'mg/mL',
            'dose_unit':'mL', 'dispense_unit':'frasco(s)', 'bottle_volume_ml':100,
            'dose_quantity':12, 'dispense_quantity':2, 'dispense_mode':'auto',
            'route':'oral', 'frequency':'6/6h', 'duration_mode':'days',
            'duration_days':3, 'indication':''}
        status, analysis, _ = self.c.post('/api/prescriptions/analyze',
            {'patient_id':patient_id, 'items':[item]})
        self.assertEqual(status, 200, analysis)
        self.assertIn('FORA_DA_REFERENCIA',
            [ev['status'] for ev in analysis['dosage_evaluations']])
        status, body, _ = self.c.post('/api/prescriptions',
            {'patient_id':patient_id, 'items':[item]})
        self.assertEqual(status, 409, body)

    def test_alergia_critica_impede_gravacao_mesmo_revisada(self):
        status, patient, _ = self.c.post('/api/patients', {
            'name': 'Paciente com alergia', 'allergies': ['Penicilina']})
        self.assertEqual(status, 201, patient)
        item = self.tablet(self.ids['Amoxicilina'], strength_value=500)
        status, body, _ = self.c.post('/api/prescriptions', {
            'patient_id': patient['patient']['id'], 'items': [item],
            'reviewed': True, 'justification': 'Tentativa de ignorar risco'})
        self.assertEqual(status, 409, body)
        self.assertIn('bloqueada', body['error'].lower())

    def test_interacao_grave_impede_gravacao_mesmo_revisada(self):
        patient_id = 2
        a = self.tablet(self.ids['Varfarina'], strength_value=5)
        b = self.tablet(self.ids['Fluconazol'], strength_value=150)
        status, body, _ = self.c.post('/api/prescriptions', {
            'patient_id': patient_id, 'items': [a, b],
            'reviewed': True, 'justification': 'Tentativa de contornar bloqueio'})
        self.assertEqual(status, 409, body)

    def test_alerta_moderado_exige_revisao_antes_de_gravar(self):
        status, paciente, _ = self.c.post('/api/patients', {
            'name': 'Paciente revisão moderada', 'allergy_status': 'nenhuma'})
        self.assertEqual(status, 201, paciente)
        a = self.tablet(self.ids['Sertralina'], strength_value=50)
        b = self.tablet(self.ids['Ibuprofeno'], strength_value=400)
        dados = {'patient_id': paciente['patient']['id'], 'items': [a, b]}
        status, body, _ = self.c.post('/api/prescriptions', dados)
        self.assertEqual(status, 409, body)
        self.assertIn('Revise', body['error'])
        status, body, _ = self.c.post('/api/prescriptions', {**dados, 'reviewed': True})
        self.assertEqual(status, 201, body)

    def test_quantidade_desatualizada_e_rejeitada(self):
        item = self.tablet(self.ids["Dipirona"], dispense_quantity=5)
        self.assertEqual(self.c.post("/api/prescriptions/analyze", {"patient_id": 2, "items": [item]})[0], 400)

    def test_medicamento_repetido_e_valores_nao_finitos(self):
        item = self.tablet(self.ids["Dipirona"])
        self.assertEqual(self.c.post("/api/prescriptions/analyze", {"patient_id": 2, "items": [item, item]})[0], 400)
        self.assertEqual(self.c.call("POST", "/api/prescriptions/analyze", {"patient_id": 2, "items": [{**item, "dose_quantity": "NaN"}]})[0], 400)

    def test_regras_de_administracao(self):
        c = self.client()
        c.post("/api/auth/register", {"name": "A", "email": "adm@x.com", "password": "12345678", "role": "student"})
        c.login("adm@x.com", "12345678")
        self.assertEqual(c.post("/api/admin/interactions", {})[0], 403)
        adm = self.client(); adm.login("admin@dosesafe.local", "Admin123!")
        regra = {"med_a_generic": "Paracetamol", "med_b_generic": "Anlodipino", "severity": "grave", "effect": "e",
                 "recommendation": "r", "source": "s", "review_date": "2026-01-01"}
        self.assertEqual(adm.post("/api/admin/interactions", {**regra, "severity": "gravíssimo"})[0], 400)
        self.assertEqual(adm.post("/api/admin/interactions", {**regra, "med_b_generic": "paracetamol"})[0], 400)
        self.assertEqual(adm.post("/api/admin/interactions", regra)[0], 201)
        self.assertEqual(adm.post("/api/admin/interactions", {**regra, "med_a_generic": "anlodipino", "med_b_generic": "PARACETAMOL"})[0], 409)
        med = {"generic_name": "Teste Novo", "form": "Comprimido", "route": "oral", "source": "s"}
        self.assertEqual(adm.post("/api/admin/medications", med)[0], 201)  # antes: 500 sem source_version
        self.assertEqual(adm.post("/api/admin/medications", med)[0], 409)


class DispensacaoTest(unittest.TestCase):
    base = {"dose_quantity": 1, "frequency": "8/8h", "duration_mode": "days", "duration_days": 7,
            "form_kind": "tablet", "dose_unit": "comprimido(s)", "dispense_unit": "comprimido(s)"}

    def test_comprimidos(self):
        self.assertEqual(expected_dispense_quantity(self.base), 21)
        self.assertEqual(expected_dispense_quantity({**self.base, "dose_quantity": 0.5, "frequency": "12/12h"}), 7)

    def test_semanal_e_dose_unica(self):
        self.assertEqual(expected_dispense_quantity({**self.base, "frequency": "1x por semana", "duration_days": 28}), 4)
        self.assertIsNone(expected_dispense_quantity({**self.base, "frequency": "1x por semana", "duration_days": 10}))
        self.assertEqual(expected_dispense_quantity({**self.base, "frequency": "dose única", "duration_mode": "single"}), 1)

    def test_frascos_arredonda_para_cima(self):
        liquido = {**self.base, "form_kind": "liquid", "dose_unit": "mL", "dispense_unit": "frasco(s)",
                   "dose_quantity": 5, "bottle_volume_ml": 100, "duration_days": 7}
        self.assertEqual(expected_dispense_quantity(liquido), 2)   # 105 mL -> 2 frascos
        self.assertIsNone(expected_dispense_quantity({**liquido, "bottle_volume_ml": ""}))

    def test_entradas_invalidas(self):
        for mudanca in ({"dose_quantity": 0}, {"dose_quantity": "x"}, {"duration_days": 1.5}, {"frequency": "xx"},
                        {"dose_quantity": float("nan")}):
            self.assertIsNone(expected_dispense_quantity({**self.base, **mudanca}), mudanca)


if __name__ == "__main__":
    unittest.main()
