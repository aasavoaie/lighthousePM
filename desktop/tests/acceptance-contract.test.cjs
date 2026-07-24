const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const ACCEPTANCE_SCRIPT_PATH = path.resolve(
  __dirname,
  "..",
  "scripts",
  "clean-machine-acceptance.ps1",
);
const acceptanceSource = fs.readFileSync(ACCEPTANCE_SCRIPT_PATH, "utf8");

function assertInOrder(source, markers) {
  let previousIndex = -1;
  for (const marker of markers) {
    const index = source.indexOf(marker, previousIndex + 1);
    assert.ok(index > previousIndex, `${JSON.stringify(marker)} must occur in order`);
    previousIndex = index;
  }
}

test("packaged acceptance follows the approved backup, clear, restore, and reset sequence", () => {
  assertInOrder(acceptanceSource, [
    'Confirm-Step "Sync Jira"',
    'Confirm-Step "Settings Backup creation"',
    "Get-ValidatedSettingsBackupEvidence -RootPath $BackupRoot",
    'Confirm-Step "Clear Data API state"',
    'Add-RetainedSettingsResults -Before $BeforeClearState',
    'Area "Clear Data migration-backup retention"',
    'Confirm-Step "Settings Restore workspace"',
    "Add-RestoreStateResults -BackupEvidence $BackupEvidence",
    'Confirm-Step "Factory Reset first-run state"',
    "Add-FactoryResetStateResults -After $AfterFactoryResetState",
    'Area "Factory Reset migration-backup retention"',
  ]);
});

test("packaged acceptance validates exact version-2 payload and migration-backup evidence", () => {
  assert.match(acceptanceSource, /\$Manifest\.app -ne "LighthousePM"/);
  assert.match(acceptanceSource, /\$Manifest\.version -ne 2/);
  for (const relativePath of ["backend.env", "data/lighthouse.db", "secrets/jira-token.bin"]) {
    assert.match(acceptanceSource, new RegExp(relativePath.replace(/[./]/g, "\\$&")));
  }
  assert.match(acceptanceSource, /Get-FileHash -LiteralPath \$Payload\.FullName -Algorithm SHA256/);
  assert.match(acceptanceSource, /lighthouse\.db\.pre-\*\.bak/);
  assert.match(acceptanceSource, /Automatic migration-backup set is unchanged/);
  assert.match(acceptanceSource, /matched by name, size, and SHA-256/);
});

test("packaged acceptance supports user-data and application-sidecar configuration", () => {
  assertInOrder(acceptanceSource, [
    "function Get-ConfigurationPathEvidence",
    'Join-Path $InstalledApp.DirectoryName "backend.env"',
    "$SidecarConfigPath -and",
    "$SidecarConfigPath",
    "$UserConfigPath",
  ]);
  assert.match(acceptanceSource, /-not \$After\.UserConfigExists -and -not \$After\.SidecarConfigExists/);
});

test("missing or skipped manual acceptance evidence cannot produce approval", () => {
  assert.match(
    acceptanceSource,
    /if \(\$NonInteractive\) \{\s*Add-Result \$Area "Pending" \$Prompt\s*return/s,
  );
  assert.match(
    acceptanceSource,
    /default \{ Add-Result \$Area "Pending" \$Prompt \}/,
  );
  assert.match(
    acceptanceSource,
    /\$Approval = if \(\$FailureCount -eq 0 -and \$PendingCount -eq 0\) \{ "APPROVED" \} else \{ "NOT APPROVED" \}/,
  );
});

test(
  "PowerShell accepts the packaged acceptance script syntax without executing it",
  { skip: process.platform !== "win32" },
  () => {
    const parserCommand = [
      "$tokens = $null",
      "$errors = $null",
      "[System.Management.Automation.Language.Parser]::ParseFile($env:LIGHTHOUSEPM_ACCEPTANCE_SCRIPT, [ref]$tokens, [ref]$errors) | Out-Null",
      'if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_.Message }; exit 1 }',
    ].join("; ");
    const result = spawnSync("powershell.exe", ["-NoProfile", "-Command", parserCommand], {
      encoding: "utf8",
      env: {
        ...process.env,
        LIGHTHOUSEPM_ACCEPTANCE_SCRIPT: ACCEPTANCE_SCRIPT_PATH,
      },
    });

    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  },
);
