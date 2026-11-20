<#
.SYNOPSIS
  Registra no Agendador de Tarefas do Windows a verificacao diaria dos dados abertos do CNPJ.

.DESCRIPTION
  A tarefa executa scripts\atualizar_receita.py todo dia no horario indicado. Quando nao ha
  competencia nova, o script encerra em poucos segundos; quando ha, baixa e trata os arquivos.
  Se o computador estiver desligado no horario, a tarefa roda assim que ele for ligado.
  A execucao usa pythonw.exe (sem janela); acompanhe pelo log em logs\atualizar_receita.log.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File data_processing\agendar_atualizacao.ps1
  powershell -ExecutionPolicy Bypass -File data_processing\agendar_atualizacao.ps1 -Horario 02:30
  powershell -ExecutionPolicy Bypass -File data_processing\agendar_atualizacao.ps1 -Remover
#>
param(
    [string]$Horario = "03:00",
    [string]$NomeTarefa = "CNPJ Receita Federal - atualizacao",
    [string]$Python = "",
    [switch]$Remover
)
$ErrorActionPreference = "Stop"

if ($Remover) {
    Unregister-ScheduledTask -TaskName $NomeTarefa -Confirm:$false
    Write-Host "Tarefa '$NomeTarefa' removida."
    return
}

$script = Join-Path $PSScriptRoot "scripts\atualizar_receita.py"
$projectRoot = Split-Path $PSScriptRoot -Parent
if (-not $Python) {
    $pythonExe = (Get-Command python -ErrorAction Stop).Source
    $pythonw = Join-Path (Split-Path $pythonExe -Parent) "pythonw.exe"
    $Python = if (Test-Path $pythonw) { $pythonw } else { $pythonExe }
}

$action = New-ScheduledTaskAction -Execute $Python -Argument "`"$script`"" -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $Horario
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 12) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $NomeTarefa -Action $action -Trigger $trigger -Settings $settings `
    -Description "Verifica diariamente se a Receita Federal publicou nova competencia dos dados abertos do CNPJ; baixa e trata quando houver." `
    -Force | Out-Null

Write-Host "Tarefa '$NomeTarefa' registrada: todo dia as $Horario."
Write-Host "  Python : $Python"
Write-Host "  Script : $script"
Write-Host "  Log    : $(Join-Path $PSScriptRoot 'logs\atualizar_receita.log')"
Write-Host "Executar agora : Start-ScheduledTask -TaskName '$NomeTarefa'"
Write-Host "Ultimo resultado: Get-ScheduledTaskInfo -TaskName '$NomeTarefa'"
