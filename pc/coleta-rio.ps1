# coleta-rio.ps1 - roda pelo Agendador do Windows (instalado por instalar-coleta-rio.ps1).
# ARQUIVO SO COM CARACTERES ASCII DE PROPOSITO: o PowerShell 5.1 le .ps1 sem BOM como ANSI, e um travessao ou
# acento dentro de texto entre aspas vira aspa solta e quebra o script.
#
# Coleta SO o Rio: o site do CEASA-RJ recusa a conexao vinda do GitHub (fora do Brasil) e funciona deste PC.
# Atualiza rio/precos_rio_ceasarj.csv numa copia PROPRIA do repositorio (%USERPROFILE%\coleta-rio) e manda ao
# GitHub; o robo diario de la (15h) usa a cotacao mais nova. PC desligado = Rio fica velho e a reserva cobre.
# Registro de cada execucao em %USERPROFILE%\coleta-rio\coleta-rio.log (inicio, fim, resultado, id da execucao).
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$base   = Join-Path $env:USERPROFILE 'coleta-rio'
$repo   = Join-Path $base 'coleta-precos-banana'
$log    = Join-Path $base 'coleta-rio.log'
$git    = 'C:\Program Files\Git\cmd\git.exe'
$python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
$id = [guid]::NewGuid().ToString().Substring(0, 8)

function Log([string]$m) { Add-Content -Path $log -Encoding UTF8 -Value ('{0} [{1}] {2}' -f (Get-Date -Format s), $id, $m) }
function Git { & $git -C $repo @args 2>&1 | ForEach-Object { Log ('git: ' + $_) }; return $LASTEXITCODE }

New-Item -ItemType Directory -Force -Path $base | Out-Null
Log 'inicio'
try {
  if (-not (Test-Path (Join-Path $repo '.git'))) {
    & $git clone --quiet https://github.com/edsonyukiosassaki-lab/coleta-precos-banana.git $repo 2>&1 | ForEach-Object { Log ('git: ' + $_) }
    if ($LASTEXITCODE -ne 0) { throw 'git clone falhou' }
  }
  if ((Git pull --rebase --quiet origin main) -ne 0) { throw 'git pull falhou' }

  & $python -I (Join-Path $repo 'scripts\coletar_precos_ceasas.py') --so-rio (Join-Path $repo 'rio\precos_rio_ceasarj.csv') 2>&1 |
    ForEach-Object { Log ('robo: ' + $_) }
  if ($LASTEXITCODE -ne 0) { throw 'coleta do Rio falhou (ver as linhas robo: acima)' }

  Git add rio/precos_rio_ceasarj.csv | Out-Null
  & $git -C $repo diff --cached --quiet
  if ($LASTEXITCODE -eq 0) { Log 'fim: OK - a serie ja tinha este dia, nada a enviar'; exit 0 }
  if ((Git commit --quiet -m ('rio: cotacao do CEASA-RJ coletada pelo PC ' + (Get-Date -Format 'yyyy-MM-dd'))) -ne 0) { throw 'commit falhou' }

  # o robo do GitHub tambem grava neste repositorio (15h): se o envio bater, puxa de novo e tenta (3 vezes, espera crescente)
  for ($i = 1; $i -le 3; $i++) {
    if ((Git push --quiet origin main) -eq 0) { Log 'fim: OK - enviado ao GitHub'; exit 0 }
    Start-Sleep -Seconds (20 * $i)
    Git pull --rebase --quiet origin main | Out-Null
  }
  throw 'envio ao GitHub falhou 3 vezes'
} catch {
  Log ('fim: FALHOU - ' + $_)
  exit 1
}
