# -*- coding: utf-8 -*-
"""
Coletor IMA-MG — Permissões de Trânsito Vegetal (PTV) de banana.

Fonte: https://www.ima.mg.gov.br/14-transparencia/2599-permissao-de-transito-vegetal-banana-2026
O IMA publica planilhas Excel a cada 3-5 dias com todas as PTVs de banana emitidas
em MG (data de emissão, município de origem/destino, variedade, carga).

Peculiaridade dos arquivos: os mais antigos são ACUMULATIVOS (janela de ~30 dias) e
se sobrepõem; os recentes trazem só o período. A reconstrução é feita por DATA de
emissão: para cada data, vale o arquivo com mais registros daquela data.

Saídas (mescladas com as existentes — datas antigas que sumirem do site são preservadas):
  ima_ptv_banana_diario.csv      data, ptvs, total_t, prata_t, nanica_t, outras_t
  ima_ptv_banana_municipios.csv  data, papel (origem|destino), municipio, toneladas

Guarda de obsolescência: falha (exit 1) se o dado mais novo tiver mais de 21 dias —
em janeiro/2027 será preciso apontar PAGINA_LISTAGEM para a página do novo ano.
"""
import csv
import datetime
import io
import re
import sys
from collections import defaultdict
from pathlib import Path

import requests

PAGINA_LISTAGEM = "https://www.ima.mg.gov.br/14-transparencia/2599-permissao-de-transito-vegetal-banana-2026"
CSV_DIARIO = Path(__file__).parent / "ima_ptv_banana_diario.csv"
CSV_MUNICIPIOS = Path(__file__).parent / "ima_ptv_banana_municipios.csv"
LIMITE_OBSOLESCENCIA_DIAS = 21
# Maior carga rodoviária plausível por registro (bitrem ~37 t). Acima disso é erro de
# digitação na fonte (kg no campo de toneladas — ex.: 24.450 "t" em 28/04/2026).
MAX_T_POR_REGISTRO = 60.0

PRATA = {"PRATA", "PRATA ANÃ", "PRATA GORUTUBA", "GORUTUBA BIOCELL", "PRATA CATARINA",
         "CATARINA", "BRS PLATINA", "PLATINA"}
CAVENDISH = {"NANICA", "CATURRA", "WILLIAMS", "GRANDE NAINE", "NANICÃO", "VALERY"}

HEADERS = {"User-Agent": "Mozilla/5.0 (coleta-precos-banana; uso interno de produtor rural)"}


def grupo_variedade(variedade):
    v = (variedade or "").strip().upper()
    if v in PRATA:
        return "prata"
    if v in CAVENDISH:
        return "nanica"
    return "outras"


