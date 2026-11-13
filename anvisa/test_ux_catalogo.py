import json
import unittest
from pathlib import Path
from clinical_rules import load_approved_rules

ROOT = Path(__file__).resolve().parent.parent

class TesteUXCatalogo(unittest.TestCase):
    def test_100_fichas_pendentes(self):
        all_meds=json.loads((ROOT/'catalog_100.json').read_text(encoding='utf8'))
        drafts=list((ROOT/'anvisa/rascunhos_catalogo').glob('*.json'))
        self.assertEqual(len(all_meds),100)
        self.assertEqual(len(drafts),100)
        for draft in drafts:
            data=json.loads(draft.read_text(encoding='utf8'))
            self.assertEqual(data['status'],'rascunho')
            self.assertIsNone(data['dose_min'])
            self.assertIsNone(data['dose_max'])
            self.assertIsNone(data['daily_max_mg'])
            self.assertTrue(data['necessita_bula_especifica'])

    def test_registros_nao_ativam_regras_clinicas(self):
        self.assertEqual(len(load_approved_rules()),0)
        idx=json.loads((ROOT/'anvisa/candidatos_para_revisao.json').read_text(encoding='utf8'))
        self.assertEqual(len(idx['medicamentos']),100)
        self.assertTrue(all(x['status']=='PENDENTE_BULA_ESPECIFICA' for x in idx['medicamentos']))

    def test_interface_indicacao_e_registro_opcional(self):
        js=(ROOT/'frontend/dist/js/pages/PrescriptionPage.js').read_text(encoding='utf8')
        self.assertIn("field('Indicação clínica'",js)
        self.assertIn("'Registro do produto (opcional)'",js)
        self.assertIn("'rx-pediatric-banner'",js)
        self.assertIn('Paciente adolescente: verifique as restrições etárias da bula.',js)
        self.assertIn('rx-quantity-stepper',js)
        self.assertIn("'aria-label':'Diminuir quantidade por administração'",js)
        self.assertIn("'aria-label':'Aumentar quantidade por administração'",js)
        self.assertNotIn("'Nº da bula selecionada'",js)
        self.assertIn('age >= 6 && age <= 17',js)

if __name__ == '__main__': unittest.main()
