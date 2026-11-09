# desinstalar-coleta-rio.ps1 - tira a tarefa "Coleta Rio (CEASA-RJ)" do Agendador do Windows.
# ARQUIVO SO COM CARACTERES ASCII DE PROPOSITO (PowerShell 5.1 le .ps1 sem BOM como ANSI).
# A pasta %USERPROFILE%\coleta-rio (copia do repositorio e registro) fica; apagar a mao se quiser.
# Sem a tarefa, o Rio fica velho em ate 7 dias e o robo do GitHub volta a usar a reserva (Uberlandia).
Unregister-ScheduledTask -TaskName 'Coleta Rio (CEASA-RJ)' -Confirm:$false
Write-Host 'Tarefa removida: Coleta Rio (CEASA-RJ)'
