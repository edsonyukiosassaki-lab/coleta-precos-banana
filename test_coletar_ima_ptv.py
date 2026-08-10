# -*- coding: utf-8 -*-
"""
Testes do coletor do IMA-MG — foco na resiliência de rede.

Motivo: em 10/08/2026 um único ConnectTimeout na página de listagem derrubou a
coleta inteira (exit 1, zero dado) e o boletim daquela manhã saiu sem as cenas de
embarques, mesmo com o IMA tendo publicado o arquivo de 02-09/08 naquele dia.
O site responde em ~15 s quando responde — é lento, não está fora.

Rodar: python -m unittest test_coletar_ima_ptv -v   (só precisa de `requests`)
"""
import datetime
import pathlib
import tempfile
import unittest
from unittest import mock

import requests

import coletar_ima_ptv as c


def _resposta_ok(texto=""):
    resp = mock.Mock(text=texto, content=b"")
    resp.raise_for_status.return_value = None
    return resp


def _sem_dormir(_segundos):
    """Zera a espera do backoff para o teste rodar instantâneo."""


class TestGetComRetry(unittest.TestCase):
    def test_repete_apos_connect_timeout_e_devolve_a_resposta_boa(self):
        boa = _resposta_ok()
        alvo = mock.patch.object(
            c.requests, "get",
            side_effect=[requests.exceptions.ConnectTimeout("timeout"), boa],
        )
        with alvo as get:
            resp = c.get_com_retry("https://ima/x", (15, 60), 4, dormir=_sem_dormir)
        self.assertIs(resp, boa)
        self.assertEqual(get.call_count, 2, "deveria ter tentado de novo após o timeout")

    def test_repete_em_erro_5xx_do_servidor(self):
        # com response anexado, como o raise_for_status real faz — senão o teste
        # passaria pelo ramo de "erro de rede" sem nunca exercitar o 5xx
        indisponivel = mock.Mock()
        indisponivel.status_code = 503
        ruim = mock.Mock()
        ruim.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "503", response=indisponivel)
        boa = _resposta_ok()
        with mock.patch.object(c.requests, "get", side_effect=[ruim, boa]) as get:
            resp = c.get_com_retry("https://ima/x", (15, 60), 3, dormir=_sem_dormir)
        self.assertIs(resp, boa)
        self.assertEqual(get.call_count, 2)

    def test_nao_repete_em_404(self):
        """Planilha que saiu do ar é resposta definitiva — insistir gasta o teto."""
        sumiu = mock.Mock()
        sumiu.status_code = 404
        erro = requests.exceptions.HTTPError("404", response=sumiu)
        ruim = mock.Mock()
        ruim.raise_for_status.side_effect = erro
        with mock.patch.object(c.requests, "get", return_value=ruim) as get:
            with self.assertRaises(requests.exceptions.HTTPError):
                c.get_com_retry("https://ima/sumiu.xlsx", (15, 60), 4, dormir=_sem_dormir)
        self.assertEqual(get.call_count, 1, "404 não deve ser repetido")

    def test_repete_em_429(self):
        """429 é 'volte depois' — exatamente o caso de esperar e tentar de novo."""
        limitado = mock.Mock()
        limitado.status_code = 429
        ruim = mock.Mock()
        ruim.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "429", response=limitado)
        boa = _resposta_ok()
        with mock.patch.object(c.requests, "get", side_effect=[ruim, boa]) as get:
            resp = c.get_com_retry("https://ima/x", (15, 60), 3, dormir=_sem_dormir)
        self.assertIs(resp, boa)
        self.assertEqual(get.call_count, 2)

    def test_desiste_no_limite_e_propaga_o_erro(self):
        erro = requests.exceptions.ConnectTimeout("timeout")
        with mock.patch.object(c.requests, "get", side_effect=erro) as get:
            with self.assertRaises(requests.exceptions.ConnectTimeout):
                c.get_com_retry("https://ima/x", (15, 60), 3, dormir=_sem_dormir)
        self.assertEqual(get.call_count, 3, "deve parar exatamente no nº de tentativas")

    def test_espera_cresce_entre_as_tentativas(self):
        esperas = []
        erro = requests.exceptions.ConnectTimeout("timeout")
        with mock.patch.object(c.requests, "get", side_effect=erro):
            with self.assertRaises(requests.exceptions.ConnectTimeout):
                c.get_com_retry("https://ima/x", (15, 60), 4, dormir=esperas.append)
        self.assertEqual(esperas, [5, 10, 20], "backoff deve dobrar e não esperar após a última")

    def test_sucesso_de_primeira_nao_espera(self):
        esperas = []
        with mock.patch.object(c.requests, "get", return_value=_resposta_ok()):
            c.get_com_retry("https://ima/x", (15, 60), 4, dormir=esperas.append)
        self.assertEqual(esperas, [])


