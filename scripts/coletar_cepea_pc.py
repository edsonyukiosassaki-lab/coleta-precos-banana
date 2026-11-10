#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Coleta HONESTA da série semanal Hortifruti/CEPEA (HF Brasil) de banana — roda no PC do Edson (09/11/2026).

O coletor antigo (coletar_cepea_banana.py, aposentado) só passava pela proteção do site (Cloudflare) DISFARÇADO:
navegador com user-agent falso, aviso de automação escondido. Este:
- se identifica como robô (mesmo user-agent do coletor de preços), sem navegador e sem disfarce;
- faz UM pedido, e só quando já pode haver semana nova (a última cotação tem 7 dias ou mais) — o CEPEA publica
  às sextas e o robots.txt pede intervalo de 10 s entre pedidos;
- se a proteção do site barrar (desafio "Um momento…", 403/503), PARA e avisa: nunca tenta de outro jeito.
Roda pelo PC (pc/coleta-pc.ps1) e não pelo GitHub, como o Rio.

Saída: acrescenta só (data, produto, região) inéditos em cepea_banana_semanal.csv — o mesmo arquivo de sempre, que o
upsert do IMA (segunda e quinta) leva ao ERP. Licença dos dados: Hortifruti/CEPEA CC BY-NC 4.0.
Códigos de saída: 0 = ok ou em dia · 2 = BARRADO pela proteção do site · 1 = outro erro.
"""
import argparse
import csv
import re
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
URL = 'https://www.hfbrasil.org.br/br/estatistica/banana.aspx'
UA = 'coleta-precos-banana/2.0 (robo de boletim semanal de precos; poucos acessos por dia)'
FONTE = 'Hortifruti/Cepea (CC BY-NC 4.0)'
CAMPOS = ['data_cotacao', 'produto', 'regiao', 'unidade', 'preco', 'fonte']
DIAS_SEMANA_NOVA = 7
MESES = {'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6, 'jul': 7, 'ago': 8, 'set': 9, 'out': 10,
         'nov': 11, 'dez': 12}
SINAIS_DE_BLOQUEIO = ('just a moment', 'um momento', '/cdn-cgi/challenge-platform', 'cf-chl')


# 09/11/2026 21h08: a 1ª leitura de verdade, do PC do Edson, voltou HTTP 403 — a proteção do site barra até o robô
# honesto. Combinado antes do teste: se barrar, PARA. Desligado, não faz nenhum pedido e sai com código 2 ("barrado"
# no registro da tarefa). Religar (True) só se o CEPEA/HF Brasil liberar o acesso por escrito.
LIGADO = False


class ErroCepea(Exception):
    pass


def bloqueado(status: int, html: str) -> bool:
    """Proteção do site respondeu no lugar da página: não é erro nosso, é um 'não' do site — respeitar."""
    t = html.lower()
    return status != 200 or any(s in t for s in SINAIS_DE_BLOQUEIO)


class _PrimeiraTabela(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.prof, self.acabou, self.linhas, self.linha, self.celula = 0, False, [], None, None

    def handle_starttag(self, tag, attrs):
        if self.acabou:
            return
        if tag == 'table':
            self.prof += 1
        elif self.prof == 1 and tag == 'tr':
            self.linha = []
        elif self.prof == 1 and tag in ('td', 'th') and self.linha is not None:
            self.celula = []

    def handle_endtag(self, tag):
        if self.acabou:
            return
        if tag == 'table' and self.prof:
            self.prof -= 1
            self.acabou = self.prof == 0
        elif self.prof == 1 and tag in ('td', 'th') and self.celula is not None:
            self.linha.append(re.sub(r'\s+', ' ', ''.join(self.celula)).strip())
            self.celula = None
        elif self.prof == 1 and tag == 'tr' and self.linha is not None:
            if self.linha:
                self.linhas.append(self.linha)
            self.linha = None

    def handle_data(self, data):
        if self.celula is not None:
            self.celula.append(data)


def ler_tabela(html: str) -> list:
    p = _PrimeiraTabela()
    p.feed(html)
    if not p.linhas:
        raise ErroCepea('tabela não encontrada na página (layout mudou?)')
    return p.linhas


def data_iso(rotulo: str, hoje: date) -> str:
    """'06/nov' → '2026-11-06' (ano corrente; rótulo de dez visto em jan é do ano passado)."""
    dia, mes_txt = rotulo.strip().split('/')
    mes = MESES[mes_txt.strip().lower()[:3]]
    ano = hoje.year - 1 if mes > hoje.month + 1 else hoje.year
    return f'{ano}-{mes:02d}-{int(dia):02d}'


def novas_cotacoes(linhas: list, existentes: list, hoje: date) -> list:
    cab = linhas[0]   # Produto | Região | Unidade | <semana 1> | ... | <semana N>
    if len(cab) < 4:
        raise ErroCepea(f'cabeçalho inesperado: {cab}')
    datas = [data_iso(x, hoje) for x in cab[3:]]
    ja_tem = {(r['data_cotacao'], r['produto'], r['regiao']) for r in existentes}
    novos = []
    for linha in linhas[1:]:
        if len(linha) < 4:
            continue
        produto, regiao, unidade = linha[0], linha[1], linha[2]
        for i, valor in enumerate(linha[3:len(datas) + 3]):
            try:
                preco = float(valor.replace(',', '.').strip())
            except ValueError:
                continue   # "- - -" = sem cotação na semana
            if (datas[i], produto, regiao) in ja_tem:
                continue
            novos.append({'data_cotacao': datas[i], 'produto': produto, 'regiao': regiao, 'unidade': unidade,
                          'preco': f'{preco:.2f}', 'fonte': FONTE})
    return novos


def em_dia(existentes: list, hoje: date) -> bool:
    if not existentes:
        return False
    ultima = max(date.fromisoformat(r['data_cotacao']) for r in existentes)
    return (hoje - ultima).days < DIAS_SEMANA_NOVA


def main() -> int:
    if not LIGADO:
        print('CEPEA: DESLIGADO desde 09/11/2026 — o site barrou o robô honesto (HTTP 403); nenhum pedido feito')
        return 2
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default=str(RAIZ / 'cepea_banana_semanal.csv'))
    arq = Path(ap.parse_args().csv)
    hoje = date.today()
    existentes = list(csv.DictReader(open(arq, encoding='utf-8'))) if arq.exists() else []
    if em_dia(existentes, hoje):
        print('CEPEA: em dia (a última semana tem menos de 7 dias) — nada a pedir ao site')
        return 0
    import requests
    try:
        r = requests.get(URL, headers={'User-Agent': UA}, timeout=60)
    except requests.RequestException as e:
        print(f'CEPEA: sem resposta do site ({e})')
        return 1
    if bloqueado(r.status_code, r.text):
        print(f'CEPEA: BARRADO pela proteção do site (HTTP {r.status_code}) — o robô honesto não passa; '
              'NÃO tentar de outro jeito. Nada gravado.')
        return 2
    try:
        novos = novas_cotacoes(ler_tabela(r.text), existentes, hoje)
    except ErroCepea as e:
        print(f'CEPEA: {e}')
        return 1
    if not novos:
        print('CEPEA: página lida, nenhuma cotação nova')
        return 0
    todos = sorted(existentes + novos, key=lambda x: (x['data_cotacao'], x['produto'], x['regiao']))
    with open(arq, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(todos)
    print(f'CEPEA: {len(novos)} cotações novas gravadas')
    for n in novos:
        if n['produto'].lower().startswith('prata anã') and 'Norte de Minas' in n['regiao']:
            print(f'  prata anã produtor Norte de Minas {n["data_cotacao"]}: R$ {n["preco"]}/kg')
    return 0


if __name__ == '__main__':
    sys.exit(main())
