# -*- coding: utf-8 -*-
"""Testes do coletor de fontes oficiais (09/11/2026). Rodar:
    python -I tests/test_coletar_precos_ceasas.py
As amostras em tests/fixtures/ são as páginas e PDFs REAIS de 09/11/2026 (nada fabricado);
as iscas são essas mesmas amostras com UMA coisa estragada, para provar que cada trava reprova.
"""
import sys
import unittest
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))
import coletar_precos_ceasas as c  # noqa: E402

FIX = RAIZ / 'tests' / 'fixtures'
HOJE = date(2026, 11, 9)


def ler(nome: str) -> str:
    return (FIX / nome).read_text(encoding='utf-8')


def pdf(nome: str) -> str:
    return c.texto_pdf((FIX / nome).read_bytes())


def por_praca(cots):
    return {x['ceasa']: x for x in cots}


class TestCeasaminas(unittest.TestCase):
    def test_estados_le_bh_sp_es_com_a_data_de_cada_coluna(self):
        p = por_praca(c.ler_ceasaminas_estados(ler('ceasaminas_estados_2026-11-09.html')))
        self.assertEqual(p['Belo Horizonte (CEASAMINAS)']['preco_kg'], 3.75)
        self.assertEqual(p['Belo Horizonte (CEASAMINAS)']['data_cotacao'], date(2026, 11, 9))
        self.assertEqual(p['São Paulo (CEAGESP)']['preco_kg'], 3.75)
        self.assertEqual(p['São Paulo (CEAGESP)']['data_cotacao'], date(2026, 11, 4))
        self.assertEqual(p['Vitória (CEASA ES)']['preco_kg'], 4.67)
        self.assertEqual(p['Vitória (CEASA ES)']['data_cotacao'], date(2026, 11, 6))

    def test_estados_rio_com_data_1900_vem_marcado_e_nao_entra_na_escolha(self):
        cots = c.ler_ceasaminas_estados(ler('ceasaminas_estados_2026-11-09.html'))
        rio = [x for x in cots if x['ceasa'].startswith('Rio')]
        self.assertTrue(all(x['data_cotacao'].year == 1900 for x in rio))
        self.assertFalse(any(x['ceasa'].startswith('Rio') for x in c.escolher(cots, HOJE)))

    def test_mg_le_reservas_uberlandia_e_juiz_de_fora(self):
        p = por_praca(c.ler_ceasaminas_mg(ler('ceasaminas_mg_2026-11-09.html')))
        self.assertEqual(p['Uberlândia (CEASAMINAS)']['preco_kg'], 3.13)
        self.assertEqual(p['Uberlândia (CEASAMINAS)']['data_cotacao'], date(2026, 11, 5))
        self.assertEqual(p['Juiz de Fora (CEASAMINAS)']['preco_kg'], 3.33)
        self.assertEqual(p['Juiz de Fora (CEASAMINAS)']['data_cotacao'], date(2026, 11, 2))

    def test_isca_sem_banana_prata_na_tabela_reprova(self):
        html = ler('ceasaminas_estados_2026-11-09.html').replace('BANANA-PRATA', 'BANANA-OUTRA')
        with self.assertRaises(c.ErroFonte):
            c.ler_ceasaminas_estados(html)

    def test_isca_unidade_que_nao_e_kg_reprova(self):
        html = ler('ceasaminas_estados_2026-11-09.html')
        i = html.index('BANANA-PRATA')
        html = html[:i] + html[i:].replace('>KG<', '>CX<', 1)
        with self.assertRaises(c.ErroFonte):
            c.ler_ceasaminas_estados(html)


class TestRio(unittest.TestCase):
    def test_pdf_real_modal_60_na_caixa_de_20kg_vira_3_reais(self):
        x = c.ler_rj(pdf('ceasarj_2026-11-09.pdf'))
        self.assertEqual(x['ceasa'], 'Rio de Janeiro (CEASA RJ)')
        self.assertEqual(x['preco_kg'], 3.0)
        self.assertEqual(x['data_cotacao'], date(2026, 11, 9))

    def test_isca_caixa_de_outro_peso_reprova(self):
        t = pdf('ceasarj_2026-11-09.pdf').replace('BANANA PRATA Extra Cx 20 kg', 'BANANA PRATA Extra Cx 18 kg')
        with self.assertRaises(c.ErroFonte):
            c.ler_rj(t)

    def test_isca_sem_a_linha_da_prata_reprova(self):
        t = pdf('ceasarj_2026-11-09.pdf').replace('BANANA PRATA', 'BANANA XXXXX')
        with self.assertRaises(c.ErroFonte):
            c.ler_rj(t)

    def test_isca_sem_data_reprova(self):
        t = pdf('ceasarj_2026-11-09.pdf').replace('09/11/2026', 'xx/xx/xxxx')
        with self.assertRaises(c.ErroFonte):
            c.ler_rj(t)


