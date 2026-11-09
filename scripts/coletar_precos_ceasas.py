#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Coleta diária de cotações de Banana Prata por CEASA — FONTES OFICIAIS (substitui o Agrolink em 09/11/2026).

Por que trocou: o Agrolink refez o site (~24/10/2026) e o coletor antigo parou (400 todo dia); e os termos de
uso do Agrolink (cl. 3.4) proíbem robôs. O coletor antigo ainda se identificava como navegador Chrome. Este se
identifica honestamente e faz poucos acessos por dia (2 páginas + 2 listas + 2 PDFs).

Fontes (todas de órgão público, sem formulário, sem login):
- CEASAMINAS "Preço mais comum nos Estados" (HTML): Belo Horizonte, São Paulo, Espírito Santo — já em R$/kg,
  uma data por coluna. A coluna do Rio vem com data 01/01/1900 (sem dado) e cai na regra de frescor.
- CEASAMINAS "Preço mais comum MG" (HTML): Uberlândia e Juiz de Fora — RESERVAS, só entram se faltar praça.
- CEASA-RJ boletim diário (PDF, dias úteis): BANANA PRATA Extra, caixa de 20 kg, preço MODAL ÷ 20.
- CEASA-PR Curitiba, coleta diária (PDF, dias úteis): BANANA PRATA, caixa de 20 kg, MAIS COMUM do dia ÷ 20.
A CEASAMINAS NÃO guarda histórico aberto (as consultas por data são formulários) — por isso o modo de teste
(--de/--ate) só refaz Rio e Curitiba.

Saída: precos_banana_prata_AAAA-MM-DD.csv (ceasa,preco_kg,data_cotacao,fonte), o MESMO formato e os MESMOS
nomes de praça que o boletim-semanal-banana já lê.

Guardrails (falham o job SEM gravar CSV — a issue automática do workflow avisa):
- menos de N_PRACAS praças com cotação fresca;
- preço fora da faixa de sanidade;
- (preço, data) idênticos aos últimos CONGELAMENTO CSVs = nenhuma fonte andou = fonte parada.
  Preço igual com data andando é mercado estável, não alarme (Curitiba ficou em R$ 4,00 por semanas).

Uso:
  python scripts/coletar_precos_ceasas.py                      # coleta de hoje e grava o CSV
  python scripts/coletar_precos_ceasas.py --seco               # coleta de hoje, só imprime
  python scripts/coletar_precos_ceasas.py --de 2026-10-19 --ate 2026-11-09   # teste: Rio e Curitiba dia a dia
