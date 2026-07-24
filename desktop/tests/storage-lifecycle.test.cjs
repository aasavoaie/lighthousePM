const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  CONFIG_PATH,
  DATABASE_PATH,
  SettingsBackupValidationError,
  TOKEN_PATH,
  publishValidatedSettingsBackup,
  validateSettingsBackup,
} = require("../src/backup.cjs");
const {
  applyFileReplacementPlan,
  runStorageTransaction,
} = require("../src/storage-transaction.cjs");

const REPRESENTATIVE_PRIOR_REVISION = "20260717_0016";
const DATABASE_WAL_PATH = `${DATABASE_PATH}-wal`;
const DATABASE_SHM_PATH = `${DATABASE_PATH}-shm`;

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "lighthouse-lifecycle-test-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function writeFile(filePath, contents) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, contents);
  return filePath;
}

function payloadPath(root, relativePath) {
  return path.join(root, ...relativePath.split("/"));
}

function databaseValidation() {
  return {
    valid: true,
    source_revision: REPRESENTATIVE_PRIOR_REVISION,
    revision_kind: "alembic",
  };
}

function backupValidators() {
  return {
    validateDatabase: (databasePath) => {
      assert.match(fs.readFileSync(databasePath, "utf8"), /release=REL-42/);
      return databaseValidation();
    },
    validateConfig: (configPath) => {
      assert.equal(fs.readFileSync(configPath, "utf8"), "JIRA_SYNC_ENABLED=false\n");
      return { valid: true };
    },
    validateToken: (tokenPath) => {
      assert.equal(fs.readFileSync(tokenPath, "utf8"), "encrypted-token-from-backup");
      return { valid: true };
    },
  };
}

function publishBackupFromActiveState(backupDirectory, activePaths, relativePaths) {
  fs.mkdirSync(backupDirectory, { recursive: true });
  for (const relativePath of relativePaths) {
    const targetPath = payloadPath(backupDirectory, relativePath);
    fs.mkdirSync(path.dirname(targetPath), { recursive: true });
    fs.copyFileSync(activePaths.get(relativePath), targetPath);
  }
  publishValidatedSettingsBackup(
    backupDirectory,
    relativePaths,
    databaseValidation(),
    (candidateDirectory) => validateSettingsBackup(candidateDirectory, backupValidators()),
  );
}

const OPTIONAL_PAYLOAD_CASES = [
  { name: "database only", optionalPaths: [] },
  { name: "database and configuration", optionalPaths: [CONFIG_PATH] },
  { name: "database and token", optionalPaths: [TOKEN_PATH] },
  { name: "database, configuration, and token", optionalPaths: [CONFIG_PATH, TOKEN_PATH] },
];

for (const { name, optionalPaths } of OPTIONAL_PAYLOAD_CASES) {
  test(`isolated backup and restore lifecycle succeeds for ${name}`, async (t) => {
    const root = temporaryDirectory(t);
    const activeRoot = path.join(root, "user-data");
    const backupDirectory = path.join(root, "selected-backups", "lighthousepm-backup-test");
    const recoveryRoot = path.join(activeRoot, "recovery");
    assert.equal(activeRoot.startsWith(`${root}${path.sep}`), true);

    const activePaths = new Map([
      [
        DATABASE_PATH,
        writeFile(
          payloadPath(activeRoot, DATABASE_PATH),
          `revision=${REPRESENTATIVE_PRIOR_REVISION};release=REL-42;sprint=SPR-7`,
        ),
      ],
      [CONFIG_PATH, writeFile(payloadPath(activeRoot, CONFIG_PATH), "JIRA_SYNC_ENABLED=false\n")],
      [TOKEN_PATH, writeFile(payloadPath(activeRoot, TOKEN_PATH), "encrypted-token-from-backup")],
    ]);
    const backupRelativePaths = [DATABASE_PATH, ...optionalPaths];
    publishBackupFromActiveState(backupDirectory, activePaths, backupRelativePaths);

    fs.writeFileSync(activePaths.get(DATABASE_PATH), "release=CHANGED;sprint=CHANGED");
    const walPath = writeFile(payloadPath(activeRoot, DATABASE_WAL_PATH), "stale wal");
    const shmPath = writeFile(payloadPath(activeRoot, DATABASE_SHM_PATH), "stale shm");
    fs.writeFileSync(activePaths.get(CONFIG_PATH), "JIRA_SYNC_ENABLED=true\n");
    fs.writeFileSync(activePaths.get(TOKEN_PATH), "current-encrypted-token");

    const events = [];
    let backendRunning = true;
    const validatedBackup = validateSettingsBackup(backupDirectory, backupValidators());
    events.push("preflight");
    const recoveryPaths = new Map([
      [DATABASE_PATH, activePaths.get(DATABASE_PATH)],
      [DATABASE_WAL_PATH, walPath],
      [DATABASE_SHM_PATH, shmPath],
    ]);
    for (const relativePath of optionalPaths) {
      recoveryPaths.set(relativePath, activePaths.get(relativePath));
    }
    const deletePaths = [activePaths.get(DATABASE_PATH), walPath, shmPath];
    const replacements = backupRelativePaths.map((relativePath) => ({
      sourcePath: validatedBackup.payloadPaths[relativePath],
      targetPath: activePaths.get(relativePath),
    }));

    await runStorageTransaction({
      operation: "restore",
      operationId: `round-trip-${name.replace(/[^a-z]+/g, "-")}`,
      operationLabel: "Restore",
      recoveryRoot,
      activePaths: [...recoveryPaths].map(([relativePath, activePath]) => ({
        relativePath,
        activePath,
      })),
      applyChanges: async () => {
        events.push("apply");
        applyFileReplacementPlan({ deletePaths, replacements });
      },
      resolveActivePath: (relativePath) => {
        const activePath = recoveryPaths.get(relativePath);
        if (!activePath) {
          throw new Error(`Test recovery path is not mapped: ${relativePath}`);
        }
        return activePath;
      },
      stopBackend: async () => {
        events.push("stop");
        backendRunning = false;
      },
      startBackend: async () => {
        events.push("start");
        backendRunning = true;
      },
      verifyState: async () => {
        events.push("verify-public-api");
        assert.equal(backendRunning, true);
        const restoredDatabase = fs.readFileSync(activePaths.get(DATABASE_PATH), "utf8");
        assert.match(restoredDatabase, /release=REL-42/);
        assert.match(restoredDatabase, /sprint=SPR-7/);
      },
    });

    assert.deepEqual(events, ["preflight", "stop", "apply", "start", "verify-public-api"]);
    assert.equal(fs.existsSync(walPath), false);
    assert.equal(fs.existsSync(shmPath), false);
    assert.equal(
      fs.readFileSync(activePaths.get(CONFIG_PATH), "utf8"),
      optionalPaths.includes(CONFIG_PATH)
        ? "JIRA_SYNC_ENABLED=false\n"
        : "JIRA_SYNC_ENABLED=true\n",
    );
    assert.equal(
      fs.readFileSync(activePaths.get(TOKEN_PATH), "utf8"),
      optionalPaths.includes(TOKEN_PATH)
        ? "encrypted-token-from-backup"
        : "current-encrypted-token",
    );
    assert.deepEqual(fs.readdirSync(recoveryRoot), []);
  });
}

