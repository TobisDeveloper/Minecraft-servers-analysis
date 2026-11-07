param(
    [string]$Time = "08:00",
    [string]$TaskName = "CZSK Minecraft Trendfinder"
)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) { throw "Run Setup-Windows.cmd first." }
$Arguments = '-m trendfinder scan --data-dir "' + (Join-Path $Repo "data") + '"'
$Config = Join-Path $Repo "config.local.json"
if (Test-Path $Config) { $Arguments += ' --config "' + $Config + '"' }
$Action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $Repo
$Trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::ParseExact($Time, "HH:mm", $null))
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)
# Current-user task; no elevation, stored password, or interactive login prompt.
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Collect CZ/SK Minecraft signals and generate an English report" | Out-Null
Write-Host "Scheduled daily at $Time. Reports: $Repo\data\reports"
Write-Host "Uses the task user's environment variables. No secrets are stored in this task."
