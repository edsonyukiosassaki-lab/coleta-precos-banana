"""
coletar_cepea_banana.py — série semanal Hortifruti/CEPEA (HF Brasil) de banana.

Extrai a tabela pública de https://www.hfbrasil.org.br/br/estatistica/banana.aspx
(todas as linhas: prata anã, prata litoral e nanica; produtor e atacado) e acumula
em cepea_banana_semanal.csv, adicionando apenas (data, produto, região) inéditos.

O site bloqueia requisições simples (403), por isso usa Playwright headless.
Licença dos dados: HORTIFRÚTI/CEPEA CC BY-NC 4.0 — uso não comercial com atribuição.
"""

import csv
import os
import sys
from datetime import date

from playwright.sync_api import sync_playwright

URL = "https://www.hfbrasil.org.br/br/estatistica/banana.aspx"
CSV_PATH = "cepea_banana_semanal.csv"
FONTE = "Hortifruti/Cepea (CC BY-NC 4.0)"
MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
         "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}


def data_iso(rotulo, hoje):
    """'10/jul' → '2026-07-10' (ano corrente; vira o ano na fronteira dez/jan)."""
    dia, mes_txt = rotulo.strip().split("/")
    mes = MESES[mes_txt.strip().lower()[:3]]
    ano = hoje.year
    if mes > hoje.month + 1:  # rótulo de dez visto em jan = ano passado
        ano -= 1
    return f"{ano}-{mes:02d}-{int(dia):02d}"


def extrair_tabela():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("table tr", timeout=30000)
        linhas = page.eval_on_selector_all(
            "table:first-of-type tr",
            "trs => trs.map(tr => [...tr.querySelectorAll('th,td')].map(c => c.textContent.trim()))",
        )
        browser.close()
    return linhas


def main():
    hoje = date.today()
    linhas = extrair_tabela()
    if not linhas or len(linhas[0]) < 4:
        raise SystemExit("Tabela não encontrada — layout do site mudou ou bloqueio de bot.")

    cab = linhas[0]  # Produto | Região | Unidade | <data1> | ... | <dataN>
    datas = [data_iso(c, hoje) for c in cab[3:]]

    ja_tem = set()
    existentes = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            existentes = list(csv.DictReader(f))
        ja_tem = {(r["data_cotacao"], r["produto"], r["regiao"]) for r in existentes}

    novos = []
    for linha in linhas[1:]:
        if len(linha) < 4:
            continue
        produto, regiao, unidade = linha[0], linha[1], linha[2]
        for i, valor in enumerate(linha[3:]):
            preco = valor.replace(",", ".").strip()
            try:
                preco_f = float(preco)
            except ValueError:
                continue  # "- - -" = sem cotação na semana
            chave = (datas[i], produto, regiao)
            if chave in ja_tem:
                continue
            novos.append({
                "data_cotacao": datas[i], "produto": produto, "regiao": regiao,
                "unidade": unidade, "preco": f"{preco_f:.2f}", "fonte": FONTE,
            })

    if not novos:
        print("Nenhuma cotação nova — CSV já está em dia.")
        return

    todos = existentes + novos
    todos.sort(key=lambda r: (r["data_cotacao"], r["produto"], r["regiao"]))
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["data_cotacao", "produto", "regiao",
                                          "unidade", "preco", "fonte"])
        w.writeheader()
        w.writerows(todos)

    print(f"{len(novos)} cotações novas gravadas em {CSV_PATH}.")
    destaque = [n for n in novos if n["produto"].lower().startswith("prata anã")
                and "Norte de Minas" in n["regiao"]]
    for n in destaque:
        print(f"  ★ Prata anã produtor Norte de Minas {n['data_cotacao']}: R$ {n['preco']}/kg")


if __name__ == "__main__":
    sys.exit(main())
