# instalar-coleta-rio.ps1 - cria (ou atualiza) a tarefa "Coleta Rio (CEASA-RJ)" no Agendador do Windows deste PC.
# ARQUIVO SO COM CARACTERES ASCII DE PROPOSITO (PowerShell 5.1 le .ps1 sem BOM como ANSI).
#
# Roda todo dia as 11h e tambem 3 min depois de entrar no Windows (se o PC estava desligado as 11h, roda assim que
# puder). So roda com o usuario logado - usa o mesmo acesso ao GitHub que o git ja tem, sem guardar senha.
# Desfazer: desinstalar-coleta-rio.ps1 (tira a tarefa; a pasta %USERPROFILE%\coleta-rio fica, com o registro).
$ErrorActionPreference = 'Stop'
$nome = 'Coleta Rio (CEASA-RJ)'
$base = Join-Path $env:USERPROFILE 'coleta-rio'
New-Item -ItemType Directory -Force -Path $base | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot 'coleta-rio.ps1') (Join-Path $base 'coleta-rio.ps1')

$acao = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f (Join-Path $base 'coleta-rio.ps1'))
$diario = New-ScheduledTaskTrigger -Daily -At '11:00'
$entrada = New-ScheduledTaskTrigger -AtLogOn -User ('{0}\{1}' -f $env:USERDOMAIN, $env:USERNAME)
$entrada.Delay = 'PT3M'
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName $nome -Action $acao -Trigger @($diario, $entrada) -Settings $config -Force `
  -Description 'Baixa o boletim do CEASA-RJ (banana prata) e manda ao GitHub (coleta-precos-banana/rio). Criada em 09/11/2026.' | Out-Null
Write-Host ('Tarefa criada: ' + $nome + '. Rodando uma vez agora para conferir...')

Start-ScheduledTask -TaskName $nome
$limite = (Get-Date).AddMinutes(4)
do { Start-Sleep -Seconds 5 } while ((Get-ScheduledTask -TaskName $nome).State -eq 'Running' -and (Get-Date) -lt $limite)
Write-Host '--- ultimas linhas do registro ---'
Get-Content (Join-Path $base 'coleta-rio.log') -Tail 8 -Encoding UTF8
