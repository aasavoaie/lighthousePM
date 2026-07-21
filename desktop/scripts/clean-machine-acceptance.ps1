param(
  [string]$SetupPath = "",
  [string]$PreviousSetupPath = "",
  [string]$BackupRoot = "",
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
$UserDataDirectory = Join-Path $env:APPDATA "LighthousePM"
$DatabasePath = Join-Path $UserDataDirectory "data\lighthouse.db"
$UserConfigPath = Join-Path $UserDataDirectory "backend.env"
$TokenPath = Join-Path $UserDataDirectory "secrets\jira-token.bin"
$UpgradeEvidenceBefore = $null

if ([string]::IsNullOrWhiteSpace($SetupPath)) {
  $SetupPath = Join-Path $DesktopRoot "out\make\squirrel.windows\x64\LighthousePM-Setup.exe"
}
if ([string]::IsNullOrWhiteSpace($BackupRoot)) {
  $BackupRoot = Join-Path $ReportDirectory "storage-lifecycle-$Timestamp"
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

function Get-OptionalFileHash {
  param([string]$FilePath)
  if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
    return ""
  }
  try {
    return (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash
  } catch {
    return ""
  }
}

function Get-ConfigurationPathEvidence {
  $InstalledApp = Find-InstalledApp
  $SidecarConfigPath = if ($null -ne $InstalledApp) {
    Join-Path $InstalledApp.DirectoryName "backend.env"
  } else {
    ""
  }
  $EffectiveConfigPath = if (
    $SidecarConfigPath -and
    (Test-Path -LiteralPath $SidecarConfigPath -PathType Leaf)
  ) {
    $SidecarConfigPath
  } else {
    $UserConfigPath
  }
  return [pscustomobject]@{
    EffectivePath = $EffectiveConfigPath
    UserPath = $UserConfigPath
    UserExists = Test-Path -LiteralPath $UserConfigPath -PathType Leaf
    SidecarPath = $SidecarConfigPath
    SidecarExists = [bool](
      $SidecarConfigPath -and
      (Test-Path -LiteralPath $SidecarConfigPath -PathType Leaf)
    )
  }
}

function Get-DesktopStateEvidence {
  $ConfigurationPaths = Get-ConfigurationPathEvidence
  $ConfigPath = $ConfigurationPaths.EffectivePath
  $Database = Get-Item -LiteralPath $DatabasePath -ErrorAction SilentlyContinue
  return [pscustomobject]@{
    DatabaseExists = $null -ne $Database
    DatabaseBytes = if ($null -ne $Database) { $Database.Length } else { 0 }
    ConfigExists = Test-Path -LiteralPath $ConfigPath -PathType Leaf
    ConfigHash = Get-OptionalFileHash $ConfigPath
    ConfigPath = $ConfigPath
    UserConfigExists = $ConfigurationPaths.UserExists
    SidecarConfigExists = $ConfigurationPaths.SidecarExists
    TokenExists = Test-Path -LiteralPath $TokenPath -PathType Leaf
    TokenHash = Get-OptionalFileHash $TokenPath
  }
}

function Add-RequiredDesktopStateResults {
  param(
    [object]$Evidence,
    [string]$AreaPrefix
  )

  if ($Evidence.DatabaseExists -and $Evidence.DatabaseBytes -gt 0) {
    Add-Result "$AreaPrefix database" "Pass" "Database exists at $DatabasePath with $($Evidence.DatabaseBytes) bytes."
  } else {
    Add-Result "$AreaPrefix database" "Fail" "A non-empty database was not found at $DatabasePath."
  }
  if ($Evidence.ConfigExists) {
    Add-Result "$AreaPrefix configuration" "Pass" "Configuration exists at $($Evidence.ConfigPath)."
  } else {
    Add-Result "$AreaPrefix configuration" "Fail" "Configuration was not found at $($Evidence.ConfigPath)."
  }
  if ($Evidence.TokenExists) {
    Add-Result "$AreaPrefix encrypted token" "Pass" "Encrypted token exists at $TokenPath."
  } else {
    Add-Result "$AreaPrefix encrypted token" "Fail" "Encrypted token was not found at $TokenPath."
  }
}

function Compare-UpgradeEvidence {
  param(
    [object]$Before,
    [object]$After
  )

  Add-RequiredDesktopStateResults -Evidence $After -AreaPrefix "Post-upgrade"
  if ($Before.ConfigHash -and $Before.ConfigHash -eq $After.ConfigHash) {
    Add-Result "Upgrade configuration preservation" "Pass" "backend.env SHA-256 is unchanged."
  } else {
    Add-Result "Upgrade configuration preservation" "Fail" "backend.env is missing or changed during installation."
  }
  if ($Before.TokenHash -and $Before.TokenHash -eq $After.TokenHash) {
    Add-Result "Upgrade token preservation" "Pass" "Encrypted Jira token SHA-256 is unchanged."
  } else {
    Add-Result "Upgrade token preservation" "Fail" "Encrypted Jira token is missing or changed during installation."
  }
  if ($After.DatabaseExists -and $After.DatabaseBytes -gt 0) {
    Add-Result "Upgrade database preservation" "Pass" "The database remains non-empty; its hash is not compared because schema migration legitimately changes it."
  } else {
    Add-Result "Upgrade database preservation" "Fail" "The active database is missing or empty after upgrade."
  }
}

function Get-MigrationBackupEvidence {
  $DataDirectory = Split-Path -Parent $DatabasePath
  $Fingerprints = @()
  if (Test-Path -LiteralPath $DataDirectory -PathType Container) {
    $Fingerprints = @(
      Get-ChildItem -LiteralPath $DataDirectory -File -Filter "lighthouse.db.pre-*.bak" |
        Sort-Object Name |
        ForEach-Object {
          "$($_.Name)|$($_.Length)|$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash)"
        }
    )
  }
  return [pscustomobject]@{
    Count = $Fingerprints.Count
    Fingerprints = $Fingerprints
  }
}

function Add-MigrationBackupRetentionResult {
  param(
    [object]$Before,
    [object]$After,
    [string]$Area
  )

  $BeforeValue = [string]::Join("`n", [string[]]@($Before.Fingerprints))
  $AfterValue = [string]::Join("`n", [string[]]@($After.Fingerprints))
  if ($BeforeValue -eq $AfterValue) {
    Add-Result $Area "Pass" "Automatic migration-backup set is unchanged ($($After.Count) file(s), matched by name, size, and SHA-256)."
  } else {
    Add-Result $Area "Fail" "Automatic migration-backup set changed. Before: $($Before.Count) file(s); after: $($After.Count) file(s)."
  }
}

function Add-RetainedSettingsResults {
  param(
    [object]$Before,
    [object]$After,
    [string]$AreaPrefix
  )

  if ($Before.ConfigHash -and $Before.ConfigHash -eq $After.ConfigHash) {
    Add-Result "$AreaPrefix configuration retention" "Pass" "Effective backend.env SHA-256 is unchanged at $($After.ConfigPath)."
  } else {
    Add-Result "$AreaPrefix configuration retention" "Fail" "Effective backend.env is missing or changed."
  }
  if ($Before.TokenHash -and $Before.TokenHash -eq $After.TokenHash) {
    Add-Result "$AreaPrefix token retention" "Pass" "Encrypted Jira token SHA-256 is unchanged."
  } else {
    Add-Result "$AreaPrefix token retention" "Fail" "Encrypted Jira token is missing or changed."
  }
}

function Get-ValidatedSettingsBackupEvidence {
  param([string]$RootPath)

  try {
    $ResolvedRoot = Resolve-FullPath $RootPath
    if (-not (Test-Path -LiteralPath $ResolvedRoot -PathType Container)) {
      throw "Backup root does not exist: $ResolvedRoot"
    }
    $BackupDirectory = Get-ChildItem -LiteralPath $ResolvedRoot -Directory -Filter "lighthousepm-backup-*" |
      Sort-Object LastWriteTimeUtc -Descending |
      Select-Object -First 1
    if ($null -eq $BackupDirectory) {
      throw "No lighthousepm-backup-* directory was found under $ResolvedRoot"
    }
    $ManifestPath = Join-Path $BackupDirectory.FullName "manifest.json"
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
      throw "manifest.json is missing from $($BackupDirectory.FullName)"
    }
    $Manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
    if ($Manifest.app -ne "LighthousePM" -or $Manifest.version -ne 2) {
      throw "Manifest identity or version is invalid"
    }
    $AllowedPaths = @("backend.env", "data/lighthouse.db", "secrets/jira-token.bin")
    $RequiredPaths = @("backend.env", "data/lighthouse.db", "secrets/jira-token.bin")
    $FileProperties = @($Manifest.files.PSObject.Properties)
    if ($FileProperties.Count -eq 0) {
      throw "Manifest contains no payloads"
    }
    $FileHashes = @{}
    foreach ($FileProperty in $FileProperties) {
      $RelativePath = $FileProperty.Name
      if ($RelativePath -notin $AllowedPaths) {
        throw "Manifest contains unsupported payload path: $RelativePath"
      }
      $PayloadPath = Join-Path $BackupDirectory.FullName ($RelativePath -replace "/", "\")
      $Payload = Get-Item -LiteralPath $PayloadPath -ErrorAction Stop
      if ($Payload.PSIsContainer) {
        throw "Backup payload is not a file: $RelativePath"
      }
      $Metadata = $FileProperty.Value
      $ActualHash = (Get-FileHash -LiteralPath $Payload.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
      $ExpectedHash = ([string]$Metadata.sha256).ToLowerInvariant()
      if ($Payload.Length -ne [long]$Metadata.sizeBytes -or $ActualHash -ne $ExpectedHash) {
        throw "Backup payload size or SHA-256 mismatch: $RelativePath"
      }
      $FileHashes[$RelativePath] = $ActualHash
    }
    foreach ($RequiredPath in $RequiredPaths) {
      if (-not $FileHashes.ContainsKey($RequiredPath)) {
        throw "Acceptance backup is missing required payload: $RequiredPath"
      }
    }
    if (
      $null -eq $Manifest.database -or
      [string]::IsNullOrWhiteSpace([string]$Manifest.database.revision) -or
      $Manifest.database.revisionKind -notin @("alembic", "recognized_legacy")
    ) {
      throw "Manifest database revision identity is invalid"
    }
    Add-Result "Settings Backup manifest" "Pass" "Validated version-2 manifest and three payload hashes at $($BackupDirectory.FullName)."
    return [pscustomobject]@{
      Directory = $BackupDirectory.FullName
      FileHashes = $FileHashes
    }
  } catch {
    Add-Result "Settings Backup manifest" "Fail" $_.Exception.Message
    return $null
  }
}

function Add-RestoreStateResults {
  param(
    [object]$BackupEvidence,
    [object]$After
  )

  if ($After.DatabaseExists -and $After.DatabaseBytes -gt 0) {
    Add-Result "Settings Restore database" "Pass" "A non-empty active database exists after restore."
  } else {
    Add-Result "Settings Restore database" "Fail" "The active database is missing or empty after restore."
  }
  if (
    $null -ne $BackupEvidence -and
    $After.ConfigHash -and
    $After.ConfigHash.ToLowerInvariant() -eq $BackupEvidence.FileHashes["backend.env"]
  ) {
    Add-Result "Settings Restore configuration" "Pass" "Effective backend.env matches the accepted backup SHA-256."
  } else {
    Add-Result "Settings Restore configuration" "Fail" "Effective backend.env does not match the accepted backup."
  }
  if (
    $null -ne $BackupEvidence -and
    $After.TokenHash -and
    $After.TokenHash.ToLowerInvariant() -eq $BackupEvidence.FileHashes["secrets/jira-token.bin"]
  ) {
    Add-Result "Settings Restore token" "Pass" "Encrypted Jira token matches the accepted backup SHA-256."
  } else {
    Add-Result "Settings Restore token" "Fail" "Encrypted Jira token does not match the accepted backup."
  }
}

function Add-FactoryResetStateResults {
  param([object]$After)

  if ($After.DatabaseExists -and $After.DatabaseBytes -gt 0) {
    Add-Result "Factory Reset database" "Pass" "A fresh non-empty SQLite database exists."
  } else {
    Add-Result "Factory Reset database" "Fail" "A fresh SQLite database was not created."
  }
  if (-not $After.UserConfigExists -and -not $After.SidecarConfigExists) {
    Add-Result "Factory Reset configuration" "Pass" "User-data and application-sidecar backend.env files are absent."
  } else {
    Add-Result "Factory Reset configuration" "Fail" "A backend.env file remains in user data or beside the installed application."
  }
  if (-not $After.TokenExists) {
    Add-Result "Factory Reset encrypted token" "Pass" "Encrypted Jira token is absent."
  } else {
    Add-Result "Factory Reset encrypted token" "Fail" "Encrypted Jira token remains after Factory Reset."
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
  $Lines.Add("- Storage lifecycle backup root: $(Resolve-FullPath $BackupRoot)")
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
  $Lines.Add("- Settings Backup produced a validated version-2 manifest with database, configuration, and encrypted-token payloads.")
  $Lines.Add("- Clear Data returned structured empty release and sprint results while retaining configuration, token, and migration backups.")
  $Lines.Add("- Settings Restore returned visible release and sprint data and usable configuration/token access.")
  $Lines.Add("- Factory Reset returned first-run state while retaining automatic migration backups.")
  $Lines.Add("- App restarted offline and loaded the local dashboard without Jira access.")
  $Lines.Add("- PDF export used the native save dialog and produced a readable PDF.")
  if ([string]::IsNullOrWhiteSpace($PreviousSetupPath)) {
    $Lines.Add("- Clean startup created an isolated database and UI configuration without prior LighthousePM user data.")
  } else {
    $Lines.Add("- Upgrade preserved the database, backend.env, encrypted Jira token, and visible workspace data.")
  }
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

if ($SkipInstall) {
  Add-Result "Isolated user-data precondition" "Pending" "User-data precondition skipped with -SkipInstall."
} elseif (Test-Path -LiteralPath $UserDataDirectory) {
  Add-Result "Isolated user-data precondition" "Fail" "Existing LighthousePM user data was found at $UserDataDirectory."
} else {
  Add-Result "Isolated user-data precondition" "Pass" "No prior LighthousePM user data exists at $UserDataDirectory."
}

if (-not [string]::IsNullOrWhiteSpace($PreviousSetupPath)) {
  if ($SkipInstall) {
    Add-Result "Previous version install" "Pending" "Skipped by -SkipInstall."
  } else {
    Invoke-Installer -InstallerPath $PreviousSetupPath -Area "Previous version install"
    Start-LighthousePM
    Confirm-Step "Previous version seed" "Configure Jira and sync data in the previous version. Confirm releases and sprints are visible before upgrading."
    $UpgradeEvidenceBefore = Get-DesktopStateEvidence
    Add-RequiredDesktopStateResults -Evidence $UpgradeEvidenceBefore -AreaPrefix "Pre-upgrade"
    Confirm-Step "Previous version shutdown" "Fully quit the previous LighthousePM version before installing the current build."
  }
}

if ($SkipInstall) {
  Add-Result "Current version install" "Pending" "Skipped by -SkipInstall."
} else {
  Invoke-Installer -InstallerPath $SetupPath -Area "Current version install"
}

Start-LighthousePM
if ([string]::IsNullOrWhiteSpace($PreviousSetupPath)) {
  Confirm-Step "Setup through UI" "Open Settings and configure Jira URL, email, token, project key, and field mappings without editing backend/.env or backend.env manually."
  Confirm-Step "Sync Jira" "Click Sync Jira. Confirm sync completes and release plus sprint information are visible."
  Add-RequiredDesktopStateResults -Evidence (Get-DesktopStateEvidence) -AreaPrefix "Clean-install"
} elseif ($null -ne $UpgradeEvidenceBefore) {
  Compare-UpgradeEvidence -Before $UpgradeEvidenceBefore -After (Get-DesktopStateEvidence)
  Confirm-Step "Upgrade workspace data" "Confirm the current build shows the release and sprint data synchronized in the previous version. A running process alone is not sufficient."
}
Confirm-Step "Offline restart" "Disconnect from the network, fully quit LighthousePM, reopen it, and confirm the local dashboard loads from stored data."
Confirm-Step "PDF export" "Export a PDF report. Confirm the native save dialog appears and the saved PDF opens successfully."

New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
Confirm-Step "Settings Backup creation" "Run Settings Backup and select $(Resolve-FullPath $BackupRoot). Confirm the app reports Backup created only after synchronized release and sprint data are visible."
$BackupEvidence = Get-ValidatedSettingsBackupEvidence -RootPath $BackupRoot

$BeforeClearState = Get-DesktopStateEvidence
$BeforeClearMigrationBackups = Get-MigrationBackupEvidence
Confirm-Step "Clear Data API state" "Run Clear Data. Confirm Releases and Sprints show structured empty results and Settings still shows the configured Jira account and token."
$AfterClearState = Get-DesktopStateEvidence
if ($AfterClearState.DatabaseExists -and $AfterClearState.DatabaseBytes -gt 0) {
  Add-Result "Clear Data database" "Pass" "A fresh non-empty SQLite database exists after Clear Data."
} else {
  Add-Result "Clear Data database" "Fail" "Clear Data did not create a fresh SQLite database."
}
Add-RetainedSettingsResults -Before $BeforeClearState -After $AfterClearState -AreaPrefix "Clear Data"
Add-MigrationBackupRetentionResult `
  -Before $BeforeClearMigrationBackups `
  -After (Get-MigrationBackupEvidence) `
  -Area "Clear Data migration-backup retention"

$RestorePath = if ($null -ne $BackupEvidence) {
  $BackupEvidence.Directory
} else {
  Resolve-FullPath $BackupRoot
}
Confirm-Step "Settings Restore workspace" "Run Settings Restore from $RestorePath. Confirm the original release and sprint data are visible and Jira configuration/token access remains usable."
$AfterRestoreState = Get-DesktopStateEvidence
Add-RestoreStateResults -BackupEvidence $BackupEvidence -After $AfterRestoreState

$BeforeFactoryResetMigrationBackups = Get-MigrationBackupEvidence
Confirm-Step "Factory Reset first-run state" "Run Factory Reset. Confirm synchronized data, configuration, token, and previous logs are removed; new startup logging may exist; and the app returns to first-run setup."
$AfterFactoryResetState = Get-DesktopStateEvidence
Add-FactoryResetStateResults -After $AfterFactoryResetState
Add-MigrationBackupRetentionResult `
  -Before $BeforeFactoryResetMigrationBackups `
  -After (Get-MigrationBackupEvidence) `
  -Area "Factory Reset migration-backup retention"

Invoke-UninstallCheck
Write-Report
