# -*- coding: utf-8 -*-
"""
Testes do coletor do IMA-MG — foco na resiliência de rede.

Motivo: em 10/08/2026 um único ConnectTimeout na página de listagem derrubou a
coleta inteira (exit 1, zero dado) e o boletim daquela manhã saiu sem as cenas de
embarques, mesmo com o IMA tendo publicado o arquivo de 02-09/08 naquele dia.
O site responde em ~15 s quando responde — é lento, não está fora.

Rodar: python -m unittest test_coletar_ima_ptv -v   (só precisa de `requests`)
"""
import contextlib
import datetime
import io
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


def _linhas(cabecalho, *dados):
    return [tuple(cabecalho), *(tuple(d) for d in dados)]


# Os dois formatos REAIS que o IMA já publicou — copiados dos arquivos no ar em
# 10/08/2026, não inventados. Formato velho ressuscita (voltou em 02-09/08), então
# os dois ficam cobertos para sempre. Repare que a ORDEM das colunas muda inteira
# entre eles: é por isso que nada aqui pode ser posicional.
CAB_ANTIGO = ['Data de Emissão da PTV', 'Cod. Município origem', 'Município de origem',
              'Cod. Município de Destino', 'Município de Destino', 'Cultura',
              'Variedade', 'Carga', 'Unidade de medida', '']
LINHA_ANTIGA = ['2026-08-05 07:53:06.203', '3116506', 'CLARO DOS POÇÕES', '3306200',
                'RIO DE JANEIRO', 'BANANA', 'PRATA GORUTUBA', '4.2', 'TONELADA(S)', '']
TITULO_NOVO = ['PTV_BANANA_20200727A20260729', None, None, None, None, None, None,
               None, None, None]
CAB_NOVO = ['dt_emissao', 'tp_documento_fundamentacao', 'cod_muni_origem',
            'municipio_origem', 'cod_muni_destino', 'municipio_destino', 'nm_cultura',
            'nm_variedade', 'total_carga', 'ds_unidade_medida']
LINHA_NOVA = ['2026-07-27 08:44:22.054', 'CFO', '3167202', 'SETE LAGOAS', '3304557',
              'RIO DE JANEIRO', 'BANANA', 'GRANDE NAINE', '7210.0', 'UNIDADES']


class TestFormatosReais(unittest.TestCase):
    def test_formato_antigo_sem_documento(self):
        _, mapa, metodos, _ = c._mapear_colunas(_linhas(CAB_ANTIGO, LINHA_ANTIGA, LINHA_ANTIGA))
        self.assertIsNotNone(mapa)
        self.assertEqual(mapa["origem"], 2)
        self.assertEqual(mapa["destino"], 4)
        self.assertEqual(mapa["carga"], 7)
        self.assertNotIn("documento", mapa, "layout antigo não tem a dimensão CFO")
        self.assertTrue(all(m == "nome" for m in metodos.values()))

    def test_formato_novo_com_documento_e_linha_de_titulo(self):
        linhas = _linhas(TITULO_NOVO, CAB_NOVO, LINHA_NOVA, LINHA_NOVA)
        idx_cab, mapa, metodos, _ = c._mapear_colunas(linhas)
        self.assertEqual(idx_cab, 1, "o cabeçalho está abaixo da linha de título")
        self.assertIsNotNone(mapa)
        self.assertEqual(mapa["documento"], 1)
        self.assertEqual(mapa["origem"], 3)
        self.assertEqual(mapa["destino"], 5)
        self.assertEqual(mapa["carga"], 8)
        self.assertTrue(all(m == "nome" for m in metodos.values()))

    def test_cod_muni_origem_nao_e_confundido_com_o_nome_do_municipio(self):
        _, mapa, _, _ = c._mapear_colunas(_linhas(TITULO_NOVO, CAB_NOVO, LINHA_NOVA))
        self.assertNotEqual(mapa["origem"], 2, "coluna de CÓDIGO não pode virar origem")

    def test_cabecalho_totalmente_renomeado_ainda_e_lido(self):
        """O que o nome não acha, o conteúdo acha — menos origem/destino, que exigem prova."""
        cab = ['aaa', 'bbb', 'ccc', 'ddd', 'eee', 'fff', 'ggg', 'hhh', 'iii', 'jjj']
        _, mapa, metodos, _ = c._mapear_colunas(_linhas(cab, *([LINHA_NOVA] * 8)))
        self.assertIsNotNone(mapa, "renomear tudo não pode derrubar a importação")
        for campo in ("data", "carga", "variedade", "documento", "unidade"):
            self.assertEqual(metodos[campo], "conteudo", f"{campo} deveria vir do conteúdo")
        # origem/destino saem do código IBGE: 31xxxxx é MG (origem), 33xxxxx é RJ
        self.assertEqual(metodos["origem"], "codigo-ibge")
        self.assertEqual(mapa["origem"], 3)
        self.assertEqual(mapa["destino"], 5)

    def test_nao_confunde_codigo_ibge_com_carga(self):
        _, mapa, _, _ = c._mapear_colunas(_linhas(CAB_ANTIGO, *([LINHA_ANTIGA] * 5)))
        self.assertEqual(mapa["carga"], 7, "7 dígitos de código IBGE não é carga")

    def test_origem_ambigua_nao_chuta(self):
        """Duas colunas de município as duas em MG: sem prova, não inventa a ordem."""
        cab = ['aaa', 'bbb', 'ccc', 'ddd', 'eee', 'fff', 'ggg', 'hhh', 'iii', 'jjj']
        linha = ['2026-07-25', 'CFO', '3136702', 'JAÍBA', '3106200', 'BELO HORIZONTE',
                 'BANANA', 'PRATA ANÃ', '12.5', 'TONELADA(S)']
        _, mapa, metodos, _ = c._mapear_colunas(_linhas(cab, *([linha] * 8)))
        self.assertIsNone(mapa, "sem prova de qual é a origem, tem que falhar alto")
        self.assertNotIn("origem", metodos)


