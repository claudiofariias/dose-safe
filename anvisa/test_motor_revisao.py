import copy
import json
import tempfile
import unittest
from pathlib import Path

import sys
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from clinical_rules import evaluate_dose,load_documented_rules,validate_rule


def fake_rule():
    """DADOS FICTÍCIOS. Não usar como prescrição ou referência clínica."""
    return {'id':'TESTE-FICTICIO-01','generic_name':'Medicamento fictício',
        'status':'documentada','product_registration':'123456789',
        'presentation':'Comprimido • 100 mg','form_kind':'tablet',
        'strength_value':100,'strength_unit':'mg','route':'oral','indication':'Teste fictício',
        'age_min':18,'age_max':65,'dose_basis':'mg','dose_min':100,'dose_max':200,
        'daily_max_mg':400,'allowed_frequencies':['12/12h','24/24h'],
        'source_url':'https://consultas.anvisa.gov.br/api/consulta/medicamento/FICTICIO.pdf',
        'source_section':'8. POSOLOGIA E MODO DE USAR','source_page':5,
        'source_pdf_sha256':'b'*64, 'source_recorded_at':'2026-11-11'}


def fake_item():
    return {'anvisa_registration':'123456789','indication':'Teste fictício',
       'presentation_label':'Comprimido • 100 mg','form_kind':'tablet',
       'strength_value':100,'strength_unit':'mg','route':'oral',
       'dose_quantity':1,'frequency':'12/12h'}


class TestMotorClinico(unittest.TestCase):
    def setUp(self):
        self.rule=fake_rule()
        self.item=fake_item()
        self.patient={'age':25,'weight_kg':65}

    def test_sem_regra_nao_verificada(self):
        result=evaluate_dose('Medicamento fictício',self.item,self.patient,[])
        self.assertEqual(result['status'],'NAO_VERIFICADA')

    def test_dentro_da_referencia_numerica(self):
        validate_rule(self.rule)
        result=evaluate_dose('Medicamento fictício',self.item,self.patient,[self.rule])
        self.assertEqual(result['status'],'COMPATIVEL_COM_REFERENCIA')
        self.assertEqual(result['amount_mg'],100)
        self.assertEqual(result['daily_mg'],200)

    def test_dose_acima_da_referencia(self):
        self.item['dose_quantity']=3
        result=evaluate_dose('Medicamento fictício',self.item,self.patient,[self.rule])
        self.assertEqual(result['status'],'FORA_DA_REFERENCIA')
        self.assertEqual(result['severity'],'grave')

    def test_dose_abaixo_da_referencia(self):
        self.item['dose_quantity']=0.5
        result=evaluate_dose('Medicamento fictício',self.item,self.patient,[self.rule])
        self.assertEqual(result['status'],'FORA_DA_REFERENCIA')
        self.assertEqual(result['severity'],'moderado')

    def test_limite_diario(self):
        self.item['dose_quantity']=2
        self.item['frequency']='12/12h'
        self.assertEqual(evaluate_dose('Medicamento fictício',self.item,self.patient,[self.rule])['status'],'COMPATIVEL_COM_REFERENCIA')
        self.rule['daily_max_mg']=300
        self.assertEqual(evaluate_dose('Medicamento fictício',self.item,self.patient,[self.rule])['status'],'FORA_DA_REFERENCIA')

    def test_registro_indicacao_apresentacao_sem_correspondencia(self):
        for name, value in [('anvisa_registration','111111111'),('indication','Outro uso'),('presentation_label','Outro produto')]:
            item={**self.item,name:value}
            self.assertEqual(evaluate_dose('Medicamento fictício',item,self.patient,[self.rule])['status'],'NAO_VERIFICADA')

    def test_idade_ou_frequencia_nao_contemplada(self):
        self.assertEqual(evaluate_dose('Medicamento fictício',self.item,{'age':8,'weight_kg':25},[self.rule])['status'],'NAO_VERIFICADA')
        self.item['frequency']='8/8h'
        self.assertEqual(evaluate_dose('Medicamento fictício',self.item,self.patient,[self.rule])['status'],'NAO_VERIFICADA')

    def test_regra_mgkg_requer_peso(self):
        rule=copy.deepcopy(self.rule)
        rule.update({'dose_basis':'mg/kg','dose_min':5,'dose_max':20,'age_min':5,'age_max':17,
                     'weight_min':10,'weight_max':70})
        validate_rule(rule)
        patient={'age':8,'weight_kg':25}
        self.assertEqual(evaluate_dose('Medicamento fictício',self.item,patient,[rule])['status'],'FORA_DA_REFERENCIA')
        self.item['dose_quantity']=2
        self.assertEqual(evaluate_dose('Medicamento fictício',self.item,patient,[rule])['status'],'COMPATIVEL_COM_REFERENCIA')
        self.item['dose_quantity']=6
        self.assertEqual(evaluate_dose('Medicamento fictício',self.item,patient,[rule])['status'],'FORA_DA_REFERENCIA')

    def test_rascunho_nao_ativa_regra(self):
        pending={**self.rule,'status':'pendente'}
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'rules.json'
            source.write_text(json.dumps([pending]),encoding='utf-8')
            self.assertEqual(load_documented_rules(source),[])
            source.write_text(json.dumps([self.rule]),encoding='utf-8')
            self.assertEqual(len(load_documented_rules(source)),1)

    def test_regra_incompleta_rejeitada(self):
        rule=copy.deepcopy(self.rule)
        rule.pop('source_pdf_sha256')
        with self.assertRaises(ValueError): validate_rule(rule)

    def test_referencia_documentada_sem_profissional(self):
        # Documento ilustrativo: teste técnico; não é regra medicamentosa real.
        rule=copy.deepcopy(self.rule)
        self.assertNotIn('reviewer_name',rule)
        self.assertNotIn('reviewer_registration',rule)
        validate_rule(rule)
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'rules.json'
            target.write_text(json.dumps([rule]),encoding='utf-8')
            self.assertEqual(len(load_documented_rules(target)),1)

    def test_legado_aprovada_continua_compativel(self):
        legacy={**self.rule,'status':'aprovada','reviewed_at':'2026-11-11'}
        legacy.pop('source_recorded_at')
        validate_rule(legacy)
        self.assertEqual(evaluate_dose('Medicamento fictício',self.item,self.patient,[legacy])['status'],
                         'COMPATIVEL_COM_REFERENCIA')

    def test_sem_data_da_fonte_nao_ativa_regra(self):
        rule=copy.deepcopy(self.rule)
        rule.pop('source_recorded_at')
        with self.assertRaises(ValueError):validate_rule(rule)

    def test_status_nao_documentado_nunca_ativa(self):
        rule={**self.rule,'status':'rascunho'}
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'rules.json'
            target.write_text(json.dumps([rule]),encoding='utf-8')
            self.assertEqual(load_documented_rules(target),[])

    def test_interface_profissional_removida(self):
        app=(ROOT/'frontend/dist/js/App.js').read_text(encoding='utf8')
        profile=(ROOT/'frontend/dist/js/pages/ProfilePage.js').read_text(encoding='utf8')
        server=(ROOT/'server.py').read_text(encoding='utf8')
        self.assertNotIn('clinicalReview',app)
        self.assertNotIn('DOSE_SAFE_REVIEWER_EMAILS',server)
        self.assertNotIn('/api/clinical/review/',server)
        self.assertNotIn('Revisão clínica de regras',profile)
        self.assertIn('Referências de dose',profile)


if __name__=='__main__': unittest.main()
