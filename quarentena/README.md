# Quarentena — série de preços inválida (14/05 a 18/07/2026)

Todos os CSVs desta pasta foram gerados pelo coletor externo **Manus AI** e trazem
**os mesmos 5 valores em todas as datas** (SP 4,80 · BH 4,50 · Campinas 4,50 ·
RJ 4,00 · DF 5,79): o coletor congelou na primeira coleta e repetiu o snapshot
por 9 semanas. Conferido contra o Agrolink em 20/07/2026 — o mercado real estava
bem diferente (ex.: BH R$ 3,50, RJ R$ 3,00). O R$ 5,79 atribuído a "Brasília"
era, no Agrolink real, a cotação de Cuiabá.

**Não usar estes dados para nada** — nem gráfico, nem variação semanal.
Foram movidos para cá (em vez de apagados) só como registro do incidente.

A série válida recomeça em `../precos_banana_prata_2026-07-20.csv`, gerada pelo
coletor próprio `scripts/coletar_precos_agrolink.py` (workflow `collect_prices.yml`),
com guardrail anti-congelamento.