test("restore preflight failure keeps the backend running and active files unchanged", async (t) => {
  const root = temporaryDirectory(t);
  const activeRoot = path.join(root, "user-data");
  const backupDirectory = path.join(root, "selected-backups", "lighthousepm-backup-invalid");
  const activeDatabasePath = writeFile(
    payloadPath(activeRoot, DATABASE_PATH),
    "release=REL-42;backup=true",
  );
  const activeConfigPath = writeFile(
    payloadPath(activeRoot, CONFIG_PATH),
    "JIRA_SYNC_ENABLED=false\n",
  );
  const sourcePaths = new Map([
    [DATABASE_PATH, activeDatabasePath],
    [CONFIG_PATH, activeConfigPath],
  ]);
  publishBackupFromActiveState(backupDirectory, sourcePaths, [DATABASE_PATH, CONFIG_PATH]);
  fs.writeFileSync(activeDatabasePath, "release=ACTIVE;unchanged=true");
  fs.writeFileSync(activeConfigPath, "JIRA_SYNC_ENABLED=true\n");
  fs.appendFileSync(payloadPath(backupDirectory, CONFIG_PATH), "tampered=true\n");
  let backendRunning = true;
  const transactionEvents = [];

  const attemptRestore = async () => {
    const validatedBackup = validateSettingsBackup(backupDirectory, backupValidators());
    await runStorageTransaction({
      operation: "restore",
      operationId: "preflight-must-block-transaction",
      operationLabel: "Restore",
      recoveryRoot: path.join(activeRoot, "recovery"),
      activePaths: [{ relativePath: DATABASE_PATH, activePath: activeDatabasePath }],
      applyChanges: async () => transactionEvents.push("apply"),
      resolveActivePath: () => activeDatabasePath,
      stopBackend: async () => {
        backendRunning = false;
        transactionEvents.push("stop");
      },
      startBackend: async () => transactionEvents.push("start"),
      verifyState: async () => transactionEvents.push("verify"),
    });
    return validatedBackup;
  };

  await assert.rejects(
    attemptRestore(),
    (error) =>
      error instanceof SettingsBackupValidationError &&
      error.rule === "payload_size" &&
      error.message ===
        `Backup validation failed for ${path.resolve(backupDirectory)}: payload_size: size mismatch for ${CONFIG_PATH}`,
  );
  assert.equal(backendRunning, true);
  assert.deepEqual(transactionEvents, []);
  assert.equal(fs.readFileSync(activeDatabasePath, "utf8"), "release=ACTIVE;unchanged=true");
  assert.equal(fs.readFileSync(activeConfigPath, "utf8"), "JIRA_SYNC_ENABLED=true\n");
  assert.equal(fs.existsSync(path.join(activeRoot, "recovery")), false);
});
