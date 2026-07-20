#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Coleta diária de cotações de Banana Prata 1Kg por CEASA — fonte: Agrolink.

Substitui o coletor externo (Manus AI), aposentado em 20/07/2026: a série dele
ficou congelada de 14/05 a 18/07 com os mesmos 5 valores (ver quarentena/).

Grava precos_banana_prata_AAAA-MM-DD.csv na raiz do repo, no formato consumido
pelo boletim-semanal-banana (ceasa,preco_kg,data_cotacao,fonte).

Guardrails (falham o job SEM gravar CSV — a issue automática do workflow avisa):
- menos de N_PRACAS praças prioritárias com cotação fresca;
- preço fora da faixa de sanidade;
- vetor de preços idêntico aos últimos CONGELAMENTO CSVs (coletor travado —
  exatamente o defeito do coletor anterior, que passou 9 semanas despercebido).
"""
import csv
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

URL = 'https://www.agrolink.com.br/cotacoes/ceasa/frutas/banana/'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                         'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'}
RAIZ = Path(__file__).resolve().parent.parent

MAX_PAGINAS = 4      # 30 linhas/página; a prata cabe na 1ª, as demais são reserva
DIAS_FRESCO = 7      # cotação mais velha que isso não entra
N_PRACAS = 5         # o boletim exige exatamente 5 (guardrails.ts do boletim)
CONGELAMENTO = 5     # nº de CSVs anteriores idênticos que caracteriza coletor travado
PRECO_MIN, PRECO_MAX = 1.0, 15.0

# Prioridade das praças: as N_PRACAS primeiras presentes (com cotação fresca) entram.
# chave = praça como aparece no Agrolink (normalizada sem acento/caixa)
# valor = nome exibido no boletim ("Cidade (ENTIDADE)" — o vídeo corta no " (")
PRIORIDADE = [
    ('ceasaminas belo horizonte', 'Belo Horizonte (CEASAMINAS)'),
    ('ceasa-rj rio de janeiro',   'Rio de Janeiro (CEASA RJ)'),
    ('ceasa-sp campinas',         'Campinas (CEASA Campinas)'),
    ('ceagesp sao paulo',         'São Paulo (CEAGESP)'),
    ('ceasa-df brasilia',         'Brasília (CEASA DF)'),
    ('ceasa-ba salvador',         'Salvador (CEASA BA)'),
    ('ceasa-pr curitiba',         'Curitiba (CEASA PR)'),
    ('ceasa-es vitoria',          'Vitória (CEASA ES)'),
    ('ceasa-ce fortaleza',        'Fortaleza (CEASA CE)'),
    ('ceasa-pe recife',           'Recife (CEASA PE)'),
    ('ceagesp ribeirao preto',    'Ribeirão Preto (CEAGESP)'),
    ('ceasa-mt cuiaba',           'Cuiabá (CEASA MT)'),
]

# linha da tabela do Agrolink: produto, praça (span mobile), preço, data
RE_LINHA = re.compile(
    r'<tr>\s*<th scope="row">\s*([^<]+?)\s*<span[^>]*>([^<]+)</span>\s*</th>'
    r'.*?R\$\s*([\d.,]+)</td>\s*<td class="text-center">(\d{2}/\d{2}/\d{4})</td>',
    re.S)


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', sem_acento).strip().casefold()


def baixar_pagina(sessao: requests.Session, pagina: int) -> str:
    if pagina == 1:
        r = sessao.get(URL, headers=HEADERS, timeout=60)
    else:  # paginação do site é POST multipart com NumeroPagina (form frmFiltroGeral)
        r = sessao.post(URL, headers=HEADERS, timeout=60,
                        files={'NumeroPagina': (None, str(pagina))})
    r.raise_for_status()
    return r.text


def extrair_prata(html: str) -> list[tuple[str, float, date]]:
    """[(praça normalizada, preço R$/kg, data da cotação)] das linhas Banana Prata 1Kg."""
    linhas = []
    for produto, praca, preco, dt in RE_LINHA.findall(html):
        if normalizar(produto) != 'banana prata 1kg':
            continue
        # remove a UF final "(MG)" — a prioridade casa por entidade+cidade
        praca_norm = normalizar(re.sub(r'\([A-Z]{2}\)\s*$', '', praca))
        linhas.append((praca_norm, float(preco.replace('.', '').replace(',', '.')),
                       datetime.strptime(dt, '%d/%m/%Y').date()))
    return linhas


def coletar(hoje: date) -> list[dict]:
    sessao = requests.Session()
    limite = hoje - timedelta(days=DIAS_FRESCO)
    mais_recente: dict[str, tuple[float, date]] = {}
    for pagina in range(1, MAX_PAGINAS + 1):
        for praca, preco, dt in extrair_prata(baixar_pagina(sessao, pagina)):
            if praca not in mais_recente or dt > mais_recente[praca][1]:
                mais_recente[praca] = (preco, dt)
        # para cedo só quando N_PRACAS prioritárias já têm cotação FRESCA — se a
        # praça veio com data velha, uma reserva em página posterior ainda entra
        frescas = sum(1 for chave, _ in PRIORIDADE
                      if chave in mais_recente and mais_recente[chave][1] >= limite)
        if frescas >= N_PRACAS:
            break

    escolhidas = []
    for chave, nome in PRIORIDADE:
        if chave not in mais_recente:
            continue
        preco, dt = mais_recente[chave]
        if dt < limite:
            print(f'  descartada {nome}: cotação velha ({dt.isoformat()})')
            continue
        if not (PRECO_MIN <= preco <= PRECO_MAX):
            print(f'  descartada {nome}: preço fora da faixa (R$ {preco})')
            continue
        entidade = nome[nome.index('(') + 1:-1]
        escolhidas.append({'ceasa': nome, 'preco_kg': preco, 'data_cotacao': dt.isoformat(),
                           'fonte': f'Agrolink ({entidade})'})
        if len(escolhidas) == N_PRACAS:
            break
    return escolhidas


def ler_vetor(caminho: Path) -> dict[str, float]:
    with open(caminho, encoding='utf-8') as f:
        return {r['ceasa']: float(r['preco_kg']) for r in csv.DictReader(f)}


def checar_congelamento(escolhidas: list[dict], hoje: date) -> None:
    anteriores = sorted(RAIZ.glob('precos_banana_prata_????-??-??.csv'))
    anteriores = [a for a in anteriores if a.stem != f'precos_banana_prata_{hoje.isoformat()}']
    if len(anteriores) < CONGELAMENTO:
        return
    vetor_hoje = {e['ceasa']: e['preco_kg'] for e in escolhidas}
    ultimos = anteriores[-CONGELAMENTO:]
    if all(ler_vetor(a) == vetor_hoje for a in ultimos):
        sys.exit(f'GUARDRAIL: preços idênticos aos últimos {CONGELAMENTO} CSVs '
                 f'({ultimos[0].name}..{ultimos[-1].name}) — coletor travado ou fonte parada. '
                 'Verificar o Agrolink manualmente antes de liberar.')


def main() -> None:
    hoje = date.today()
    escolhidas = coletar(hoje)
    for e in escolhidas:
        print(f"  {e['ceasa']}: R$ {e['preco_kg']:.2f} ({e['data_cotacao']})")
    if len(escolhidas) < N_PRACAS:
        sys.exit(f'GUARDRAIL: só {len(escolhidas)} praças frescas (precisa de {N_PRACAS}) — '
                 'Agrolink pode ter mudado o layout ou estar sem atualizar.')
    checar_congelamento(escolhidas, hoje)

    destino = RAIZ / f'precos_banana_prata_{hoje.isoformat()}.csv'
    with open(destino, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['ceasa', 'preco_kg', 'data_cotacao', 'fonte'])
        w.writeheader()
        w.writerows(escolhidas)
    print(f'OK: {destino.name} ({len(escolhidas)} praças)')


if __name__ == '__main__':
    main()
