import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).parent))
import sincronizar_anvisa as a


class TesteAnvisa(unittest.TestCase):
    def test_nomes_com_acentos_e_sais(self):
        self.assertTrue(a.med_matches('Ácido acetilsalicílico','ÁCIDO ACETILSALICÍLICO'))
        self.assertTrue(a.med_matches('Sertralina','CLORIDRATO DE SERTRALINA'))
        self.assertTrue(a.med_matches('Sulfametoxazol + Trimetoprima','SULFAMETOXAZOL + TRIMETOPRIMA'))
        self.assertFalse(a.med_matches('Lítio','sulfato de magnésio'))
        self.assertFalse(a.med_matches('Codeína','Dihidrocodeína'))

    def test_csv_local_com_separador_e_acentos(self):
        catalog=[{'generic_name':'Dipirona'},{'generic_name':'Ibuprofeno'}]
        content='PRINCIPIO_ATIVO;NOME_PRODUTO;NUMERO_REGISTRO_PRODUTO;SITUACAO_REGISTRO\nDIPIRONA;PRODUTO TESTE;123456789;Válido\nIBUPROFENO;PRODUTO 2;234567891;Inativo\n'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'med.csv'
            p.write_bytes(content.encode('cp1252'))
            records,total,counts=a.aggregate_csv(p,catalog)
        self.assertEqual(total,2)
        self.assertEqual(len(records[a.norm('Dipirona')]),1)
        self.assertEqual(records[a.norm('Ibuprofeno')][0]['situacao_registro'],'Inativo')

    def test_secao_pendente_nao_e_regra(self):
        text='''8. POSOLOGIA E MODO DE USAR\nExemplo de dose para extracao sem validade clinica.\n9. REAÇÕES ADVERSAS\nEfeitos.\n'''
        parts=a.extracted_sections(text)
        self.assertEqual(parts['posologia']['status'],'trecho_candidato_revisar')
        self.assertNotIn('Efeitos.',parts['posologia']['texto'])

    def test_importacao_pdf_profissional_sem_ativar_regra(self):
        try:
            import fitz
            from pypdf import PdfReader
        except ImportError:
            self.skipTest('Bibliotecas PDF de teste nao disponiveis')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            folder=root/'bulas_profissional'
            folder.mkdir()
            pdf=folder/'dipirona.pdf'
            doc=fitz.open()
            page=doc.new_page()
            page.insert_text((72,90),'8. POSOLOGIA E MODO DE USAR\nConteudo TESTE, sem valor clinico.\n9. REACOES ADVERSAS')
            doc.save(pdf)
            doc.close()
            bindings=[{'medicamento':'Dipirona','arquivo':'dipirona.pdf','tipo_bula':'profissional',
                       'numero_registro':'111111111','data_consulta':'2026-11-11',
                       'fonte_url':'https://consultas.anvisa.gov.br/#/bulario/'}]
            (root/'vinculos_bulas.json').write_text(json.dumps(bindings),encoding='utf-8')
            with patch.object(a,'ANVISA_DIR',root):
                rows,problems=a.extract_pdfs([{'generic_name':'Dipirona'}])
            self.assertEqual(problems,[])
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['status'],'EXTRAIDO_PENDENTE_CADASTRO_DOCUMENTAL')
            self.assertFalse(rows[0]['regra_ativada'])
            self.assertEqual(len(rows[0]['sha256_pdf']),64)

    def test_catalogo_100_sem_fontes_nao_inventa_regras(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(a,'OUTPUT',Path(tmp)):
                code=a.main([])
                report=json.loads((Path(tmp)/'catalogo_anvisa_revisao.json').read_text(encoding='utf-8'))
                pdfs=json.loads((Path(tmp)/'extracoes_bulas_pendentes.json').read_text(encoding='utf-8'))
            self.assertEqual(code,0)
            self.assertEqual(len(report['medicamentos']),100)
            self.assertTrue(all(x['status_posologia']=='NAO_VALIDADA' for x in report['medicamentos']))
            self.assertEqual(len(pdfs['bulas']),0)

if __name__=='__main__': unittest.main()
