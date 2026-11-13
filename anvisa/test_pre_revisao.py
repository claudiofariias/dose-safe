import json
import unittest
from pathlib import Path
from anvisa.sincronizar_anvisa import suspected_combination
from clinical_rules import load_approved_rules

ROOT=Path(__file__).resolve().parent.parent

class PreRevisaoTest(unittest.TestCase):
    def test_evidencia_nao_e_aprovacao(self):
        source=json.loads((ROOT/'anvisa/evidencias_curadas.json').read_text(encoding='utf8'))
        self.assertEqual(len(source['fontes']),2)
        self.assertFalse(source['aprovacao_clinica_realizada'])
        self.assertFalse(load_approved_rules())
        for row in source['fontes']:
            self.assertIn('PENDENTE',row['status'])
            self.assertTrue(row['fonte_url'].startswith('https://'))

    def test_dipirona_conversao_valores_publicados(self):
        data=json.loads((ROOT/'anvisa/evidencias_curadas.json').read_text(encoding='utf8'))['fontes'][0]
        for faixa in data['tabela_pediatrica']:
            self.assertEqual(faixa['dose_unica_ml_min']*50,faixa['dose_unica_mg_min'])
            self.assertEqual(faixa['dose_unica_ml_max']*50,faixa['dose_unica_mg_max'])
            self.assertEqual(faixa['maximo_diario_ml']*50,faixa['maximo_diario_mg'])
        faixa=next(x for x in data['tabela_pediatrica'] if x['peso_kg_min']<=25<=x['peso_kg_max'])
        self.assertEqual((faixa['dose_unica_ml_min'],faixa['dose_unica_ml_max']),(5,10))

    def test_associacao_medicamentosa_nao_e_monofarmaco(self):
        self.assertTrue(suspected_combination('Dipirona','dipirona monoidratada, citrato de orfenadrina, cafeina anidra'))
        self.assertFalse(suspected_combination('Dipirona','dipirona monoidratada, dipirona'))
        self.assertFalse(suspected_combination('Sertralina','cloridrato de sertralina'))

    def test_100_medicamentos_preservados(self):
        medications=json.loads((ROOT/'catalog_100.json').read_text(encoding='utf8'))
        self.assertEqual(len(medications),100)

if __name__=='__main__':unittest.main()