def listar_urls_planilhas():
    resp = requests.get(PAGINA_LISTAGEM, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    urls = re.findall(r'href="(https?://[^"]+\.xlsx?)"', resp.text)
    # preserva ordem, remove duplicatas (cada link aparece 2x na página)
    vistos, unicos = set(), []
    for u in urls:
        if u not in vistos:
            vistos.add(u)
            unicos.append(u)
    return unicos


# O IMA já publicou 2 layouts: cabeçalho na linha 1 ("Data de Emissão da PTV",
# 9 colunas) e, do arquivo de 20-22/07/2026 em diante, linha de TÍTULO antes do
# cabeçalho ("dt_emissao", 10 colunas — entrou tp_documento_fundamento na 2ª).
# Por isso as colunas são localizadas pelo NOME, nunca pela posição.
CAMPOS_CABECALHO = {
    "data": lambda c: "emiss" in c,
    "origem": lambda c: "origem" in c and "cod" not in c,
    "destino": lambda c: "destino" in c and "cod" not in c,
    "variedade": lambda c: "variedade" in c,
    "carga": lambda c: "carga" in c,
    "unidade": lambda c: "unidade" in c,
}


def _mapear_cabecalho(linhas_iniciais):
    """Acha a linha de cabeçalho nas primeiras linhas e devolve (indice, {campo: coluna})."""
    for i, row in enumerate(linhas_iniciais):
        celulas = [str(c).strip().lower() if c is not None else "" for c in row]
        mapa = {}
        for campo, reconhece in CAMPOS_CABECALHO.items():
            for j, cel in enumerate(celulas):
                if cel and reconhece(cel):
                    mapa[campo] = j
                    break
        if len(mapa) == len(CAMPOS_CABECALHO):
            # tp_documento_fundamento (CFO=origem produtora, CFOC=consolidado/reembarque,
            # PTV=retransito) existe SÓ no layout novo — opcional, não invalida o cabeçalho
            for j, cel in enumerate(celulas):
                if "documento" in cel:
                    mapa["documento"] = j
                    break
            return i, mapa
    return None, None


def iterar_linhas_excel(conteudo, url):
    """Gera tuplas (data_iso, origem, destino, variedade, toneladas) de um xlsx/xls."""
    conv_data = None
    if url.lower().endswith(".xls"):
        import xlrd
        book = xlrd.open_workbook(file_contents=conteudo)
        sheet = book.sheet_by_index(0)
        linhas = [tuple(sheet.row_values(i)) for i in range(sheet.nrows)]

        def conv_data(v):
            # datas em .xls vêm como número serial do Excel
            return xlrd.xldate_as_datetime(v, book.datemode) if isinstance(v, float) else v
    else:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        linhas = list(ws.iter_rows(values_only=True))

    idx_cab, mapa = _mapear_cabecalho(linhas[:5])
    if mapa is None:
        # FALHA visível no log da coleta (o chamador trata) — nunca "0 registros" mudo
        raise ValueError("cabeçalho não reconhecido — o IMA mudou o layout de novo?")

    ultima_col = max(mapa.values())
    for row in linhas[idx_cab + 1:]:
        if len(row) <= ultima_col:
            continue
        data_s = row[mapa["data"]]
        origem = row[mapa["origem"]]
        unidade = row[mapa["unidade"]]
        if not data_s or not origem:
            continue
        if not (unidade and "TONELADA" in str(unidade).upper()):
            continue
        try:
            toneladas = float(row[mapa["carga"]])
        except (TypeError, ValueError):
            continue
        if toneladas <= 0 or toneladas > MAX_T_POR_REGISTRO:
            continue
        if conv_data:
            data_s = conv_data(data_s)
        data_iso = str(data_s)[:10]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", data_iso):
            continue
        documento = str(row[mapa["documento"]] or "").strip().lower() if "documento" in mapa else ""
        yield (data_iso, str(origem).strip(), str(row[mapa["destino"]] or "").strip(),
               row[mapa["variedade"]], toneladas, documento)


def coletar():
    urls = listar_urls_planilhas()
    if not urls:
        print("ERRO: nenhuma planilha encontrada na página de listagem.")
        return 1
    print(f"{len(urls)} planilhas listadas na página do IMA.")

    # (indice_arquivo, data) -> lista de registros
    por_arquivo_data = defaultdict(list)
    falhas = 0
    for i, url in enumerate(urls):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=120)
            resp.raise_for_status()
            # buffer local: o arquivo só entra no consolidado se parsear INTEIRO —
            # exceção no meio (download truncado/zip corrompido) deixaria datas
            # parciais subcontadas no CSV sem nenhum alerta
            regs_arquivo = defaultdict(list)
            for reg in iterar_linhas_excel(resp.content, url):
                regs_arquivo[reg[0]].append(reg[1:])
            for data, regs in regs_arquivo.items():
                por_arquivo_data[(i, data)].extend(regs)
            n = sum(len(r) for r in regs_arquivo.values())
            print(f"  ok: {url.rsplit('/', 3)[-3]}/{url.rsplit('/', 1)[-1]} — {n} registros")
        except Exception as e:  # noqa: BLE001 — arquivo individual não derruba a coleta
            falhas += 1
            print(f"  FALHA em {url}: {e}")
    if falhas == len(urls):
        print("ERRO: todas as planilhas falharam.")
        return 1

    # para cada data, vale o arquivo com mais registros daquela data
    melhor = {}
    for (i, data), regs in por_arquivo_data.items():
        if data not in melhor or len(regs) > len(por_arquivo_data[(melhor[data], data)]):
            melhor[data] = i

    diario = {}
    municipios = defaultdict(float)  # (data, papel, municipio, documento) -> t
    for data, i in melhor.items():
        d = {"ptvs": 0, "total": 0.0, "prata": 0.0, "nanica": 0.0, "outras": 0.0,
             "cfo_ptvs": 0, "cfo_total": 0.0, "cfo_prata": 0.0, "cfo_nanica": 0.0,
             "cfo_outras": 0.0, "tem_documento": False}
        for origem, destino, variedade, t, documento in por_arquivo_data[(i, data)]:
            grupo = grupo_variedade(variedade)
            d["ptvs"] += 1
            d["total"] += t
            d[grupo] += t
            if documento:
                d["tem_documento"] = True
            if documento == "cfo":
                d["cfo_ptvs"] += 1
                d["cfo_total"] += t
                d["cfo_" + grupo] += t
            municipios[(data, "origem", origem, documento)] += t
            if destino:
                municipios[(data, "destino", destino, documento)] += t
        diario[data] = d

    # mescla com CSVs existentes SEM regredir dado bom: a coleta nova só substitui
    # a linha de uma data se tiver PELO MENOS os mesmos registros (ptvs) — um
    # arquivo que sumiu da listagem ou falhou no download não pode apagar uma
    # versão mais completa gravada em execução anterior
    existentes_diario = {}
    if CSV_DIARIO.exists():
        with open(CSV_DIARIO, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existentes_diario[row["data"]] = row
    datas_vencedor_novo = set()
    for data, d in diario.items():
        antiga = existentes_diario.get(data)
        if antiga is None or d["ptvs"] >= int(antiga["ptvs"]):
            datas_vencedor_novo.add(data)
        else:
            print(f"  mantendo versão existente de {data}: {antiga['ptvs']} regs > {d['ptvs']} da coleta nova")

    with open(CSV_DIARIO, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["data", "ptvs", "total_t", "prata_t", "nanica_t", "outras_t",
                    "cfo_ptvs", "cfo_total_t", "cfo_prata_t", "cfo_nanica_t", "cfo_outras_t"])
        todas = sorted(set(existentes_diario) | set(diario))
        for data in todas:
            if data in datas_vencedor_novo:
                d = diario[data]
                # layout antigo não tem a coluna de documento — cfo_* fica VAZIO
                # (desconhecido), nunca 0, que seria um zero real
                cfo = ([d["cfo_ptvs"], round(d["cfo_total"], 3), round(d["cfo_prata"], 3),
                        round(d["cfo_nanica"], 3), round(d["cfo_outras"], 3)]
                       if d["tem_documento"] else ["", "", "", "", ""])
                w.writerow([data, d["ptvs"], round(d["total"], 3), round(d["prata"], 3),
                            round(d["nanica"], 3), round(d["outras"], 3), *cfo])
            else:
                e = existentes_diario[data]
                w.writerow([data, e["ptvs"], e["total_t"], e["prata_t"], e["nanica_t"], e["outras_t"],
                            e.get("cfo_ptvs") or "", e.get("cfo_total_t") or "",
                            e.get("cfo_prata_t") or "", e.get("cfo_nanica_t") or "",
                            e.get("cfo_outras_t") or ""])

    # municípios seguem o MESMO vencedor por data (diário e municípios têm que ser coerentes)
    existentes_mun = []
    if CSV_MUNICIPIOS.exists():
        with open(CSV_MUNICIPIOS, newline="", encoding="utf-8") as f:
            existentes_mun = [row for row in csv.DictReader(f)
                              if row["data"] not in datas_vencedor_novo]

    with open(CSV_MUNICIPIOS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        # "documento" por ÚLTIMO: o boletim em produção lê as 4 primeiras por posição
        w.writerow(["data", "papel", "municipio", "toneladas", "documento"])
        for e in sorted(existentes_mun, key=lambda r: (r["data"], r["papel"], r["municipio"])):
            w.writerow([e["data"], e["papel"], e["municipio"], e["toneladas"],
                        e.get("documento") or ""])
        for (data, papel, municipio, documento) in sorted(municipios):
            if data in datas_vencedor_novo:
                w.writerow([data, papel, municipio,
                            round(municipios[(data, papel, municipio, documento)], 3), documento])

    datas = todas
    print(f"\nSérie diária: {datas[0]} a {datas[-1]} ({len(datas)} dias).")

    # guarda de obsolescência
    mais_novo = datetime.date.fromisoformat(datas[-1])
    idade = (datetime.date.today() - mais_novo).days
    if idade > LIMITE_OBSOLESCENCIA_DIAS:
        print(f"ERRO: dado mais novo tem {idade} dias (limite {LIMITE_OBSOLESCENCIA_DIAS}). "
              f"Virada de ano? Atualizar PAGINA_LISTAGEM para a página do novo ano.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(coletar())