class TestEstadoDaFonte(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = pathlib.Path(self.tmp.name)
        for p in (mock.patch.object(c, "ESTADO_FONTE", d / "estado.json"),
                  mock.patch.object(c, "AVISO_MUDANCA", d / "aviso.txt")):
            p.start()
            self.addCleanup(p.stop)

    def test_primeira_rodada_registra_sem_alarme(self):
        c.conferir_formato_da_fonte({"campos": {"data": "nome"}, "cabecalho": ["x"]})
        self.assertTrue(c.ESTADO_FONTE.exists())
        self.assertFalse(c.AVISO_MUDANCA.exists(), "1ª rodada não tem com o que comparar")

    def test_formato_igual_nao_gera_aviso(self):
        layout = {"campos": {"data": "nome", "documento": "nome"}, "cabecalho": ["x"]}
        c.conferir_formato_da_fonte(layout)
        c.conferir_formato_da_fonte(layout)
        self.assertFalse(c.AVISO_MUDANCA.exists(), "sem mudança, sem ruído")

    def test_coluna_que_some_gera_aviso_com_a_consequencia(self):
        c.conferir_formato_da_fonte({"campos": {"data": "nome", "documento": "nome"},
                                     "cabecalho": ["a", "b"]})
        c.conferir_formato_da_fonte({"campos": {"data": "nome"}, "cabecalho": ["a"]})
        self.assertTrue(c.AVISO_MUDANCA.exists())
        txt = c.AVISO_MUDANCA.read_text(encoding="utf-8")
        self.assertIn("SUMIU", txt)
        self.assertIn("ranking de origem e destino", txt, "tem que dizer o efeito prático")
        self.assertIn("a coleta funcionou", txt.lower(), "mudança absorvida não é erro")

    def test_coluna_que_volta_tambem_avisa(self):
        c.conferir_formato_da_fonte({"campos": {"data": "nome"}, "cabecalho": ["a"]})
        c.conferir_formato_da_fonte({"campos": {"data": "nome", "documento": "nome"},
                                     "cabecalho": ["a", "b"]})
        self.assertIn("VOLTOU", c.AVISO_MUDANCA.read_text(encoding="utf-8"))

    def test_renomear_coluna_avisa_mesmo_sem_perder_dado(self):
        c.conferir_formato_da_fonte({"campos": {"data": "nome"}, "cabecalho": ["a"]})
        c.conferir_formato_da_fonte({"campos": {"data": "conteudo"}, "cabecalho": ["zzz"]})
        self.assertIn("renomeou", c.AVISO_MUDANCA.read_text(encoding="utf-8"))


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
        # um registro por planilha: 0 registros agora é falha (guard do .xls mudo)
        um_registro = [(hoje, "JAÍBA", "BELO HORIZONTE", "PRATA ANÃ", 1.0, "cfo")]
        self.patches = [
            mock.patch.object(c, "CSV_DIARIO", diario),
            mock.patch.object(c, "CSV_MUNICIPIOS", pathlib.Path(self.tmp.name) / "mun.csv"),
            mock.patch.object(c, "ESTADO_FONTE", pathlib.Path(self.tmp.name) / "estado.json"),
            mock.patch.object(c, "AVISO_MUDANCA", pathlib.Path(self.tmp.name) / "aviso.txt"),
            mock.patch.object(c, "iterar_linhas_excel",
                              lambda conteudo, url, layout=None: iter(um_registro)),
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

    def test_planilha_que_parseia_zero_registros_conta_como_FALHA(self):
        """O .xls de 11-13/05 entrou mudo com '0 registros' — nunca mais em silêncio."""
        hoje = datetime.date.today().isoformat()
        cheia = [(hoje, "JAÍBA", "RIO DE JANEIRO", "PRATA ANÃ", 1.0, "cfo")]

        def parse(conteudo, url, layout=None):
            return iter(cheia if url.endswith("boa.xlsx") else ())

        saida = io.StringIO()
        with mock.patch.object(c, "listar_urls_planilhas",
                               return_value=["https://ima/boa.xlsx", "https://ima/muda.xlsx"]), \
             mock.patch.object(c, "get_com_retry", return_value=_resposta_ok()), \
             mock.patch.object(c, "iterar_linhas_excel", parse), \
             contextlib.redirect_stdout(saida):
            resultado = c.coletar()

        texto = saida.getvalue()
        self.assertEqual(resultado, 0, "uma planilha muda não derruba a coleta inteira")
        self.assertIn("FALHA em https://ima/muda.xlsx", texto)
        self.assertIn("0 registros aproveitados", texto)
        self.assertNotIn("ok: /muda.xlsx", texto, "muda NUNCA pode ser reportada como ok")

    def test_sem_estouro_baixa_todas(self):
        urls = [f"https://ima/f{n}.xlsx" for n in range(5)]
        with mock.patch.object(c, "listar_urls_planilhas", return_value=urls), \
             mock.patch.object(c, "get_com_retry", return_value=_resposta_ok()) as get:
            saida = c.coletar()
        self.assertEqual(saida, 0)
        self.assertEqual(get.call_count, len(urls))


if __name__ == "__main__":
    unittest.main()