"""
import argparse
import csv
import io
import re
import sys
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from calendar import monthrange
from urllib.parse import quote, unquote, urljoin

RAIZ = Path(__file__).resolve().parent.parent
UA = 'coleta-precos-banana/2.0 (robo de boletim semanal de precos; poucos acessos por dia)'

DIAS_FRESCO = 7      # cotação mais velha que isso não entra (mesma régua do boletim)
N_PRACAS = 5         # o boletim exige exatamente 5 (guardrails.ts do boletim)
CONGELAMENTO = 5     # nº de CSVs anteriores idênticos em (preço, data) que caracteriza fonte parada
PRECO_MIN, PRECO_MAX = 1.0, 15.0
CAIXA_KG = 20        # Rio e Curitiba cotam a prata em caixa de 20 kg; outro peso = layout mudou → para

# Ordem de preferência: as N_PRACAS primeiras com cotação fresca entram. Nomes = os que o boletim usa
# (ele casa praça pelo nome na variação semanal) — NÃO mudar sem mudar o boletim junto.
PRIORIDADE = [
    'Belo Horizonte (CEASAMINAS)',
    'São Paulo (CEAGESP)',
    'Rio de Janeiro (CEASA RJ)',
    'Curitiba (CEASA PR)',
    'Vitória (CEASA ES)',
    'Uberlândia (CEASAMINAS)',     # reserva
    'Juiz de Fora (CEASAMINAS)',   # reserva
]

URL_CM_ESTADOS = 'https://minas1.ceasa.mg.gov.br/ceasainternet/cst_precosmaiscomumEstados/cst_precosmaiscomumEstados.php'
URL_CM_MG = 'https://minas1.ceasa.mg.gov.br/ceasainternet/cst_precosmaiscomumMG/cst_precosmaiscomumMG.php'
# índice anual do boletim do CEASA-RJ (uma página por ano, com um link por mês). Ano sem índice aqui = o Rio
# falha com aviso claro e a reserva cobre — atualizar em janeiro.
RJ_INDICE_ANO = {2026: 'https://www.rj.gov.br/ceasa/node/600'}
URL_PR_ANO = 'https://www.ceasa.pr.gov.br/Pagina/Cotacao-Diaria-de-Precos-{ano}'
MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro',
         'Outubro', 'Novembro', 'Dezembro']


class ErroFonte(Exception):
    """A fonte respondeu, mas não do jeito esperado (layout, unidade, data) — essa praça fica de fora."""


class ErroGuardrail(Exception):
    """Dados insuficientes ou suspeitos — o CSV do dia NÃO é gravado."""


def cotacao(ceasa: str, preco: float, dia: date, fonte: str) -> dict:
    return {'ceasa': ceasa, 'preco_kg': round(preco, 2), 'data_cotacao': dia, 'fonte': fonte}


def num_br(s: str) -> float:
    """'3,75' / '1.234,50' / '3.75' → float."""
    s = s.strip()
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    return float(s)


def data_br(s: str) -> date:
    return datetime.strptime(s, '%d/%m/%Y').date()


# ── CEASAMINAS (HTML do Scriptcase) ─────────────────────────────────────────────────────────────────────
def _linha_prata(html: str) -> str:
    m = re.search(r'id="id_sc_field_produto_(\d+)">\s*BANANA-PRATA\s*<', html)
    if not m:
        raise ErroFonte('CEASAMINAS: linha BANANA-PRATA não encontrada (layout mudou?)')
    n = m.group(1)
    un = re.search(rf'id="id_sc_field_unidade_{n}">\s*([^<]*?)\s*<', html)
    if not un or un.group(1).upper() != 'KG':
        raise ErroFonte(f'CEASAMINAS: unidade da prata não é KG ({un.group(1) if un else "?"})')
    return n


def _valor(html: str, campo: str, n: str):
    m = re.search(rf'id="id_sc_field_{campo}_{n}">\s*([^<]*?)\s*<', html)
    if not m or not m.group(1):
        return None
    try:
        v = num_br(m.group(1))
    except ValueError:
        return None
    return v if v > 0 else None


def _datas_cabecalho(html: str) -> dict:
    """{'Grande BH': date(...), 'São Paulo': ...} — o cabeçalho de cada coluna traz 'X - cotação de: dd/mm/aaaa'."""
    return {rotulo.strip(): data_br(d) for rotulo, d in
            re.findall(r'>\s*([^<>]+?)\s*-\s*cota\w+o de:\s*(\d{2}/\d{2}/\d{4})', html)}


def ler_ceasaminas_estados(html: str) -> list:
    n = _linha_prata(html)
    datas = _datas_cabecalho(html)
    colunas = [('mg', 'Grande BH', 'Belo Horizonte (CEASAMINAS)'),
               ('sp', 'São Paulo', 'São Paulo (CEAGESP)'),
               ('rj', 'Rio de Janeiro', 'Rio de Janeiro (CEASA RJ)'),
               ('es', 'Espírito Santo', 'Vitória (CEASA ES)')]
    saida = []
    for campo, rotulo, nome in colunas:
        v, d = _valor(html, campo, n), datas.get(rotulo)
        if v is not None and d is not None:
            saida.append(cotacao(nome, v, d, f'CEASAMINAS ({rotulo})'))
    if not saida:
        raise ErroFonte('CEASAMINAS estados: nenhuma coluna com preço e data')
    return saida


def ler_ceasaminas_mg(html: str) -> list:
    n = _linha_prata(html)
    datas = _datas_cabecalho(html)
    colunas = [('precosub', 'Uberlândia', 'Uberlândia (CEASAMINAS)'),
               ('precosjf', 'Juiz de Fora', 'Juiz de Fora (CEASAMINAS)')]
    saida = []
    for campo, rotulo, nome in colunas:
        v, d = _valor(html, campo, n), datas.get(rotulo)
        if v is not None and d is not None:
            saida.append(cotacao(nome, v, d, f'CEASAMINAS ({rotulo})'))
    return saida


# ── boletim diário da CEASAMINAS (histórico por data) ───────────────────────────────────────────────────
# Achado em 09/11/2026: o "Boletim Diário de Preços Completo" abre por GET simples, sem sessão nem formulário
# (mercod 214 = Grande BH; data em MÊS/DIA/ANO). Guarda o histórico desde 11/2021. A linha usada é a BANANA PRATA
# CLIM EXT, preço COMUM — a mesma série do Agrolink (3,25 em outubro) e da página "mais comum" (3,75 em 09/11).
URL_CM_BOLETIM = 'https://minas1.ceasa.mg.gov.br/detec/boletim_completo/boletim_completo.php'
MERCOD_GRANDE_BH = 214


def url_boletim_ceasaminas(mercod: int, dia: date) -> str:
    parms = f'mercod?#?{mercod}?@?data?#?{dia.strftime("%m/%d/%Y")}?@?numero?#?1?@?'
    return f'{URL_CM_BOLETIM}?nmgp_parms={quote(parms, safe="")}'


def ler_ceasaminas_boletim(html: str) -> dict:
    d = re.search(r'Data:\s*(\d{2}/\d{2}/\d{4})', html)
    if not d:
        raise ErroFonte('boletim CEASAMINAS: sem data (dia sem boletim ou página de erro)')
    m = re.search(r'id="id_sc_field_prdnom_(\d+)">\s*BANANA PRATA CLIM EXT\s*<', html)
    if not m:
        raise ErroFonte('boletim CEASAMINAS: linha BANANA PRATA CLIM EXT não encontrada')
    n = m.group(1)
    campo = lambda nome: re.search(rf'id="id_sc_field_{nome}_{n}">\s*([^<]*?)\s*<', html)
    un, comum = campo('embdesresu'), campo('pboprccomum')
    if not un or un.group(1).strip().upper() != 'KG':
        raise ErroFonte(f'boletim CEASAMINAS: prata extra não está em KG ({un.group(1) if un else "?"})')
    if not comum or not comum.group(1):
        raise ErroFonte('boletim CEASAMINAS: prata extra sem preço comum')
    return cotacao('Belo Horizonte (CEASAMINAS)', num_br(comum.group(1)), data_br(d.group(1)),
                   'CEASAMINAS (boletim diário - Grande BH)')


# ── PDFs (Rio e Curitiba) ───────────────────────────────────────────────────────────────────────────────
def texto_pdf(conteudo: bytes) -> str:
    from pypdf import PdfReader  # import aqui: o resto do módulo (e os testes de HTML) não depende dele
    return '\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(conteudo)).pages)


DINHEIRO = r'\d{1,3}(?:\.\d{3})*,\d{2}'


def ler_rj(texto: str) -> dict:
    d = re.search(r'Dia Semana:\s*\S+\s+(\d{2}/\d{2}/\d{4})', texto)
    if not d:
        raise ErroFonte('CEASA-RJ: data do boletim não encontrada')
    m = re.search(rf'^BANANA PRATA\b[^\n]*?\bCx\s*(\d+)\s*kg\b\s+(?:-?[\d.]+,\d+%|S/C)\s+({DINHEIRO})\s+({DINHEIRO})\s+({DINHEIRO})',
                  texto, re.M)
    if not m:
        raise ErroFonte('CEASA-RJ: linha da BANANA PRATA com mín/modal/máx não encontrada (sem cotação no dia ou layout mudou)')
    if int(m.group(1)) != CAIXA_KG:
        raise ErroFonte(f'CEASA-RJ: prata cotada em caixa de {m.group(1)} kg (esperado {CAIXA_KG}) — conferir antes de dividir')
    modal = num_br(m.group(3))
    # fonte SEM vírgula: o boletim lê o CSV com split(',') simples (parsePrecosCsv)
    return cotacao('Rio de Janeiro (CEASA RJ)', modal / CAIXA_KG, data_br(d.group(1)), 'CEASA-RJ (boletim diário - modal)')


def ler_pr_curitiba(texto: str) -> dict:
    if 'CEASA - CURITIBA' not in texto:
        raise ErroFonte('CEASA-PR: o PDF não é do mercado de Curitiba')
    d = re.search(r'Data da Coleta:\s*(\d{2}/\d{2}/\d{4})', texto)
    if not d:
        raise ErroFonte('CEASA-PR: data da coleta não encontrada')
    no_bloco = False
    for linha in texto.splitlines():
        if linha.strip() == 'BANANA':
            no_bloco = True
            continue
        if no_bloco and not linha[:1].isspace():
            no_bloco = False   # o bloco de um produto são as linhas recuadas logo abaixo do nome dele
        if no_bloco:
            m = re.match(r'^\s+PRATA\s+cx\s*(\d+)\s*kg\b(.*)$', linha, re.I)
            if m:
                if int(m.group(1)) != CAIXA_KG:
                    raise ErroFonte(f'CEASA-PR: prata cotada em caixa de {m.group(1)} kg (esperado {CAIXA_KG})')
                precos = re.findall(DINHEIRO, m.group(2))   # mín, MAIS COMUM do dia, máx, mais comum do dia anterior
                if len(precos) < 2:
                    raise ErroFonte('CEASA-PR: linha da prata sem o preço mais comum')
                return cotacao('Curitiba (CEASA PR)', num_br(precos[1]) / CAIXA_KG, data_br(d.group(1)),
                               'CEASA-PR (Curitiba - mais comum)')
    raise ErroFonte('CEASA-PR: BANANA PRATA não encontrada no bloco BANANA')


def links_rj(html: str) -> dict:
    links = {}
    for href in re.findall(r'href="([^"]+\.pdf)"', html):
        m = re.search(r'(\d{2}) (\d{2}) (\d{4})(?:_\d+)?\.pdf$', unquote(href))
        if m:
            dia = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            links.setdefault(dia, urljoin('https://www.rj.gov.br/', href))
    return links


def links_pr(html: str) -> dict:
    links = {}
    for href, dd, mm, aaaa in re.findall(
            r'href="([^"]*/documento/\d{4}-\d{2}/cotacaopdf(\d{2})(\d{2})(\d{4})(?:_\d+)?\.pdf)"', html):
        links.setdefault(date(int(aaaa), int(mm), int(dd)), urljoin('https://www.ceasa.pr.gov.br/', href))
    return links


def links_rj_meses(html_indice: str) -> dict:
    """{número do mês: url da página do mês} a partir do índice anual do CEASA-RJ."""
    saida = {}
    for href, nome in re.findall(r'href="([^"]*node/\d+)"[^>]*>\s*<strong>\s*([A-Za-zç]+)', html_indice):
        if nome in MESES:
            saida[MESES.index(nome) + 1] = urljoin('https://www.rj.gov.br/', href)
    return saida


# ── escolha das 5 praças e travas ───────────────────────────────────────────────────────────────────────
def escolher(cots: list, hoje: date) -> list:
    mais_nova = {}
    for x in cots:                      # mesma praça por duas fontes: vale a cotação mais nova (empate: a 1ª lida)
        atual = mais_nova.get(x['ceasa'])
        if atual is None or x['data_cotacao'] > atual['data_cotacao']:
            mais_nova[x['ceasa']] = x
    escolhidas = []
    for nome in PRIORIDADE:
        x = mais_nova.get(nome)
        if x is None:
            continue
        idade = (hoje - x['data_cotacao']).days
        if idade < 0 or idade > DIAS_FRESCO:
            print(f'  descartada {nome}: cotação de {x["data_cotacao"].isoformat()} fora da janela de {DIAS_FRESCO} dias')
            continue
        if not (PRECO_MIN <= x['preco_kg'] <= PRECO_MAX):
            print(f'  descartada {nome}: preço fora da faixa (R$ {x["preco_kg"]})')
            continue
        escolhidas.append(x)
        if len(escolhidas) == N_PRACAS:
            break
    return escolhidas


def _assinatura(vetor) -> set:
    return {(x['ceasa'], round(float(x['preco_kg']), 2), str(x['data_cotacao'])) for x in vetor}


def checar_congelamento(escolhidas: list, anteriores: list) -> None:
    if len(anteriores) < CONGELAMENTO:
        return
    hoje = _assinatura(escolhidas)
    if all(_assinatura(a) == hoje for a in anteriores[-CONGELAMENTO:]):
        raise ErroGuardrail(f'preços E datas idênticos aos últimos {CONGELAMENTO} CSVs — nenhuma fonte andou '
                            '(fonte parada?). Verificar as páginas manualmente antes de liberar.')


def linhas_csv(escolhidas: list) -> list:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(['ceasa', 'preco_kg', 'data_cotacao', 'fonte'])
    for x in escolhidas:
        w.writerow([x['ceasa'], x['preco_kg'], x['data_cotacao'].isoformat(), x['fonte']])
    return buf.getvalue().splitlines()


# ── rede ────────────────────────────────────────────────────────────────────────────────────────────────
class Rede:
    """GET com identificação honesta, 3 tentativas com espera crescente e cache por execução."""

    def __init__(self):
        import requests
        self.sessao = requests.Session()
        self.sessao.headers['User-Agent'] = UA
        self.cache = {}

    def get(self, url: str) -> bytes:
        if url in self.cache:
            return self.cache[url]
        erro = None
        for tentativa in range(3):
            try:
                r = self.sessao.get(url, timeout=60)
                r.raise_for_status()
                self.cache[url] = r.content
                return r.content
            except Exception as e:  # rede instável: tenta de novo (5 s, 15 s)
                erro = e
                if tentativa < 2:
                    time.sleep(5 + 10 * tentativa)
        raise ErroFonte(f'sem resposta de {url}: {erro}')


def _pdf_do_dia(rede: Rede, links: dict, alvo: date, ler) -> dict:
    """PDF mais recente com data <= alvo dentro da janela de frescor; confere que a data do PDF bate com a do link."""
    candidatos = sorted(d for d in links if d <= alvo and (alvo - d).days <= DIAS_FRESCO)
    if not candidatos:
        raise ErroFonte(f'nenhum PDF entre {(alvo - timedelta(days=DIAS_FRESCO)).isoformat()} e {alvo.isoformat()}')
    dia = candidatos[-1]
    x = ler(texto_pdf(rede.get(links[dia])))
    if x['data_cotacao'] != dia:
        raise ErroFonte(f'o PDF de {dia.isoformat()} traz data {x["data_cotacao"].isoformat()} por dentro')
    return x


def coletar_rj(rede: Rede, alvo: date) -> dict:
    links = {}
    for ano, mes in {(alvo.year, alvo.month), ((alvo - timedelta(days=DIAS_FRESCO)).year,
                                               (alvo - timedelta(days=DIAS_FRESCO)).month)}:
        if ano not in RJ_INDICE_ANO:
            raise ErroFonte(f'CEASA-RJ: índice do ano {ano} não configurado (RJ_INDICE_ANO) — atualizar o endereço')
        meses = links_rj_meses(rede.get(RJ_INDICE_ANO[ano]).decode('utf-8', 'replace'))
        if mes in meses:
            links.update(links_rj(rede.get(meses[mes]).decode('utf-8', 'replace')))
    return _pdf_do_dia(rede, links, alvo, ler_rj)


def coletar_pr(rede: Rede, alvo: date) -> dict:
    links = {}
    for ano in {alvo.year, (alvo - timedelta(days=DIAS_FRESCO)).year}:
        links.update(links_pr(rede.get(URL_PR_ANO.format(ano=ano)).decode('utf-8', 'replace')))
    return _pdf_do_dia(rede, links, alvo, ler_pr_curitiba)


def recompor_mes(rede: Rede, mes: str, log=print) -> list:
    """Mês inteiro só com fontes OFICIAIS que guardam histórico (09/11/2026, para o vídeo da porteira de outubro):
    BH pelo boletim diário da CEASAMINAS (dia útil a dia útil), Rio e Curitiba pelos PDFs de cada dia, uma vez cada.
    São Paulo e Vitória ficam de fora — a página "mais comum" da CEASAMINAS só mostra o preço do dia."""
    ano, m = map(int, mes.split('-'))
    cots = []
    for dia in (date(ano, m, d) for d in range(1, monthrange(ano, m)[1] + 1)):
        if dia.weekday() >= 5:
            continue
        try:
            x = ler_ceasaminas_boletim(rede.get(url_boletim_ceasaminas(MERCOD_GRANDE_BH, dia)).decode('utf-8', 'replace'))
            if x['data_cotacao'] != dia:
                raise ErroFonte(f'pedido {dia.isoformat()}, veio {x["data_cotacao"].isoformat()}')
            cots.append(x)
            log(f'  BH {dia.isoformat()}: R$ {x["preco_kg"]:.2f}')
        except ErroFonte as e:
            log(f'  BH {dia.isoformat()}: sem cotação ({e})')
        time.sleep(1)   # boletim é gerado na hora pelo banco deles — sem pressa

    def links_rj_mes() -> dict:
        if ano not in RJ_INDICE_ANO:
            raise ErroFonte(f'índice do ano {ano} não configurado')
        meses = links_rj_meses(rede.get(RJ_INDICE_ANO[ano]).decode('utf-8', 'replace'))
        if m not in meses:
            raise ErroFonte(f'mês {m:02d}/{ano} não está no índice')
        return links_rj(rede.get(meses[m]).decode('utf-8', 'replace'))

    def links_pr_mes() -> dict:
        return links_pr(rede.get(URL_PR_ANO.format(ano=ano)).decode('utf-8', 'replace'))

    for nome, obter, ler in [('Rio', links_rj_mes, ler_rj), ('Curitiba', links_pr_mes, ler_pr_curitiba)]:
        try:
            links = {d: u for d, u in obter().items() if (d.year, d.month) == (ano, m)}
        except ErroFonte as e:
            log(f'  {nome}: FONTE FALHOU ({e})')
            continue
        for dia in sorted(links):
            try:
                x = ler(texto_pdf(rede.get(links[dia])))
                if x['data_cotacao'] != dia:
                    raise ErroFonte(f'PDF de {dia.isoformat()} traz {x["data_cotacao"].isoformat()} por dentro')
                cots.append(x)
                log(f'  {nome} {dia.isoformat()}: R$ {x["preco_kg"]:.2f}')
            except ErroFonte as e:
                log(f'  {nome} {dia.isoformat()}: fora ({e})')
    return sorted(cots, key=lambda x: (x['data_cotacao'], PRIORIDADE.index(x['ceasa'])))


def coletar_tudo(rede: Rede, hoje: date) -> list:
    cots = []
    # ordem importa no empate de data: o Rio do PDF do CEASA-RJ vem antes do Rio da CEASAMINAS
    for nome, fazer in [('CEASA-RJ', lambda: [coletar_rj(rede, hoje)]),
                        ('CEASA-PR', lambda: [coletar_pr(rede, hoje)]),
                        ('CEASAMINAS estados', lambda: ler_ceasaminas_estados(rede.get(URL_CM_ESTADOS).decode('utf-8', 'replace'))),
                        ('CEASAMINAS MG', lambda: ler_ceasaminas_mg(rede.get(URL_CM_MG).decode('utf-8', 'replace')))]:
        try:
            lidas = fazer()
            cots.extend(lidas)
            for x in lidas:
                print(f'  {nome}: {x["ceasa"]} R$ {x["preco_kg"]:.2f} ({x["data_cotacao"].isoformat()})')
        except ErroFonte as e:
            print(f'  FONTE FALHOU — {nome}: {e}')
    return cots


def ler_csv(caminho: Path) -> list:
    with open(caminho, encoding='utf-8') as f:
        return list(csv.DictReader(f))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--seco', action='store_true', help='coleta de hoje sem gravar o CSV')
    ap.add_argument('--de', type=date.fromisoformat, help='modo teste: primeiro dia (Rio e Curitiba)')
    ap.add_argument('--ate', type=date.fromisoformat, help='modo teste: último dia')
    ap.add_argument('--recompor', help='AAAA-MM: mês inteiro só com fontes oficiais; CSV na saída padrão, registro no stderr')
    args = ap.parse_args()
    execucao = uuid.uuid4().hex[:8]
    rede = Rede()

    if args.recompor:
        log = lambda s: print(s, file=sys.stderr)
        log(f'[{execucao}] RECOMPOSIÇÃO de {args.recompor} (só fontes oficiais) — início {datetime.now().isoformat(timespec="seconds")}')
        cots = recompor_mes(rede, args.recompor, log)
        print('\n'.join(linhas_csv(cots)))
        log(f'[{execucao}] fim: {len(cots)} cotações')
        return

    print(f'[{execucao}] início {datetime.now().isoformat(timespec="seconds")}')

    if args.de:
        ate = args.ate or args.de
        print(f'[{execucao}] MODO TESTE {args.de} a {ate} — só Rio e Curitiba (a CEASAMINAS não guarda histórico); nada é gravado')
        dia = args.de
        while dia <= ate:
            linha = [dia.strftime('%a %d/%m')]
            for nome, fazer in [('Rio', coletar_rj), ('Curitiba', coletar_pr)]:
                try:
                    x = fazer(rede, dia)
                    linha.append(f'{nome} R$ {x["preco_kg"]:.2f} (PDF de {x["data_cotacao"].strftime("%d/%m")})')
                except ErroFonte as e:
                    linha.append(f'{nome} — {e}')
            print('  ' + ' | '.join(linha))
            dia += timedelta(days=1)
        print(f'[{execucao}] fim do teste')
        return

    hoje = date.today()
    escolhidas = escolher(coletar_tudo(rede, hoje), hoje)
    for x in escolhidas:
        print(f'  ESCOLHIDA {x["ceasa"]}: R$ {x["preco_kg"]:.2f} ({x["data_cotacao"].isoformat()}) — {x["fonte"]}')
    try:
        if len(escolhidas) < N_PRACAS:
            raise ErroGuardrail(f'só {len(escolhidas)} praças frescas (precisa de {N_PRACAS}) — uma fonte pode ter '
                                'mudado o layout ou parado de publicar.')
        anteriores = [ler_csv(a) for a in sorted(RAIZ.glob('precos_banana_prata_????-??-??.csv'))
                      if a.stem != f'precos_banana_prata_{hoje.isoformat()}']
        checar_congelamento(escolhidas, anteriores)
    except ErroGuardrail as e:
        print(f'[{execucao}] fim: FALHOU')
        sys.exit(f'GUARDRAIL: {e}')

    if args.seco:
        print(f'[{execucao}] fim: OK (seco — nada gravado)')
        return
    destino = RAIZ / f'precos_banana_prata_{hoje.isoformat()}.csv'
    destino.write_text('\n'.join(linhas_csv(escolhidas)) + '\n', encoding='utf-8')
    print(f'[{execucao}] fim: OK — {destino.name} ({len(escolhidas)} praças)')


if __name__ == '__main__':
    main()
