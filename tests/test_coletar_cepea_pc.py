# -*- coding: utf-8 -*-
"""Testes do coletor HONESTO do CEPEA pelo PC (09/11/2026). Rodar: python -I tests/test_coletar_cepea_pc.py
O antigo (coletar_cepea_banana.py) passava pela proteção do site disfarçado e foi aposentado. Este se identifica,
faz 1 pedido por semana e, se a proteção barrar, PARA — nunca tenta de outro jeito."""
import sys
import unittest
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))
import coletar_cepea_pc as c  # noqa: E402

HOJE = date(2026, 11, 13)
# tabela no formato que o coletor antigo lia: Produto | Região | Unidade | <semana 1> | ... | <semana N>
HTML = '''<html><head><title>Banana - HF Brasil</title></head><body>
<table class="tabela"><thead><tr><th>Produto</th><th>Região</th><th>Unidade</th><th>30/out</th><th>06/nov</th></tr></thead>
<tbody>
<tr><td>Prata anã primeira - produtor</td><td>Norte de Minas Gerais</td><td>quilograma</td><td>2,59</td><td><span>2,70</span></td></tr>
<tr><td>Nanica primeira - produtor</td><td>Norte de Minas Gerais</td><td>quilograma</td><td>1,13</td><td>- - -</td></tr>
</tbody></table>
<table><tr><td>outra tabela qualquer</td></tr></table>
</body></html>'''


class TestBloqueio(unittest.TestCase):
    def test_desafio_do_cloudflare_e_bloqueio(self):
        self.assertTrue(c.bloqueado(403, '<html><title>Just a moment...</title></html>'))
        self.assertTrue(c.bloqueado(200, '<html><title>Um momento…</title><script src="/cdn-cgi/challenge-platform/x"></script></html>'))
        self.assertTrue(c.bloqueado(503, 'qualquer'))

    def test_pagina_normal_nao_e_bloqueio(self):
        self.assertFalse(c.bloqueado(200, HTML))


class TestTabela(unittest.TestCase):
    def test_le_so_a_primeira_tabela_com_texto_limpo(self):
        linhas = c.ler_tabela(HTML)
        self.assertEqual(linhas[0], ['Produto', 'Região', 'Unidade', '30/out', '06/nov'])
        self.assertEqual(linhas[1], ['Prata anã primeira - produtor', 'Norte de Minas Gerais', 'quilograma', '2,59', '2,70'])
        self.assertEqual(len(linhas), 3)

    def test_sem_tabela_e_erro(self):
        with self.assertRaises(c.ErroCepea):
            c.ler_tabela('<html><body>sem tabela</body></html>')


class TestSerie(unittest.TestCase):
    EXISTENTES = [{'data_cotacao': '2026-10-30', 'produto': 'Prata anã primeira - produtor', 'regiao': 'Norte de Minas Gerais',
                   'unidade': 'quilograma', 'preco': '2.59', 'fonte': c.FONTE}]

    def test_so_entra_o_que_e_novo_e_tem_preco(self):
        novos = c.novas_cotacoes(c.ler_tabela(HTML), self.EXISTENTES, HOJE)
        self.assertEqual([(n['data_cotacao'], n['produto'], n['preco']) for n in novos], [
            ('2026-11-06', 'Prata anã primeira - produtor', '2.70'),
            ('2026-10-30', 'Nanica primeira - produtor', '1.13')])   # "- - -" = sem cotação, fica de fora

    def test_virada_de_ano_dez_visto_em_janeiro_e_do_ano_passado(self):
        self.assertEqual(c.data_iso('26/dez', date(2027, 1, 8)), '2026-12-26')
        self.assertEqual(c.data_iso('06/nov', HOJE), '2026-11-06')

    def test_em_dia_nao_pede_a_pagina(self):
        # cortesia com o site: só pede quando já pode haver semana nova (a última tem 7 dias ou mais)
        self.assertTrue(c.em_dia([{'data_cotacao': '2026-11-06'}], date(2026, 11, 12)))
        self.assertFalse(c.em_dia([{'data_cotacao': '2026-11-06'}], date(2026, 11, 13)))
        self.assertFalse(c.em_dia([], HOJE))


if __name__ == '__main__':
    unittest.main(verbosity=1)
