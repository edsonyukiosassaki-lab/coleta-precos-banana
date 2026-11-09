# Recomposições de mês — só fontes oficiais

Arquivos `precos_banana_prata_AAAA-MM_oficial.csv` (mesmo formato dos CSVs diários: `ceasa,preco_kg,data_cotacao,fonte`)
com um mês INTEIRO montado depois, a partir de fontes oficiais que guardam histórico. Não substituem nem alteram os
CSVs diários da raiz (o histórico nunca é apagado).

Gerados com `python scripts/coletar_precos_ceasas.py --recompor AAAA-MM` (rodar do PC no Brasil — o site do
CEASA-RJ recusa conexão vinda do GitHub). Fontes:

- **BH**: boletim diário da CEASAMINAS, linha BANANA PRATA CLIM EXT, preço comum (a mesma série do robô diário);
- **Rio**: boletim diário do CEASA-RJ (PDF), BANANA PRATA Extra, modal ÷ 20 kg;
- **Curitiba**: coleta diária do CEASA-PR (PDF), BANANA PRATA, mais comum ÷ 20 kg.

São Paulo e Vitória não entram: a página da CEASAMINAS que traz essas praças só mostra o preço do dia.

| Arquivo | Por quê | Quando |
|---|---|---|
| `precos_banana_prata_2026-10_oficial.csv` | A coleta do Agrolink parou em 20/10/2026 e o Agrolink proíbe robôs e reprodução nos termos de uso. Outubro inteiro só com oficiais: BH 13 dias, Rio 19, Curitiba 21 (53 cotações, 01/10 a 30/10) | 09/11/2026, pedido do Edson para o vídeo da porteira de outubro |

Quem lê: a Fábrica (`boletim-semanal-banana/src/fabrica/fontes.ts`, vídeo "Quanto do preço da CEASA chega na minha
porteira?"). O boletim semanal NÃO lê esta pasta.
