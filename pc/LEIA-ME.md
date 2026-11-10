# Coletas pelo PC do Edson (Rio e CEPEA)

Duas fontes só funcionam a partir do PC, e não do GitHub:

- **Rio (CEASA-RJ)** — o site recusa a conexão vinda do GitHub (os servidores dele ficam fora do Brasil).
- **CEPEA (HF Brasil)** — o coletor antigo do GitHub só passava pela proteção do site (Cloudflare) disfarçado e foi
  aposentado. O de agora (`scripts/coletar_cepea_pc.py`) é **honesto**: se identifica como robô, faz um pedido só
  quando já pode haver semana nova (o CEPEA publica às sextas) e, **se a proteção do site barrar, para e registra —
  nunca tenta de outro jeito**.

| Arquivo | O que faz |
|---|---|
| `instalar-coleta-pc.ps1` | Cria a tarefa **"Coleta pelo PC (Rio e CEPEA)"**: todo dia às 11h e 3 min depois de entrar no Windows (se o PC estava desligado às 11h). Só com o usuário logado — usa o acesso ao GitHub que o git já tem. Troca a tarefa antiga "Coleta Rio (CEASA-RJ)" e reaproveita a pasta dela. Roda uma vez na hora e mostra o registro. |
| `coleta-pc.ps1` | O que a tarefa roda: numa cópia própria do repositório (`%USERPROFILE%\coleta-pc`), coleta o Rio e o CEPEA (uma parte falhar não impede a outra) e manda ao GitHub só o que mudou (3 tentativas). Registro em `%USERPROFILE%\coleta-pc\coleta-pc.log`. |
| `desinstalar-coleta-pc.ps1` | Tira a tarefa (e a antiga, se ainda existir). |

Como o resto usa:
- **Rio** → o robô diário do GitHub (`scripts/coletar_precos_ceasas.py`, 15h) lê a cotação mais nova de
  `rio/precos_rio_ceasarj.csv`; com mais de 7 dias (PC desligado), o Rio sai e a reserva (Uberlândia) entra.
- **CEPEA** → `cepea_banana_semanal.csv` (o mesmo de sempre); o upsert do IMA (segunda e quinta) leva ao ERP
  (`mercado_precos`), e o farol "Preço de mercado (CEPEA)" do painel de confiabilidade volta a ficar em dia.

Os `.ps1` são só ASCII de propósito: o PowerShell 5.1 lê `.ps1` sem BOM como ANSI, e travessão ou acento dentro de
texto entre aspas vira aspa solta e quebra o script.

Histórico: 09/11/2026 — Rio pelo PC ("faça a coleta do Rio pelo meu PC") e, no mesmo dia, CEPEA honesto pelo PC
("a coleta CEPEA você não consegue fazer igual o Rio?").
