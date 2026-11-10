# desinstalar-coleta-pc.ps1 - tira a tarefa "Coleta pelo PC (Rio e CEPEA)" (e a antiga "Coleta Rio (CEASA-RJ)", se
# ainda existir) do Agendador do Windows.
# ARQUIVO SO COM CARACTERES ASCII DE PROPOSITO (PowerShell 5.1 le .ps1 sem BOM como ANSI).
# A pasta %USERPROFILE%\coleta-pc (copia do repositorio e registro) fica.
# Sem a tarefa: o Rio fica velho em ate 7 dias (o robo do GitHub volta a usar a reserva) e a serie do CEPEA para.
foreach ($n in @('Coleta pelo PC (Rio e CEPEA)', 'Coleta Rio (CEASA-RJ)')) {
  if (Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $n -Confirm:$false
    Write-Host ('Tarefa removida: ' + $n)
  }
}
