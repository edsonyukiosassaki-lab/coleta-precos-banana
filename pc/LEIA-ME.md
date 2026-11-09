# Coleta do Rio pelo PC do Edson

O site do CEASA-RJ recusa a conexão vinda do GitHub (os servidores dele ficam fora do Brasil) e funciona do PC.
Por isso o Rio é coletado aqui, por uma tarefa do Agendador do Windows, e o resto continua no GitHub.

| Arquivo | O que faz |
|---|---|
| `instalar-coleta-rio.ps1` | Cria a tarefa **"Coleta Rio (CEASA-RJ)"**: todo dia às 11h e 3 min depois de entrar no Windows (se o PC estava desligado às 11h). Só com o usuário logado — usa o acesso ao GitHub que o git já tem. Roda uma vez na hora e mostra o registro. |
| `coleta-rio.ps1` | O que a tarefa roda: numa cópia própria do repositório (`%USERPROFILE%\coleta-rio`), baixa o boletim do CEASA-RJ, atualiza `rio/precos_rio_ceasarj.csv` e manda ao GitHub (3 tentativas). Registro em `%USERPROFILE%\coleta-rio\coleta-rio.log`. |
| `desinstalar-coleta-rio.ps1` | Tira a tarefa. |

Como o GitHub usa: o robô diário (`scripts/coletar_precos_ceasas.py`, 15h) lê a cotação mais nova de
`rio/precos_rio_ceasarj.csv`. Se ela tiver mais de 7 dias (PC desligado por muito tempo), o Rio fica de fora e a
reserva (Uberlândia) entra — sem alarme, porque o boletim mostra o nome das praças.

Os `.ps1` são só ASCII de propósito: o PowerShell 5.1 lê `.ps1` sem BOM como ANSI, e travessão ou acento dentro de
texto entre aspas vira aspa solta e quebra o script.

Criado em 09/11/2026, pedido do Edson ("faça a coleta do Rio pelo meu PC" — o Rio representa melhor Pirapora que Uberlândia).
