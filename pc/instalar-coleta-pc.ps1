# instalar-coleta-pc.ps1 - cria (ou atualiza) a tarefa "Coleta pelo PC (Rio e CEPEA)" no Agendador do Windows.
# ARQUIVO SO COM CARACTERES ASCII DE PROPOSITO (PowerShell 5.1 le .ps1 sem BOM como ANSI).
#
# Substitui a tarefa antiga "Coleta Rio (CEASA-RJ)" (09/11/2026) e reaproveita a pasta dela: %USERPROFILE%\coleta-rio
# vira %USERPROFILE%\coleta-pc, com a copia do repositorio e o registro (nada e apagado).
# Roda todo dia as 11h e 3 min depois de entrar no Windows (se o PC estava desligado as 11h). So roda com o usuario
# logado - usa o mesmo acesso ao GitHub que o git ja tem, sem guardar senha. Desfazer: desinstalar-coleta-pc.ps1.
$ErrorActionPreference = 'Stop'
$nome = 'Coleta pelo PC (Rio e CEPEA)'
$antigo = 'Coleta Rio (CEASA-RJ)'
$base = Join-Path $env:USERPROFILE 'coleta-pc'
$velha = Join-Path $env:USERPROFILE 'coleta-rio'

if (Get-ScheduledTask -TaskName $antigo -ErrorAction SilentlyContinue) {
  Unregister-ScheduledTask -TaskName $antigo -Confirm:$false
  Write-Host ('Tarefa antiga removida: ' + $antigo)
}
if ((Test-Path $velha) -and -not (Test-Path $base)) {
  Rename-Item -Path $velha -NewName 'coleta-pc'
  if (Test-Path (Join-Path $base 'coleta-rio.log')) { Rename-Item -Path (Join-Path $base 'coleta-rio.log') -NewName 'coleta-pc.log' }
  if (Test-Path (Join-Path $base 'coleta-rio.ps1')) { Remove-Item -Path (Join-Path $base 'coleta-rio.ps1') }
  Write-Host ('Pasta reaproveitada: ' + $velha + ' -> ' + $base)
}
New-Item -ItemType Directory -Force -Path $base | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot 'coleta-pc.ps1') (Join-Path $base 'coleta-pc.ps1')

$acao = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f (Join-Path $base 'coleta-pc.ps1'))
$diario = New-ScheduledTaskTrigger -Daily -At '11:00'
$entrada = New-ScheduledTaskTrigger -AtLogOn -User ('{0}\{1}' -f $env:USERDOMAIN, $env:USERNAME)
$entrada.Delay = 'PT3M'
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName $nome -Action $acao -Trigger @($diario, $entrada) -Settings $config -Force `
  -Description 'Rio (CEASA-RJ) todo dia e CEPEA (HF Brasil, robo honesto) quando ha semana nova; manda ao GitHub (coleta-precos-banana). Criada em 09/11/2026.' | Out-Null
Write-Host ('Tarefa criada: ' + $nome + '. Rodando uma vez agora para conferir...')

Start-ScheduledTask -TaskName $nome
$limite = (Get-Date).AddMinutes(4)
do { Start-Sleep -Seconds 5 } while ((Get-ScheduledTask -TaskName $nome).State -eq 'Running' -and (Get-Date) -lt $limite)
Write-Host '--- ultimas linhas do registro ---'
Get-Content (Join-Path $base 'coleta-pc.log') -Tail 12 -Encoding UTF8
