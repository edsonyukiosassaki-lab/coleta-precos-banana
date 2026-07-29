"""
supabase_upsert.py — envia os CSVs de mercado para a tabela mercado_precos do ERP.

Upsert do arquivo INTEIRO a cada execução (idempotente pela UNIQUE
data+fonte+produto+praca+unidade): a primeira rodada faz o backfill do
histórico e as seguintes só acrescentam o que faltar — mesmo desenho do
clima-migrate. Fonte mestre continua sendo o CSV no repo.

Requer env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
"""
import csv
import json
import os
import sys
import urllib.request

BASE = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
LOTE = 500  # linhas por request


def upsert(linhas):
    url = f"{BASE}/rest/v1/mercado_precos?on_conflict=data,fonte,produto,praca,unidade"
    for i in range(0, len(linhas), LOTE):
        corpo = json.dumps(linhas[i:i + LOTE]).encode()
        req = urllib.request.Request(url, data=corpo, method="POST", headers={
            "apikey": KEY, "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        })
        with urllib.request.urlopen(req) as r:
            if r.status not in (200, 201, 204):
                sys.exit(f"ERRO upsert HTTP {r.status}")


def ler_cepea():
    linhas = []
    with open("cepea_banana_semanal.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            linhas.append({
                "data": r["data_cotacao"], "fonte": "cepea",
                "produto": r["produto"], "praca": r["regiao"],
                "unidade": r["unidade"], "valor": float(r["preco"]),
            })
    return linhas


def ler_ima():
    linhas = []
    with open("ima_ptv_banana_diario.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for produto, col in (("total", "total_t"), ("prata", "prata_t"),
                                 ("nanica", "nanica_t"), ("outras", "outras_t")):
                linhas.append({
                    "data": r["data"], "fonte": "ima_ptv",
                    "produto": produto, "praca": "Norte de Minas — PTV",
                    "unidade": "t", "valor": float(r[col]),
                })
    return linhas


if __name__ == "__main__":
    dados = ler_cepea() + ler_ima()
    upsert(dados)
    print(f"OK: {len(dados)} linhas upsertadas em mercado_precos")