class TestCuritiba(unittest.TestCase):
    def test_pdf_real_mais_comum_80_na_caixa_de_20kg_vira_4_reais(self):
        x = c.ler_pr_curitiba(pdf('ceasapr_curitiba_2026-11-09.pdf'))
        self.assertEqual(x['ceasa'], 'Curitiba (CEASA PR)')
        self.assertEqual(x['preco_kg'], 4.0)
        self.assertEqual(x['data_cotacao'], date(2026, 11, 9))

    def test_isca_pdf_de_outro_mercado_reprova(self):
        t = pdf('ceasapr_curitiba_2026-11-09.pdf').replace('CEASA - CURITIBA', 'CEASA - MARINGA')
        with self.assertRaises(c.ErroFonte):
            c.ler_pr_curitiba(t)

    def test_isca_caixa_de_outro_peso_reprova(self):
        t = pdf('ceasapr_curitiba_2026-11-09.pdf').replace('PRATA cx 20 kg', 'PRATA cx 13kg')
        with self.assertRaises(c.ErroFonte):
            c.ler_pr_curitiba(t)

    def test_prata_so_vale_dentro_do_bloco_banana(self):
        # "PRATA" fora do bloco BANANA (ex.: outro produto) não pode ser lido como banana
        t = pdf('ceasapr_curitiba_2026-11-09.pdf').replace('\nBANANA\n', '\nBANANAS IMPORTADAS\n')
        with self.assertRaises(c.ErroFonte):
            c.ler_pr_curitiba(t)


class TestLinks(unittest.TestCase):
    def test_rj_acha_o_pdf_de_cada_dia_inclusive_com_sufixo(self):
        html = ('<a href="/ceasa/sites/default/files/arquivos_paginas/Boletim%20di%C3%A1rio%20de%20pre%C3%A7os%20%2009%2011%202026.pdf">x</a>'
                '<a href="/ceasa/sites/default/files/arquivos_paginas/Boletim%20di%C3%A1rio%20de%20pre%C3%A7os%20%2003%2011%202026_0.pdf">y</a>')
        links = c.links_rj(html)
        self.assertEqual(sorted(links), [date(2026, 11, 3), date(2026, 11, 9)])
        self.assertTrue(links[date(2026, 11, 3)].startswith('https://www.rj.gov.br/ceasa/sites/'))

    def test_pr_acha_so_os_pdfs_de_curitiba(self):
        html = ('<a href="https://www.ceasa.pr.gov.br/sites/ceasa/arquivos_restritos/files/documento/2026-11/cotacaopdf09112026.pdf">c</a>'
                '<a href="/sites/ceasa/arquivos_restritos/files/documento/2026-10/cotacaopdf02102026_0.pdf">c2</a>'
                '<a href="https://www.ceasa.pr.gov.br/sites/ceasa/arquivos_restritos/files/documento/2026-11/manovembro_09112026.pdf">maringa</a>')
        links = c.links_pr(html)
        self.assertEqual(sorted(links), [date(2026, 10, 2), date(2026, 11, 9)])
        self.assertTrue(links[date(2026, 10, 2)].startswith('https://www.ceasa.pr.gov.br/sites/'))


def cot(ceasa, preco, dia):
    return {'ceasa': ceasa, 'preco_kg': preco, 'data_cotacao': dia, 'fonte': 'x'}


