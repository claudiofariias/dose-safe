"""Testes apenas de cálculo/escopo de fontes; não são validação clínica."""
import json
import shutil
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from clinical_rules import dosage_evaluations
from dose_reference_screening import evaluate_orientative_reference


def item(*, strength=500, kind='tablet', unit='mg', qty=1, freq='8/8h', indication='febre'):
    return {'form_kind': kind, 'strength_value': strength, 'strength_unit': unit,
            'dose_quantity': qty, 'route': 'oral', 'frequency': freq, 'indication': indication}


class TesteReferenciasOrientativas(unittest.TestCase):
    def test_dipirona_comprimido_adulto_compara_sem_afirmar_seguranca(self):
        ev = evaluate_orientative_reference('Dipirona', item(), {'age': 30, 'weight_kg': None})
        self.assertEqual(ev['status'], 'COMPARACAO_ORIENTATIVA')
        self.assertEqual(ev['amount_mg'], 500)
        self.assertEqual(ev['daily_mg'], 1500)
        self.assertIn('não confirma segurança', ev['message'])
        self.assertEqual(ev['comparison_kind'], 'ORIENTATIVA_NAO_ESPECIFICA_PRODUTO')

    def test_dipirona_comprimido_limite_de_dose(self):
        ev = evaluate_orientative_reference('Dipirona', item(qty=3), {'age': 32})
        self.assertEqual(ev['status'], 'FORA_DA_REFERENCIA')
        self.assertEqual(ev['severity'], 'grave')

    def test_dipirona_comprimido_quatro_quatro_ultrapassa_tomadas(self):
        ev = evaluate_orientative_reference('Dipirona', item(freq='4/4h'), {'age': 32})
        self.assertEqual(ev['status'], 'FORA_DA_REFERENCIA')
        self.assertEqual(ev['severity'], 'grave')

    def test_dipirona_comprimido_pediatrico_nao_compara(self):
        ev = evaluate_orientative_reference('Dipirona', item(), {'age': 8, 'weight_kg': 25})
        self.assertEqual(ev['status'], 'NAO_VERIFICADA')

    def test_dipirona_solução_50_pediatrica_faixa_peso(self):
        med = item(strength=50, kind='liquid', unit='mg/mL', qty=10, freq='6/6h')
        ev = evaluate_orientative_reference('Dipirona', med, {'age': 8, 'weight_kg': 25})
        self.assertEqual(ev['status'], 'COMPARACAO_ORIENTATIVA')
        self.assertEqual(ev['amount_mg'], 500)
        self.assertEqual(ev['daily_mg'], 2000)
        med['dose_quantity'] = 12
        self.assertEqual(evaluate_orientative_reference('Dipirona', med, {'age': 8, 'weight_kg': 25})['status'], 'FORA_DA_REFERENCIA')
        med['dose_quantity'] = 2
        self.assertEqual(evaluate_orientative_reference('Dipirona', med, {'age': 8, 'weight_kg': 25})['severity'], 'moderado')

    def test_dipirona_solução_rejeita_peso_intermediario_sem_interpolacao(self):
        med = item(strength=50, kind='liquid', unit='mg/mL', qty=2.5)
        self.assertEqual(evaluate_orientative_reference('Dipirona', med, {'age': 3, 'weight_kg': 8.5})['status'], 'NAO_VERIFICADA')
        self.assertEqual(evaluate_orientative_reference('Dipirona', med, {'age': 0, 'weight_kg': 5})['status'], 'NAO_VERIFICADA')

    def test_dipirona_solução_adulto_e_dia(self):
        med = item(strength=50, kind='liquid', unit='mg/mL', qty=20, freq='6/6h')
        self.assertEqual(evaluate_orientative_reference('Dipirona', med, {'age': 42})['status'], 'COMPARACAO_ORIENTATIVA')
        med['frequency'] = '4/4h'
        self.assertEqual(evaluate_orientative_reference('Dipirona', med, {'age': 42})['status'], 'FORA_DA_REFERENCIA')

    def test_paracetamol_solução_pediatrica_mgkg(self):
        med = item(strength=200, kind='liquid', unit='mg/mL', qty=1.5, freq='6/6h', indication='dor')
        ev = evaluate_orientative_reference('Paracetamol', med, {'age': 8, 'weight_kg': 25})
        self.assertEqual(ev['status'], 'COMPARACAO_ORIENTATIVA')
        self.assertEqual(ev['amount_reference'], 12)
        med['dose_quantity'] = 3
        self.assertEqual(evaluate_orientative_reference('Paracetamol', med, {'age': 8, 'weight_kg': 25})['status'], 'FORA_DA_REFERENCIA')
        med['dose_quantity'] = 1.5
        med['frequency'] = '4/4h'
        self.assertEqual(evaluate_orientative_reference('Paracetamol', med, {'age': 8, 'weight_kg': 25})['status'], 'FORA_DA_REFERENCIA')

    def test_paracetamol_limites_especificos_de_idade_e_peso(self):
        med = item(strength=200, kind='liquid', unit='mg/mL', qty=1.5, freq='6/6h')
        for age, weight in ((1, 10), (8, 10), (12, 25), (8, None)):
            with self.subTest(age=age, weight=weight):
                self.assertEqual(evaluate_orientative_reference('Paracetamol', med, {'age': age, 'weight_kg': weight})['status'], 'NAO_VERIFICADA')

    def test_paracetamol_adulto_max_por_dose(self):
        med = item(strength=200, kind='liquid', unit='mg/mL', qty=5, freq='6/6h', indication='dor')
        self.assertEqual(evaluate_orientative_reference('Paracetamol', med, {'age': 34})['status'], 'COMPARACAO_ORIENTATIVA')
        med['dose_quantity'] = 6
        self.assertEqual(evaluate_orientative_reference('Paracetamol', med, {'age': 34})['status'], 'FORA_DA_REFERENCIA')

    def test_nao_estende_para_concentracoes_ou_formas_nao_cobertas(self):
        wrong = [item(strength=1000), item(kind='drops', unit='mg/mL'),
                 item(kind='liquid', strength=500, unit='mg/mL')]
        for med in wrong:
            self.assertIsNone(evaluate_orientative_reference('Dipirona', med, {'age': 20}))
        self.assertIsNone(evaluate_orientative_reference('Ibuprofeno', item(), {'age': 25}))

    def test_indicacao_nao_suportada_ou_ausente(self):
        for value in ('', 'outro', 'doravante'):
            self.assertEqual(evaluate_orientative_reference('Dipirona', item(indication=value), {'age': 30})['status'], 'NAO_VERIFICADA')

    def test_sem_indicacao_adulto_teto_continua_bloqueante(self):
        # 3 comprimidos de 500 mg, 8/8h = 1.500 mg/dose e 4.500 mg/dia.
        for indication in ('', 'outra', 'inflamacao'):
            with self.subTest(indication=indication):
                ev = evaluate_orientative_reference('Dipirona',
                    item(qty=3, indication=indication), {'age': 36})
                self.assertEqual(ev['status'], 'FORA_DA_REFERENCIA')
                self.assertEqual(ev['severity'], 'grave')
                self.assertEqual(ev['comparison_kind'], 'TRIAGEM_TETO_DOCUMENTAL')
                self.assertIn('não foi confirmada', ev['message'])

    def test_sem_indicacao_nao_faz_comparacao_completa(self):
        for indication in ('', 'outra'):
            with self.subTest(indication=indication):
                ev = evaluate_orientative_reference('Dipirona',
                    item(qty=1, indication=indication), {'age': 36})
                self.assertEqual(ev['status'], 'NAO_VERIFICADA')
        self.assertEqual(evaluate_orientative_reference('Dipirona',
            item(qty=1, indication='febre'), {'age': 36})['status'], 'COMPARACAO_ORIENTATIVA')

    def test_pediatrico_sem_indicacao_dipirona_acima_do_teto(self):
        # Bula orientativa 24–30 kg: até 10 mL/dose, 40 mL/dia.
        med = item(strength=50, kind='liquid', unit='mg/mL', qty=12,
                   freq='6/6h', indication='')
        ev = evaluate_orientative_reference('Dipirona', med, {'age': 8, 'weight_kg': 25})
        self.assertEqual(ev['status'], 'FORA_DA_REFERENCIA')
        self.assertEqual(ev['severity'], 'grave')
        med['dose_quantity'] = 5
        self.assertEqual(evaluate_orientative_reference('Dipirona', med,
            {'age': 8, 'weight_kg': 25})['status'], 'NAO_VERIFICADA')
        med['indication'] = 'febre'
        self.assertEqual(evaluate_orientative_reference('Dipirona', med,
            {'age': 8, 'weight_kg': 25})['status'], 'COMPARACAO_ORIENTATIVA')

    def test_pediatrico_sem_indicacao_paracetamol_acima_do_teto(self):
        med = item(strength=200, kind='liquid', unit='mg/mL', qty=3,
                   freq='6/6h', indication='')
        ev = evaluate_orientative_reference('Paracetamol', med, {'age': 8, 'weight_kg': 25})
        self.assertEqual(ev['status'], 'FORA_DA_REFERENCIA')
        self.assertEqual(ev['severity'], 'grave')

    def test_sem_indicacao_nao_extrapola_apresentacao_ou_peso(self):
        self.assertIsNone(evaluate_orientative_reference('Dipirona',
            item(strength=1000, qty=10, indication=''), {'age': 36}))
        ev = evaluate_orientative_reference('Dipirona',
            item(strength=50, kind='liquid', unit='mg/mL', qty=40, indication=''),
            {'age': 8, 'weight_kg': None})
        self.assertEqual(ev['status'], 'NAO_VERIFICADA')

    def test_prioridade_dos_status_sem_inventar_regra_clinica(self):
        con = sqlite3.connect(':memory:')
        con.row_factory = sqlite3.Row
        con.execute('CREATE TABLE medications (id INTEGER PRIMARY KEY, generic_name TEXT NOT NULL)')
        con.executemany('INSERT INTO medications VALUES (?,?)', [(1,'Dipirona'),(2,'Ibuprofeno')])
        try:
            results = dosage_evaluations(con, [dict(item(), medication_id=1), dict(item(), medication_id=2)], {'age': 30, 'weight_kg': 75})
            self.assertEqual([x['status'] for x in results], ['COMPARACAO_ORIENTATIVA','NAO_VERIFICADA'])
        finally:
            con.close()

    @unittest.skipUnless(shutil.which('node'), 'Node não instalado: teste de interface ignorado')
    def test_js_pages_syntax_and_singular_plural(self):
        for name in ('pages/PatientsPage.js', 'pages/HistoryPage.js', 'pages/PrescriptionPage.js',
                     'components/ClinicalAlertSummary.js', 'utils/alertText.js'):
            subprocess.run(['node', '--check', str(ROOT/'frontend/dist/js'/name)], check=True, capture_output=True, text=True)
        script = '''import {summarizeAlertCounts} from './frontend/dist/js/utils/alertText.js';
        const a = summarizeAlertCounts([{severity:'informação insuficiente'}]);
        const b = summarizeAlertCounts([{severity:'informação insuficiente'},{severity:'informação insuficiente'}]);
        const c = summarizeAlertCounts([{severity:'grave'},{severity:'informação insuficiente'}]);
        if(a!=='1 pendência'||b!=='2 pendências'||c!=='1 risco · 1 pendência')throw Error([a,b,c].join('|'));'''
        subprocess.run(['node','--experimental-default-type=module','--input-type=module','-e',script], cwd=ROOT, check=True, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