class TestListagem(unittest.TestCase):
    HTML = (
        '<a href="https://ima/files/a.xlsx">planilha</a>'
        '<a href="https://ima/files/a.xlsx">o mesmo link repetido</a>'
        '<a href="https://ima/files/b.xls">outra</a>'
        '<a href="https://ima/files/c.pdf">nao e planilha</a>'
    )

    def test_listagem_sobrevive_a_um_timeout(self):
        boa = _resposta_ok(self.HTML)
        efeitos = [requests.exceptions.ConnectTimeout("timeout"), boa]
        with mock.patch.object(c.requests, "get", side_effect=efeitos):
            with mock.patch.object(c.time, "sleep", _sem_dormir):
                urls = c.listar_urls_planilhas()
        self.assertEqual(urls, ["https://ima/files/a.xlsx", "https://ima/files/b.xls"])

    def test_timeout_persistente_ainda_falha(self):
        """Queda real do IMA continua sendo falha visível — silêncio seria pior."""
        erro = requests.exceptions.ConnectTimeout("timeout")
        with mock.patch.object(c.requests, "get", side_effect=erro):
            with mock.patch.object(c.time, "sleep", _sem_dormir):
                with self.assertRaises(requests.exceptions.ConnectTimeout):
                    c.listar_urls_planilhas()


class TestTetoDeTempo(unittest.TestCase):
    """O retry não pode virar uma pendura de horas quando o IMA está lento."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        hoje = datetime.date.today().isoformat()
        diario = pathlib.Path(self.tmp.name) / "diario.csv"
        diario.write_text(
            "data,ptvs,total_t,prata_t,nanica_t,outras_t,"
            "cfo_ptvs,cfo_total_t,cfo_prata_t,cfo_nanica_t,cfo_outras_t\n"
            f"{hoje},10,100.0,60.0,40.0,0.0,,,,,\n",
            encoding="utf-8",
        )
        self.patches = [
            mock.patch.object(c, "CSV_DIARIO", diario),
            mock.patch.object(c, "CSV_MUNICIPIOS", pathlib.Path(self.tmp.name) / "mun.csv"),
            mock.patch.object(c, "iterar_linhas_excel", lambda conteudo, url: iter(())),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_para_de_baixar_ao_estourar_o_teto(self):
        urls = [f"https://ima/f{n}.xlsx" for n in range(30)]
        # relógio falso: cada download "gasta" 60 s; o teto de 12 min corta na 12ª
        relogio = {"t": 0.0}

        def monotonic_falso():
            return relogio["t"]

        def get_falso(*_a, **_k):
            relogio["t"] += 60.0
            return _resposta_ok()

        with mock.patch.object(c, "listar_urls_planilhas", return_value=urls), \
             mock.patch.object(c, "get_com_retry", side_effect=get_falso) as get, \
             mock.patch.object(c.time, "monotonic", monotonic_falso):
            saida = c.coletar()

        self.assertEqual(saida, 0, "teto estourado degrada, não derruba a coleta")
        self.assertEqual(get.call_count, 13, "deve parar assim que passar de 12 min")
        self.assertLess(get.call_count, len(urls), "não pode baixar tudo depois do teto")

    def test_sem_estouro_baixa_todas(self):
        urls = [f"https://ima/f{n}.xlsx" for n in range(5)]
        with mock.patch.object(c, "listar_urls_planilhas", return_value=urls), \
             mock.patch.object(c, "get_com_retry", return_value=_resposta_ok()) as get:
            saida = c.coletar()
        self.assertEqual(saida, 0)
        self.assertEqual(get.call_count, len(urls))


if __name__ == "__main__":
    unittest.main()