class TestEscolha(unittest.TestCase):
    TODAS = [cot('Juiz de Fora (CEASAMINAS)', 3.33, date(2026, 11, 2)),
             cot('Vitória (CEASA ES)', 4.67, date(2026, 11, 6)),
             cot('Curitiba (CEASA PR)', 4.0, date(2026, 11, 9)),
             cot('Rio de Janeiro (CEASA RJ)', 3.0, date(2026, 11, 9)),
             cot('São Paulo (CEAGESP)', 3.75, date(2026, 11, 4)),
             cot('Belo Horizonte (CEASAMINAS)', 3.75, date(2026, 11, 9)),
             cot('Uberlândia (CEASAMINAS)', 3.13, date(2026, 11, 5))]

    def test_cinco_pela_prioridade(self):
        nomes = [x['ceasa'] for x in c.escolher(self.TODAS, HOJE)]
        self.assertEqual(nomes, ['Belo Horizonte (CEASAMINAS)', 'São Paulo (CEAGESP)', 'Rio de Janeiro (CEASA RJ)',
                                 'Curitiba (CEASA PR)', 'Vitória (CEASA ES)'])

    def test_reserva_entra_quando_falta_uma(self):
        sem_curitiba = [x for x in self.TODAS if not x['ceasa'].startswith('Curitiba')]
        nomes = [x['ceasa'] for x in c.escolher(sem_curitiba, HOJE)]
        self.assertEqual(len(nomes), 5)
        self.assertIn('Uberlândia (CEASAMINAS)', nomes)

    def test_cotacao_velha_e_preco_fora_da_faixa_ficam_de_fora(self):
        cots = [cot('Belo Horizonte (CEASAMINAS)', 3.75, date(2026, 10, 30)),   # 10 dias
                cot('São Paulo (CEAGESP)', 37.5, date(2026, 11, 4))]            # vírgula perdida
        self.assertEqual(c.escolher(cots, HOJE), [])

    def test_o_mesmo_dia_pode_ter_duas_leituras_da_mesma_praca_vale_a_mais_nova(self):
        cots = [cot('Rio de Janeiro (CEASA RJ)', 3.0, date(2026, 11, 6)),
                cot('Rio de Janeiro (CEASA RJ)', 3.25, date(2026, 11, 9))]
        self.assertEqual(c.escolher(cots, HOJE)[0]['preco_kg'], 3.25)

    def test_nomes_sao_os_que_o_boletim_espera(self):
        # o boletim casa praças pelo nome (variação semanal, preferência BH/SP/Campinas) — nome novo quebra tudo
        esperados = {'Belo Horizonte (CEASAMINAS)', 'São Paulo (CEAGESP)', 'Rio de Janeiro (CEASA RJ)',
                     'Curitiba (CEASA PR)', 'Vitória (CEASA ES)', 'Uberlândia (CEASAMINAS)', 'Juiz de Fora (CEASAMINAS)'}
        self.assertEqual({nome for nome in c.PRIORIDADE}, esperados)


class TestCongelamento(unittest.TestCase):
    def vetor(self, dia):
        return [{'ceasa': 'A', 'preco_kg': 3.0, 'data_cotacao': dia}, {'ceasa': 'B', 'preco_kg': 4.0, 'data_cotacao': dia}]

    def test_mesmos_precos_e_mesmas_datas_por_5_arquivos_e_fonte_parada(self):
        anteriores = [self.vetor(date(2026, 11, 2))] * 5
        with self.assertRaises(c.ErroGuardrail):
            c.checar_congelamento(self.vetor(date(2026, 11, 2)), anteriores)

    def test_mesmos_precos_com_datas_andando_e_mercado_estavel_nao_alarme(self):
        anteriores = [self.vetor(date(2026, 11, d)) for d in (2, 3, 4, 5, 6)]
        c.checar_congelamento(self.vetor(date(2026, 11, 9)), anteriores)  # não levanta

    def test_poucos_arquivos_anteriores_nao_julga(self):
        c.checar_congelamento(self.vetor(date(2026, 11, 2)), [self.vetor(date(2026, 11, 2))] * 2)


class TestCsv(unittest.TestCase):
    def test_nenhuma_fonte_tem_virgula(self):
        # o boletim lê o CSV com split(',') simples (parsePrecosCsv): vírgula na fonte viraria aspas no rodapé
        fontes = [c.ler_rj(pdf('ceasarj_2026-11-09.pdf'))['fonte'],
                  c.ler_pr_curitiba(pdf('ceasapr_curitiba_2026-11-09.pdf'))['fonte'],
                  *[x['fonte'] for x in c.ler_ceasaminas_estados(ler('ceasaminas_estados_2026-11-09.html'))],
                  *[x['fonte'] for x in c.ler_ceasaminas_mg(ler('ceasaminas_mg_2026-11-09.html'))]]
        for f in fontes:
            self.assertNotIn(',', f)
            self.assertNotIn('"', '\n'.join(c.linhas_csv([cot('Rio de Janeiro (CEASA RJ)', 3.0, date(2026, 11, 9)) | {'fonte': f}])))

    def test_formato_igual_ao_que_o_boletim_le(self):
        linhas = c.linhas_csv([cot('Rio de Janeiro (CEASA RJ)', 3.0, date(2026, 11, 9))])
        self.assertEqual(linhas, ['ceasa,preco_kg,data_cotacao,fonte', 'Rio de Janeiro (CEASA RJ),3.0,2026-11-09,x'])


if __name__ == '__main__':
    unittest.main(verbosity=1)
