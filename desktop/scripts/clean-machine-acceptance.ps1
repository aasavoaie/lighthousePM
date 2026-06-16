param(
  [string]$SetupPath = "",
  [string]$PreviousSetupPath = "",
  [switch]$RequireNoDevTools,
  [switch]$SkipInstall,
  [switch]$NoLaunch,
  [switch]$RunUninstall,
  [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

$DesktopRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PackageJson = Get-Content -Raw -LiteralPath (Join-Path $DesktopRoot "package.json") | ConvertFrom-Json
$Version = $PackageJson.version
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ReportDirectory = Join-Path $DesktopRoot "out\acceptance"
$ReportPath = Join-Path $ReportDirectory "clean-machine-acceptance-$Timestamp.md"
$Results = New-Object System.Collections.Generic.List[object]

if ([string]::IsNullOrWhiteSpace($SetupPath)) {
  $SetupPath = Join-Path $DesktopRoot "out\make\squirrel.windows\x64\LighthousePM-Setup.exe"
}

function Add-Result {
  param(
    [string]$Area,
    [string]$Status,
    [string]$Evidence
  )
  $Results.Add([pscustomobject]@{
    Area = $Area
    Status = $Status
    Evidence = $Evidence
  })
  Write-Host "[$Status] $Area - $Evidence"
}

function Resolve-FullPath {
  param([string]$PathValue)
  if ([string]::IsNullOrWhiteSpace($PathValue)) {
    return ""
  }
  return [System.IO.Path]::GetFullPath($PathValue)
}

function Test-CommandMissing {
  param([string]$CommandName)
  $Command = Get-Command $CommandName -ErrorAction SilentlyContinue
  if ($null -eq $Command) {
    Add-Result "Prerequisite: $CommandName absent" "Pass" "$CommandName is not on PATH."
  } else {
    Add-Result "Prerequisite: $CommandName absent" "Fail" "$CommandName was found at $($Command.Source)."
  }
}

function Find-InstalledApp {
  $InstallRoot = Join-Path $env:LOCALAPPDATA "lighthousepm"
  if (-not (Test-Path -LiteralPath $InstallRoot)) {
    return $null
  }

  $DirectExe = Join-Path $InstallRoot "LighthousePM.exe"
  if (Test-Path -LiteralPath $DirectExe) {
    return Get-Item -LiteralPath $DirectExe
  }

  return Get-ChildItem -LiteralPath $InstallRoot -Recurse -Filter "LighthousePM.exe" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
}

function Find-SquirrelUpdate {
  $UpdatePath = Join-Path (Join-Path $env:LOCALAPPDATA "lighthousepm") "Update.exe"
  if (Test-Path -LiteralPath $UpdatePath) {
    return Get-Item -LiteralPath $UpdatePath
  }
  return $null
}

function Invoke-Installer {
  param(
    [string]$InstallerPath,
    [string]$Area
  )

  $ResolvedInstaller = Resolve-FullPath $InstallerPath
  if (-not (Test-Path -LiteralPath $ResolvedInstaller)) {
    Add-Result $Area "Fail" "Installer not found at $ResolvedInstaller."
    return
  }

  Add-Result $Area "Pass" "Installer found at $ResolvedInstaller."
  $Process = Start-Process -FilePath $ResolvedInstaller -PassThru -Wait
  if ($Process.ExitCode -eq 0) {
    Add-Result "$Area exit code" "Pass" "Setup exited with code 0."
  } else {
    Add-Result "$Area exit code" "Fail" "Setup exited with code $($Process.ExitCode)."
  }
}

function Start-LighthousePM {
  if ($NoLaunch) {
    Add-Result "Launch" "Pending" "Launch check skipped by -NoLaunch."
    return
  }

  $InstalledApp = Find-InstalledApp
  if ($null -eq $InstalledApp) {
    Add-Result "Launch" "Fail" "Installed LighthousePM.exe was not found under %LOCALAPPDATA%\lighthousepm."
    return
  }

  $Process = Start-Process -FilePath $InstalledApp.FullName -PassThru
  Start-Sleep -Seconds 10
  $Running = Get-Process -Name "LighthousePM" -ErrorAction SilentlyContinue
  if ($null -eq $Running) {
    Add-Result "Launch" "Fail" "LighthousePM process was not running after launch."
  } else {
    Add-Result "Launch" "Pass" "LighthousePM launched from $($InstalledApp.FullName)."
  }
}

function Confirm-Step {
  param(
    [string]$Area,
    [string]$Prompt
  )

  if ($NonInteractive) {
    Add-Result $Area "Pending" $Prompt
    return
  }

  Write-Host ""
  Write-Host $Prompt
  $Answer = Read-Host "Enter P for pass, F for fail, or S for skip"
  switch ($Answer.Trim().ToUpperInvariant()) {
    "P" { Add-Result $Area "Pass" $Prompt }
    "F" { Add-Result $Area "Fail" $Prompt }
    default { Add-Result $Area "Pending" $Prompt }
  }
}

function Invoke-UninstallCheck {
  if (-not $RunUninstall) {
    Confirm-Step "Uninstall" "Uninstall from Windows Apps, then verify the LighthousePM shortcut is removed. User data may remain unless Factory Reset was run first."
    return
  }

  $Update = Find-SquirrelUpdate
  if ($null -eq $Update) {
    Add-Result "Uninstall" "Fail" "Squirrel Update.exe was not found."
    return
  }

  $Process = Start-Process -FilePath $Update.FullName -ArgumentList "--uninstall" -PassThru -Wait
  Start-Sleep -Seconds 3
  if ($Process.ExitCode -eq 0 -and $null -eq (Find-InstalledApp)) {
    Add-Result "Uninstall" "Pass" "Squirrel uninstall completed and app executable is gone."
  } else {
    Add-Result "Uninstall" "Fail" "Uninstall exit code was $($Process.ExitCode), app executable still present: $($null -ne (Find-InstalledApp))."
  }
}

function Write-Report {
  New-Item -ItemType Directory -Force -Path $ReportDirectory | Out-Null
  $FailureCount = ($Results | Where-Object { $_.Status -eq "Fail" }).Count
  $PendingCount = ($Results | Where-Object { $_.Status -eq "Pending" }).Count
  $Approval = if ($FailureCount -eq 0 -and $PendingCount -eq 0) { "APPROVED" } else { "NOT APPROVED" }

  $Lines = New-Object System.Collections.Generic.List[string]
  $Lines.Add("# LighthousePM Clean-Machine Acceptance")
  $Lines.Add("")
  $Lines.Add("- Version: $Version")
  $Lines.Add("- Date: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz")")
  $Lines.Add("- Machine: $env:COMPUTERNAME")
  $Lines.Add("- User: $env:USERNAME")
  $Lines.Add("- Setup: $(Resolve-FullPath $SetupPath)")
  if (-not [string]::IsNullOrWhiteSpace($PreviousSetupPath)) {
    $Lines.Add("- Previous setup: $(Resolve-FullPath $PreviousSetupPath)")
  }
  $Lines.Add("- Approval: $Approval")
  $Lines.Add("")
  $Lines.Add("| Area | Status | Evidence |")
  $Lines.Add("| --- | --- | --- |")
  foreach ($Result in $Results) {
    $Evidence = $Result.Evidence.Replace("|", "\|")
    $Lines.Add("| $($Result.Area) | $($Result.Status) | $Evidence |")
  }
  $Lines.Add("")
  $Lines.Add("## Required Manual Evidence")
  $Lines.Add("")
  $Lines.Add("- Jira setup was completed through Settings without editing `.env`.")
  $Lines.Add("- Sync Jira completed and release plus sprint information was visible.")
  $Lines.Add("- App restarted offline and loaded the local dashboard without Jira access.")
  $Lines.Add("- PDF export used the native save dialog and produced a readable PDF.")
  $Lines.Add("- Factory Reset removed local app data and returned the app to first-run setup.")
  $Lines.Add("- Upgrade preserved local data across versions.")
  $Lines.Add("- Uninstall removed the app and shortcuts.")
  $Lines.Add("")

  Set-Content -LiteralPath $ReportPath -Value $Lines -Encoding UTF8
  Write-Host ""
  Write-Host "Acceptance report written to $ReportPath"
  Write-Host "Release approval: $Approval"

  if ($FailureCount -gt 0) {
    exit 1
  }
  if ($PendingCount -gt 0) {
    exit 2
  }
}

if (-not $IsWindows -and $PSVersionTable.PSEdition -eq "Core") {
  Add-Result "Operating system" "Fail" "This acceptance test must run on Windows."
  Write-Report
}

Add-Result "Operating system" "Pass" "Running on $([System.Environment]::OSVersion.VersionString)."

if ($RequireNoDevTools) {
  Test-CommandMissing "python"
  Test-CommandMissing "node"
  Test-CommandMissing "psql"
  Test-CommandMissing "docker"
} else {
  Add-Result "Clean-machine prerequisite" "Pending" "Run with -RequireNoDevTools on a machine without Python, Node, PostgreSQL, or Docker."
}

if (-not [string]::IsNullOrWhiteSpace($PreviousSetupPath)) {
  if ($SkipInstall) {
    Add-Result "Previous version install" "Pending" "Skipped by -SkipInstall."
  } else {
    Invoke-Installer -InstallerPath $PreviousSetupPath -Area "Previous version install"
    Start-LighthousePM
    Confirm-Step "Previous version seed" "Configure Jira and sync data in the previous version. Confirm releases and sprints are visible before upgrading."
  }
}

if ($SkipInstall) {
  Add-Result "Current version install" "Pending" "Skipped by -SkipInstall."
} else {
  Invoke-Installer -InstallerPath $SetupPath -Area "Current version install"
}

Start-LighthousePM
Confirm-Step "Setup through UI" "Open Settings and configure Jira URL, email, token, project key, and field mappings without editing backend/.env or backend.env manually."
Confirm-Step "Sync Jira" "Click Sync Jira. Confirm sync completes and release plus sprint information are visible."
Confirm-Step "Offline restart" "Disconnect from the network, fully quit LighthousePM, reopen it, and confirm the local dashboard loads from stored data."
Confirm-Step "PDF export" "Export a PDF report. Confirm the native save dialog appears and the saved PDF opens successfully."
Confirm-Step "Factory reset" "Run Factory Reset from Settings. Confirm local data is cleared and the app returns to first-run setup/configuration state."

if ([string]::IsNullOrWhiteSpace($PreviousSetupPath)) {
  Confirm-Step "Upgrade" "Install this build over a previous installed version and confirm local data remains available after restart."
} else {
  Confirm-Step "Upgrade" "Confirm the current version installed over the previous version and preserved local data."
}

Invoke-UninstallCheck
Write-Report
