"""Testes técnicos do PDF acadêmico; não validam decisões clínicas."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import receipt_pdf
import server


class TestePdfPrescricao(unittest.TestCase):
    def setUp(self):
        self.item = {
            'medication_id': 1, 'medication_name_at_registration': 'Dipirona',
            'presentation': 'Solução oral • 50 mg/mL',
            'presentation_label': 'Solução oral • 50 mg/mL',
            'form_kind': 'liquid', 'strength_value': 50, 'strength_unit': 'mg/mL',
            'dose_quantity': 5, 'dose_unit': 'mL', 'frequency': '8/8h',
            'duration_mode': 'days', 'duration_days': 3, 'route': 'oral',
            'bottle_volume_ml': 100, 'dispense_quantity': 1,
            'dispense_unit': 'frasco(s)', 'dispense_mode': 'auto',
            'indication': 'febre', 'anvisa_registration': '',
        }
        self.patient = {
            'name': 'Paciente Fictício', 'code': 'L-411',
            'birth_date': '2021-11-11', 'age_at_registration': 5,
            'weight_kg': 25, 'weight_date': '2026-11-11',
            'historical_snapshot': True,
        }
        self.professional = {'name': 'Responsável Fictício', 'crm': 'Informado no cadastro', 'specialty': 'Teste'}
        self.medicines = {1: {'generic_name': 'Dipirona'}}
        self.prescription = {
            'id': 1, 'version': 1, 'items': [self.item],
            'created_at': '2026-11-11T18:14:58+00:00', 'rule_version': '2.4-academico-revisao-clinica',
            'alerts': [{'severity': 'informação insuficiente', 'type': 'posologia',
                        'title': 'Posologia não verificada: Dipirona',
                        'effect': 'Sem regra clínica aprovada.',
                        'recommendation': 'Conferir bula profissional.',
                        'source': 'Cobertura pendente', 'rule_id': 'DOSE-PENDENTE-1',
                        'review_date': ''}],
            'dosage_evaluations': [{'status': 'NAO_VERIFICADA',
                                    'message': 'Sem regra clínica aprovada.',
                                    'rule_id': None}],
        }

    def pdf(self, patient=None, prescription=None):
        result = receipt_pdf.build_receipt_pdf(
            prescription if prescription is not None else self.prescription,
            patient if patient is not None else self.patient,
            self.professional, self.medicines,
        )
        self.assertTrue(result.startswith(b'%PDF-1.4'))
        self.assertTrue(result.rstrip().endswith(b'%%EOF'))
        return result

    def test_inclui_dose_dispensa_e_regras_pendentes(self):
        result = self.pdf()
        for word in ('5 anos', '25 kg', '250 mg', '10 mg/kg', '1 frasco de 100 mL',
                     '45 mL', 'febre', 'DOSE-PENDENTE-1', 'NÃO VERIFICADA',
                     'Conferir bula profissional', 'NÃO VÁLIDO COMO RECEITA'):
            with self.subTest(word=word):
                self.assertIn(word.encode('cp1252'), result)

    def test_registro_antigo_nao_inventa_peso_ou_resultado(self):
        prescription = dict(self.prescription, dosage_evaluations=[])
        patient = dict(self.patient, historical_snapshot=False, weight_kg=None)
        result = self.pdf(patient=patient, prescription=prescription)
        self.assertIn('peso utilizado na análise não preservado'.encode('cp1252'), result)
        self.assertIn('não preservada neste registro antigo'.encode('cp1252'), result)
        self.assertNotIn(b'10 mg/kg', result)

    def test_multiplos_alertas_geram_paginacao(self):
        alerts = self.prescription['alerts'] * 25
        result = self.pdf(prescription=dict(self.prescription, alerts=alerts))
        self.assertIn(b'/Count ', result)
        self.assertGreater(result.count(b'/Type /Page /Parent'), 1)
        self.assertIn('DOSE-PENDENTE-1'.encode('cp1252'), result)

    def test_migracao_nao_destrutiva_em_banco_existente(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'base.db'
            with sqlite3.connect(database) as conn:
                conn.execute('''CREATE TABLE prescriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    items_json TEXT NOT NULL,
                    alerts_json TEXT NOT NULL,
                    justification TEXT,
                    rule_version TEXT NOT NULL,
                    created_at TEXT NOT NULL)''')
                conn.execute('''INSERT INTO prescriptions
                    (patient_id,user_id,version,status,items_json,alerts_json,rule_version,created_at)
                    VALUES (1,1,1,'saved','[]','[]','v-antiga','2026-01-01')''')
            with patch.object(server, 'DB_PATH', database):
                server.init_db()
                with server.db() as conn:
                    fields = {row['name'] for row in conn.execute('PRAGMA table_info(prescriptions)')}
                    self.assertIn('dosage_evaluations_json', fields)
                    self.assertIn('patient_snapshot_json', fields)
                    historical = conn.execute('SELECT * FROM prescriptions WHERE id=1').fetchone()
                    self.assertEqual(historical['rule_version'], 'v-antiga')
                    self.assertEqual(historical['dosage_evaluations_json'], '[]')
                    self.assertEqual(historical['patient_snapshot_json'], '{}')


if __name__ == '__main__':
    unittest.main()
