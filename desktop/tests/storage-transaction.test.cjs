const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  JOURNAL_FILENAME,
  TARGET_LOCATION_APPLICATION_SIDECAR,
  createRecoveryJournal,
  transitionRecoveryJournal,
  validateRecoveryJournal,
} = require("../src/storage-recovery.cjs");
const {
  StorageTransactionError,
  applyFileReplacementPlan,
  recoverInterruptedStorageOperation,
  replaceFileAtomically,
  runStorageTransaction,
} = require("../src/storage-transaction.cjs");

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "lighthouse-transaction-test-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function writeFile(filePath, contents) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, contents);
  return filePath;
}

function baseOptions(root, overrides = {}) {
  const databasePath = writeFile(path.join(root, "active", "data", "lighthouse.db"), "old database");
  const events = [];
  return {
    databasePath,
    events,
    options: {
      operation: "restore",
      operationId: "restore-operation",
      operationLabel: "Restore",
      recoveryRoot: path.join(root, "recovery"),
      activePaths: [{ relativePath: "data/lighthouse.db", activePath: databasePath }],
      applyChanges: async () => {
        events.push("apply");
        fs.writeFileSync(databasePath, "new database");
      },
      resolveActivePath: () => databasePath,
      startBackend: async () => events.push("start"),
      stopBackend: async () => events.push("stop"),
      verifyState: async () => events.push("verify"),
      ...overrides,
    },
  };
}

test("commits a verified storage transaction and removes recovery evidence", async (t) => {
  const root = temporaryDirectory(t);
  const { databasePath, events, options } = baseOptions(root);
  const untouchedConfigPath = writeFile(path.join(root, "active", "backend.env"), "untouched config");

  await runStorageTransaction(options);

  assert.equal(fs.readFileSync(databasePath, "utf8"), "new database");
  assert.equal(fs.readFileSync(untouchedConfigPath, "utf8"), "untouched config");
  assert.deepEqual(events, ["stop", "apply", "start", "verify"]);
  assert.deepEqual(fs.readdirSync(options.recoveryRoot), []);
});

test("unconfirmed shutdown aborts before snapshot or mutation", async (t) => {
  const root = temporaryDirectory(t);
  const { databasePath, events, options } = baseOptions(root, {
    stopBackend: async () => {
      events.push("stop");
      throw new Error("still running");
    },
  });

  await assert.rejects(
    runStorageTransaction(options),
    (error) =>
      error instanceof StorageTransactionError &&
      error.rule === "shutdown_unconfirmed" &&
      error.previousStateRestored === false,
  );
  assert.equal(fs.readFileSync(databasePath, "utf8"), "old database");
  assert.equal(fs.existsSync(options.recoveryRoot), false);
  assert.deepEqual(events, ["stop"]);
});

test("snapshot failure restarts and verifies the unchanged backend", async (t) => {
  const root = temporaryDirectory(t);
  const { databasePath, events, options } = baseOptions(root, {
    activePaths: [{ relativePath: "logs", activePath: path.join(root, "active", "logs") }],
  });

  await assert.rejects(
    runStorageTransaction(options),
    (error) =>
      error instanceof StorageTransactionError &&
      error.rule === "snapshot_failed" &&
      error.message === "Restore failed before active files changed; previous state remains unchanged.",
  );
  assert.equal(fs.readFileSync(databasePath, "utf8"), "old database");
  assert.deepEqual(events, ["stop", "start", "verify"]);
  assert.deepEqual(fs.readdirSync(options.recoveryRoot), []);
});

test("unfinished recovery fails closed before backend shutdown", async (t) => {
  const root = temporaryDirectory(t);
  const { databasePath, events, options } = baseOptions(root);
  createRecoveryJournal(options.recoveryRoot, {
    operationId: "existing-operation",
    operation: "restore",
    activePaths: [{ relativePath: "data/lighthouse.db", activePath: databasePath }],
  });

  await assert.rejects(
    runStorageTransaction(options),
    (error) =>
      error instanceof StorageTransactionError &&
      error.rule === "recovery_pending" &&
      error.recoveryRequired === true,
  );
  assert.deepEqual(events, []);
  assert.equal(fs.readFileSync(databasePath, "utf8"), "old database");
});

for (const failureBoundary of ["database-set-delete", "database", "config", "token"]) {
  test(`restores every original path after ${failureBoundary} replacement failure`, async (t) => {
    const root = temporaryDirectory(t);
    const activeRoot = path.join(root, "active");
    const pathMap = new Map([
      ["data/lighthouse.db", writeFile(path.join(activeRoot, "data", "lighthouse.db"), "old database")],
      ["data/lighthouse.db-wal", writeFile(path.join(activeRoot, "data", "lighthouse.db-wal"), "old wal")],
      ["data/lighthouse.db-shm", writeFile(path.join(activeRoot, "data", "lighthouse.db-shm"), "old shm")],
      ["backend.env", writeFile(path.join(activeRoot, "backend.env"), "old config")],
      ["secrets/jira-token.bin", writeFile(path.join(activeRoot, "secrets", "jira-token.bin"), "old token")],
    ]);
    const original = Object.fromEntries(
      [...pathMap].map(([relativePath, activePath]) => [relativePath, fs.readFileSync(activePath, "utf8")]),
    );
    let startCalls = 0;
    const mutationSteps = [
      ["database-set-delete", () => {
        fs.rmSync(pathMap.get("data/lighthouse.db"));
        fs.rmSync(pathMap.get("data/lighthouse.db-wal"));
        fs.rmSync(pathMap.get("data/lighthouse.db-shm"));
      }],
      ["database", () => writeFile(pathMap.get("data/lighthouse.db"), "new database")],
      ["config", () => fs.writeFileSync(pathMap.get("backend.env"), "new config")],
      ["token", () => fs.writeFileSync(pathMap.get("secrets/jira-token.bin"), "new token")],
    ];

    await assert.rejects(
      runStorageTransaction({
        operation: "restore",
        operationId: `failure-${failureBoundary}`,
        operationLabel: "Restore",
        recoveryRoot: path.join(root, "recovery"),
        activePaths: [...pathMap].map(([relativePath, activePath]) => ({ relativePath, activePath })),
        applyChanges: async () => {
          for (const [step, mutate] of mutationSteps) {
            mutate();
            if (step === failureBoundary) {
              throw new Error(`failed after ${step}`);
            }
          }
        },
        resolveActivePath: (relativePath) => pathMap.get(relativePath),
        startBackend: async () => {
          startCalls += 1;
        },
        stopBackend: async () => {},
        verifyState: async () => {},
      }),
      (error) =>
        error instanceof StorageTransactionError &&
        error.previousStateRestored === true &&
        error.message === `Restore failed; previous state restored. Cause: failed after ${failureBoundary}`,
    );

    for (const [relativePath, activePath] of pathMap) {
      assert.equal(fs.readFileSync(activePath, "utf8"), original[relativePath]);
    }
    assert.equal(startCalls, 1);
    assert.deepEqual(fs.readdirSync(path.join(root, "recovery")), []);
  });
}

test("restart failure after replacement rolls back and verifies the previous backend", async (t) => {
  const root = temporaryDirectory(t);
  let startCalls = 0;
  const { databasePath, events, options } = baseOptions(root, {
    startBackend: async () => {
      startCalls += 1;
      events.push(`start-${startCalls}`);
      if (startCalls === 1) {
        throw new Error("new backend failed");
      }
    },
  });

  await assert.rejects(
    runStorageTransaction(options),
    (error) => error instanceof StorageTransactionError && error.previousStateRestored === true,
  );
  assert.equal(fs.readFileSync(databasePath, "utf8"), "old database");
  assert.deepEqual(events, ["stop", "apply", "start-1", "stop", "start-2", "verify"]);
});

test("post-restart verification failure rolls back and verifies the previous backend", async (t) => {
  const root = temporaryDirectory(t);
  let verifyCalls = 0;
  const { databasePath, events, options } = baseOptions(root, {
    verifyState: async () => {
      verifyCalls += 1;
      events.push(`verify-${verifyCalls}`);
      if (verifyCalls === 1) {
        throw new Error("release API invalid");
      }
    },
  });

  await assert.rejects(
    runStorageTransaction(options),
    (error) => error instanceof StorageTransactionError && error.previousStateRestored === true,
  );
  assert.equal(fs.readFileSync(databasePath, "utf8"), "old database");
  assert.deepEqual(events, ["stop", "apply", "start", "verify-1", "stop", "start", "verify-2"]);
});

test("rollback-copy failure preserves a rolling-back journal and diagnostics", async (t) => {
  const root = temporaryDirectory(t);
  const { options } = baseOptions(root, {
    applyChanges: async () => {
      throw new Error("replacement failed");
    },
    resolveActivePath: () => {
      throw new Error("rollback destination unavailable");
    },
  });

  let failure;
  await assert.rejects(runStorageTransaction(options), (error) => {
    failure = error;
    return error instanceof StorageTransactionError && error.rule === "rollback_copy";
  });
  assert.equal(failure.recoveryRequired, true);
  const recovered = validateRecoveryJournal(failure.recoveryPath);
  assert.equal(recovered.journal.state, "rolling_back");
  const diagnostic = JSON.parse(fs.readFileSync(path.join(failure.recoveryPath, "failure.json"), "utf8"));
  assert.equal(diagnostic.rule, "rollback_copy");
});

test("rollback-restart failure preserves restored files and rollback-applied state", async (t) => {
  const root = temporaryDirectory(t);
  const { databasePath, options } = baseOptions(root, {
    applyChanges: async () => {
      fs.writeFileSync(databasePath, "new database");
      throw new Error("replacement failed");
    },
    startBackend: async () => {
      throw new Error("old backend failed");
    },
  });

  let failure;
  await assert.rejects(runStorageTransaction(options), (error) => {
    failure = error;
    return error instanceof StorageTransactionError && error.rule === "rollback_restart";
  });
  assert.equal(fs.readFileSync(databasePath, "utf8"), "old database");
  assert.equal(validateRecoveryJournal(failure.recoveryPath).journal.state, "rollback_applied");
  const diagnostic = JSON.parse(fs.readFileSync(path.join(failure.recoveryPath, "failure.json"), "utf8"));
  assert.equal(diagnostic.rule, "rollback_restart");
});

test("file replacement plan removes stale companions and atomically publishes exact payloads", (t) => {
  const root = temporaryDirectory(t);
  const activeDatabase = writeFile(path.join(root, "active", "data", "lighthouse.db"), "old database");
  const activeWal = writeFile(`${activeDatabase}-wal`, "stale wal");
  const activeShm = writeFile(`${activeDatabase}-shm`, "stale shm");
  const activeConfig = writeFile(path.join(root, "active", "backend.env"), "old config");
  const backupDatabase = writeFile(path.join(root, "backup", "data", "lighthouse.db"), "backup database");
  const backupConfig = writeFile(path.join(root, "backup", "backend.env"), "backup config");

  applyFileReplacementPlan({
    deletePaths: [activeDatabase, activeWal, activeShm],
    replacements: [
      { sourcePath: backupDatabase, targetPath: activeDatabase },
      { sourcePath: backupConfig, targetPath: activeConfig },
    ],
  });

  assert.equal(fs.readFileSync(activeDatabase, "utf8"), "backup database");
  assert.equal(fs.existsSync(activeWal), false);
  assert.equal(fs.existsSync(activeShm), false);
  assert.equal(fs.readFileSync(activeConfig, "utf8"), "backup config");
  assert.equal(
    fs.readdirSync(path.dirname(activeDatabase)).some((name) => name.endsWith(".restore.tmp")),
    false,
  );
});

test("atomic replacement leaves an existing target unchanged when its source is missing", (t) => {
  const root = temporaryDirectory(t);
  const targetPath = writeFile(path.join(root, "active", "backend.env"), "old config");

  assert.throws(
    () => replaceFileAtomically(path.join(root, "missing.env"), targetPath),
    /Replacement source is missing/,
  );
  assert.equal(fs.readFileSync(targetPath, "utf8"), "old config");
});

test("Clear Data commits an empty fresh database while retaining settings, logs, and migration backups", async (t) => {
  const root = temporaryDirectory(t);
  const activeRoot = path.join(root, "active");
  const databasePath = writeFile(path.join(activeRoot, "data", "lighthouse.db"), "old database");
  const walPath = writeFile(`${databasePath}-wal`, "old wal");
  const shmPath = writeFile(`${databasePath}-shm`, "old shm");
  const migrationBackupPath = writeFile(`${databasePath}.pre-20260720_0017.bak`, "migration backup");
  const configPath = writeFile(path.join(activeRoot, "backend.env"), "configured=true");
  const tokenPath = writeFile(path.join(activeRoot, "secrets", "jira-token.bin"), "encrypted token");
  const logPath = writeFile(path.join(activeRoot, "logs", "backend.log"), "existing log");
  const pathMap = new Map([
    ["data/lighthouse.db", databasePath],
    ["data/lighthouse.db-wal", walPath],
    ["data/lighthouse.db-shm", shmPath],
  ]);

  await runStorageTransaction({
    operation: "clear-data",
    operationId: "clear-operation",
    operationLabel: "Clear Data",
    recoveryRoot: path.join(activeRoot, "recovery"),
    activePaths: [...pathMap].map(([relativePath, activePath]) => ({ relativePath, activePath })),
    applyChanges: async () => {
      for (const activePath of pathMap.values()) {
        fs.rmSync(activePath, { force: true });
      }
    },
    resolveActivePath: (relativePath) => pathMap.get(relativePath),
    stopBackend: async () => {},
    startBackend: async () => writeFile(databasePath, "fresh current-head database"),
    verifyState: async () => {
      assert.equal(fs.readFileSync(databasePath, "utf8"), "fresh current-head database");
      assert.equal(fs.existsSync(walPath), false);
      assert.equal(fs.existsSync(shmPath), false);
    },
  });

  assert.equal(fs.readFileSync(configPath, "utf8"), "configured=true");
  assert.equal(fs.readFileSync(tokenPath, "utf8"), "encrypted token");
  assert.equal(fs.readFileSync(logPath, "utf8"), "existing log");
  assert.equal(fs.readFileSync(migrationBackupPath, "utf8"), "migration backup");
});

test("Clear Data failure restores the complete original database set", async (t) => {
  const root = temporaryDirectory(t);
  const databasePath = writeFile(path.join(root, "active", "data", "lighthouse.db"), "old database");
  const pathMap = new Map([
    ["data/lighthouse.db", databasePath],
    ["data/lighthouse.db-wal", writeFile(`${databasePath}-wal`, "old wal")],
    ["data/lighthouse.db-shm", writeFile(`${databasePath}-shm`, "old shm")],
  ]);

  await assert.rejects(
    runStorageTransaction({
      operation: "clear-data",
      operationId: "clear-failure",
      operationLabel: "Clear Data",
      recoveryRoot: path.join(root, "recovery"),
      activePaths: [...pathMap].map(([relativePath, activePath]) => ({ relativePath, activePath })),
      applyChanges: async () => {
        for (const activePath of pathMap.values()) {
          fs.rmSync(activePath, { force: true });
        }
        throw new Error("database deletion failed");
      },
      resolveActivePath: (relativePath) => pathMap.get(relativePath),
      stopBackend: async () => {},
      startBackend: async () => {},
      verifyState: async () => {},
    }),
    (error) =>
      error instanceof StorageTransactionError &&
      error.message === "Clear Data failed; previous state restored. Cause: database deletion failed",
  );

  assert.equal(fs.readFileSync(pathMap.get("data/lighthouse.db"), "utf8"), "old database");
  assert.equal(fs.readFileSync(pathMap.get("data/lighthouse.db-wal"), "utf8"), "old wal");
  assert.equal(fs.readFileSync(pathMap.get("data/lighthouse.db-shm"), "utf8"), "old shm");
});

test("Factory Reset commits first-run files while retaining automatic migration backups", async (t) => {
  const root = temporaryDirectory(t);
  const activeRoot = path.join(root, "active");
  const databasePath = writeFile(path.join(activeRoot, "data", "lighthouse.db"), "old database");
  const migrationBackupPath = writeFile(`${databasePath}.pre-20260720_0017.bak`, "migration backup");
  const configPath = writeFile(path.join(activeRoot, "backend.env"), "configured=true");
  const tokenPath = writeFile(path.join(activeRoot, "secrets", "jira-token.bin"), "encrypted token");
  const logsPath = path.join(activeRoot, "logs");
  writeFile(path.join(logsPath, "backend.log"), "old log");
  const rootPaths = new Map([
    ["data/lighthouse.db", databasePath],
    ["data/lighthouse.db-wal", `${databasePath}-wal`],
    ["data/lighthouse.db-shm", `${databasePath}-shm`],
    ["backend.env", configPath],
    ["secrets/jira-token.bin", tokenPath],
    ["logs", logsPath],
  ]);
  const resolveActivePath = (relativePath) =>
    rootPaths.get(relativePath) ?? path.join(logsPath, ...relativePath.slice("logs/".length).split("/"));

  await runStorageTransaction({
    operation: "factory-reset",
    operationId: "factory-operation",
    operationLabel: "Factory Reset",
    recoveryRoot: path.join(activeRoot, "recovery"),
    activePaths: [...rootPaths].map(([relativePath, activePath]) => ({ relativePath, activePath })),
    applyChanges: async () => {
      for (const activePath of rootPaths.values()) {
        fs.rmSync(activePath, { recursive: true, force: true });
      }
    },
    resolveActivePath,
    stopBackend: async () => {},
    startBackend: async () => {
      writeFile(databasePath, "fresh current-head database");
      writeFile(path.join(logsPath, "backend.log"), "new startup log");
    },
    verifyState: async () => {
      assert.equal(fs.existsSync(configPath), false);
      assert.equal(fs.existsSync(tokenPath), false);
      assert.equal(fs.readFileSync(databasePath, "utf8"), "fresh current-head database");
    },
  });

  assert.equal(fs.readFileSync(path.join(logsPath, "backend.log"), "utf8"), "new startup log");
  assert.equal(fs.readFileSync(migrationBackupPath, "utf8"), "migration backup");
});

test("Factory Reset restart failure restores all prior files and preserves separate diagnostics", async (t) => {
  const root = temporaryDirectory(t);
  const activeRoot = path.join(root, "active");
  const databasePath = writeFile(path.join(activeRoot, "data", "lighthouse.db"), "old database");
  const migrationBackupPath = writeFile(`${databasePath}.pre-20260720_0017.bak`, "migration backup");
  const configPath = writeFile(path.join(activeRoot, "backend.env"), "old config");
  const tokenPath = writeFile(path.join(activeRoot, "secrets", "jira-token.bin"), "old token");
  const logsPath = path.join(activeRoot, "logs");
  const oldLogPath = writeFile(path.join(logsPath, "backend.log"), "old log");
  const rootPaths = new Map([
    ["data/lighthouse.db", databasePath],
    ["data/lighthouse.db-wal", `${databasePath}-wal`],
    ["data/lighthouse.db-shm", `${databasePath}-shm`],
    ["backend.env", configPath],
    ["secrets/jira-token.bin", tokenPath],
    ["logs", logsPath],
  ]);
  const resolveActivePath = (relativePath) =>
    rootPaths.get(relativePath) ?? path.join(logsPath, ...relativePath.slice("logs/".length).split("/"));
  let startCalls = 0;
  const diagnosticPrefix = "factory-reset-factory-failure-failure";

  await assert.rejects(
    runStorageTransaction({
      operation: "factory-reset",
      operationId: "factory-failure",
      operationLabel: "Factory Reset",
      recoveryRoot: path.join(activeRoot, "recovery"),
      activePaths: [...rootPaths].map(([relativePath, activePath]) => ({ relativePath, activePath })),
      applyChanges: async () => {
        for (const activePath of rootPaths.values()) {
          fs.rmSync(activePath, { recursive: true, force: true });
        }
      },
      resolveActivePath,
      stopBackend: async () => {},
      startBackend: async () => {
        startCalls += 1;
        if (startCalls === 1) {
          writeFile(path.join(logsPath, "backend.log"), "failed startup log");
          throw new Error("first-run backend failed");
        }
      },
      verifyState: async () => {},
      captureOperationDiagnostic: async (journalDirectory) => {
        replaceFileAtomically(
          path.join(logsPath, "backend.log"),
          path.join(journalDirectory, "failed-backend.log"),
        );
      },
      preserveRollbackDiagnostic: async (journalDirectory) => {
        replaceFileAtomically(
          path.join(journalDirectory, "failure.json"),
          path.join(logsPath, `${diagnosticPrefix}.json`),
        );
        replaceFileAtomically(
          path.join(journalDirectory, "failed-backend.log"),
          path.join(logsPath, `${diagnosticPrefix}.log`),
        );
      },
    }),
    (error) =>
      error instanceof StorageTransactionError &&
      error.message === "Factory Reset failed; previous state restored. Cause: first-run backend failed",
  );

  assert.equal(fs.readFileSync(databasePath, "utf8"), "old database");
  assert.equal(fs.readFileSync(configPath, "utf8"), "old config");
  assert.equal(fs.readFileSync(tokenPath, "utf8"), "old token");
  assert.equal(fs.readFileSync(oldLogPath, "utf8"), "old log");
  assert.equal(fs.readFileSync(path.join(logsPath, `${diagnosticPrefix}.log`), "utf8"), "failed startup log");
  assert.equal(
    JSON.parse(fs.readFileSync(path.join(logsPath, `${diagnosticPrefix}.json`), "utf8")).rule,
    "operation_failure",
  );
  assert.equal(fs.readFileSync(migrationBackupPath, "utf8"), "migration backup");
});

const INTERRUPTED_STATE_TRANSITIONS = {
  prepared: [],
  mutating: ["mutating"],
  applied: ["mutating", "applied"],
  verifying: ["mutating", "applied", "verifying"],
  rolling_back: ["mutating", "rolling_back"],
  rollback_applied: ["mutating", "rolling_back", "rollback_applied"],
};

for (const [interruptedState, transitions] of Object.entries(INTERRUPTED_STATE_TRANSITIONS)) {
  test(`startup recovery restores and verifies an operation interrupted in ${interruptedState}`, async (t) => {
    const root = temporaryDirectory(t);
    const recoveryRoot = path.join(root, "recovery");
    const databasePath = writeFile(path.join(root, "active", "data", "lighthouse.db"), "old database");
    let recovery = createRecoveryJournal(recoveryRoot, {
      operationId: `interrupted-${interruptedState}`,
      operation: "clear-data",
      activePaths: [{ relativePath: "data/lighthouse.db", activePath: databasePath }],
    });
    for (const state of transitions) {
      recovery = transitionRecoveryJournal(recovery.journalDirectory, state);
    }
    fs.writeFileSync(databasePath, "interrupted database");
    const events = [];

    const result = await recoverInterruptedStorageOperation({
      recoveryRoot,
      resolveActivePath: () => databasePath,
      startBackend: async () => events.push("start"),
      stopBackend: async () => events.push("stop"),
      verifyState: async () => events.push("verify"),
    });

    assert.deepEqual(result, {
      backendStarted: true,
      recoveredOperationId: `interrupted-${interruptedState}`,
    });
    assert.equal(fs.readFileSync(databasePath, "utf8"), "old database");
    assert.deepEqual(events, ["start", "verify"]);
    assert.deepEqual(fs.readdirSync(recoveryRoot), []);
  });
}

test("startup recovery removes originally absent files without using migration backups", async (t) => {
  const root = temporaryDirectory(t);
  const activeRoot = path.join(root, "active");
  const recoveryRoot = path.join(root, "recovery");
  const databasePath = writeFile(path.join(activeRoot, "data", "lighthouse.db"), "old database");
  const walPath = `${databasePath}-wal`;
  const migrationBackupPath = writeFile(`${databasePath}.pre-20260720_0017.bak`, "migration backup");
  const recovery = createRecoveryJournal(recoveryRoot, {
    operationId: "interrupted-absence",
    operation: "clear-data",
    activePaths: [
      { relativePath: "data/lighthouse.db", activePath: databasePath },
      { relativePath: "data/lighthouse.db-wal", activePath: walPath },
    ],
  });
  transitionRecoveryJournal(recovery.journalDirectory, "mutating");
  fs.writeFileSync(databasePath, "new database");
  writeFile(walPath, "new wal");

  await recoverInterruptedStorageOperation({
    recoveryRoot,
    resolveActivePath: (relativePath) =>
      relativePath === "data/lighthouse.db" ? databasePath : walPath,
    startBackend: async () => {},
    stopBackend: async () => {},
    verifyState: async () => {},
  });

  assert.equal(fs.readFileSync(databasePath, "utf8"), "old database");
  assert.equal(fs.existsSync(walPath), false);
  assert.equal(fs.readFileSync(migrationBackupPath, "utf8"), "migration backup");
});

test("startup recovery resolves sidecar configuration from logical journal metadata", async (t) => {
  const root = temporaryDirectory(t);
  const recoveryRoot = path.join(root, "recovery");
  const sidecarConfigPath = writeFile(path.join(root, "application", "backend.env"), "old config");
  const userConfigPath = path.join(root, "user-data", "backend.env");
  const recovery = createRecoveryJournal(recoveryRoot, {
    operationId: "interrupted-sidecar",
    operation: "restore",
    activePaths: [
      {
        relativePath: "backend.env",
        activePath: sidecarConfigPath,
        targetLocation: TARGET_LOCATION_APPLICATION_SIDECAR,
      },
    ],
  });
  transitionRecoveryJournal(recovery.journalDirectory, "mutating");
  fs.writeFileSync(sidecarConfigPath, "new config");
  const locations = [];

  await recoverInterruptedStorageOperation({
    recoveryRoot,
    resolveActivePath: (relativePath, targetLocation) => {
      locations.push([relativePath, targetLocation]);
      return targetLocation === TARGET_LOCATION_APPLICATION_SIDECAR
        ? sidecarConfigPath
        : userConfigPath;
    },
    startBackend: async () => {},
    stopBackend: async () => {},
    verifyState: async () => {},
  });

  assert.deepEqual(locations, [["backend.env", TARGET_LOCATION_APPLICATION_SIDECAR]]);
  assert.equal(fs.readFileSync(sidecarConfigPath, "utf8"), "old config");
  assert.equal(fs.existsSync(userConfigPath), false);
});

for (const terminalState of ["committed", "rolled_back"]) {
  test(`startup recovery cleans a terminal ${terminalState} journal without starting the backend`, async (t) => {
    const root = temporaryDirectory(t);
    const recoveryRoot = path.join(root, "recovery");
    const databasePath = writeFile(path.join(root, "active.db"), "old database");
    let recovery = createRecoveryJournal(recoveryRoot, {
      operationId: `terminal-${terminalState}`,
      operation: "clear-data",
      activePaths: [{ relativePath: "data/lighthouse.db", activePath: databasePath }],
    });
    const transitions =
      terminalState === "committed"
        ? ["mutating", "applied", "verifying", "committed"]
        : ["mutating", "rolling_back", "rollback_applied", "rolled_back"];
    for (const state of transitions) {
      recovery = transitionRecoveryJournal(recovery.journalDirectory, state);
    }
    const events = [];

    const result = await recoverInterruptedStorageOperation({
      recoveryRoot,
      resolveActivePath: () => databasePath,
      startBackend: async () => events.push("start"),
      stopBackend: async () => events.push("stop"),
      verifyState: async () => events.push("verify"),
    });

    assert.deepEqual(result, {
      backendStarted: false,
      recoveredOperationId: `terminal-${terminalState}`,
    });
    assert.deepEqual(events, []);
    assert.deepEqual(fs.readdirSync(recoveryRoot), []);
  });
}

test("startup recovery fails closed on invalid journal state with an exact actionable error", async (t) => {
  const root = temporaryDirectory(t);
  const recoveryRoot = path.join(root, "recovery");
  const journalDirectory = path.join(recoveryRoot, "broken-operation");
  fs.mkdirSync(journalDirectory, { recursive: true });
  fs.writeFileSync(path.join(journalDirectory, JOURNAL_FILENAME), "{invalid-json");
  const events = [];

  await assert.rejects(
    recoverInterruptedStorageOperation({
      recoveryRoot,
      resolveActivePath: () => path.join(root, "active.db"),
      startBackend: async () => events.push("start"),
      stopBackend: async () => events.push("stop"),
      verifyState: async () => events.push("verify"),
    }),
    (error) =>
      error instanceof StorageTransactionError &&
      error.rule === "startup_recovery_invalid" &&
      error.recoveryRequired === true &&
      error.recoveryPath === recoveryRoot &&
      error.message ===
        `Startup recovery could not validate recovery state. Recovery is preserved at ${recoveryRoot}.`,
  );
  assert.deepEqual(events, []);
  assert.equal(fs.existsSync(journalDirectory), true);
});

test("startup recovery rejects missing, duplicate, and corrupt recovery evidence before backend start", async (t) => {
  const root = temporaryDirectory(t);
  const scenarios = [];

  const missingRoot = path.join(root, "missing-journal", "recovery");
  fs.mkdirSync(path.join(missingRoot, "operation"), { recursive: true });
  scenarios.push(missingRoot);

  const duplicateRoot = path.join(root, "duplicate-journals", "recovery");
  fs.mkdirSync(path.join(duplicateRoot, "operation-1"), { recursive: true });
  fs.mkdirSync(path.join(duplicateRoot, "operation-2"), { recursive: true });
  scenarios.push(duplicateRoot);

  const corruptRoot = path.join(root, "corrupt-snapshot", "recovery");
  const corruptDatabasePath = writeFile(
    path.join(root, "corrupt-snapshot", "active.db"),
    "old database",
  );
  const corruptRecovery = createRecoveryJournal(corruptRoot, {
    operationId: "corrupt-operation",
    operation: "clear-data",
    activePaths: [{ relativePath: "data/lighthouse.db", activePath: corruptDatabasePath }],
  });
  fs.appendFileSync(
    path.join(corruptRecovery.journalDirectory, "snapshot", "data", "lighthouse.db"),
    "corrupt",
  );
  scenarios.push(corruptRoot);

  for (const recoveryRoot of scenarios) {
    let backendStarted = false;
    await assert.rejects(
      recoverInterruptedStorageOperation({
        recoveryRoot,
        resolveActivePath: () => path.join(root, "active.db"),
        startBackend: async () => {
          backendStarted = true;
        },
        stopBackend: async () => {},
        verifyState: async () => {},
      }),
      (error) =>
        error instanceof StorageTransactionError &&
        error.rule === "startup_recovery_invalid" &&
        error.recoveryPath === recoveryRoot,
    );
    assert.equal(backendStarted, false);
    assert.equal(fs.existsSync(recoveryRoot), true);
  }
});

test("startup recovery preserves a rolling-back journal when file restoration fails", async (t) => {
  const root = temporaryDirectory(t);
  const recoveryRoot = path.join(root, "recovery");
  const databasePath = writeFile(path.join(root, "active.db"), "old database");
  const recovery = createRecoveryJournal(recoveryRoot, {
    operationId: "restore-copy-failure",
    operation: "clear-data",
    activePaths: [{ relativePath: "data/lighthouse.db", activePath: databasePath }],
  });
  fs.writeFileSync(databasePath, "new database");

  await assert.rejects(
    recoverInterruptedStorageOperation({
      recoveryRoot,
      resolveActivePath: () => {
        throw new Error("destination unavailable");
      },
      startBackend: async () => assert.fail("backend must not start"),
      stopBackend: async () => {},
      verifyState: async () => assert.fail("backend must not be verified"),
    }),
    (error) =>
      error instanceof StorageTransactionError &&
      error.rule === "startup_recovery_restore" &&
      error.message ===
        `Startup recovery could not restore the previous files. Recovery is preserved at ${recovery.journalDirectory}.`,
  );
  assert.equal(validateRecoveryJournal(recovery.journalDirectory).journal.state, "rolling_back");
  assert.equal(
    JSON.parse(fs.readFileSync(path.join(recovery.journalDirectory, "failure.json"), "utf8")).rule,
    "startup_recovery_restore",
  );
});

test("startup recovery stops the backend and preserves rollback-applied evidence on readiness failure", async (t) => {
  const root = temporaryDirectory(t);
  const recoveryRoot = path.join(root, "recovery");
  const databasePath = writeFile(path.join(root, "active.db"), "old database");
  const recovery = createRecoveryJournal(recoveryRoot, {
    operationId: "restore-backend-failure",
    operation: "clear-data",
    activePaths: [{ relativePath: "data/lighthouse.db", activePath: databasePath }],
  });
  fs.writeFileSync(databasePath, "new database");
  const events = [];

  await assert.rejects(
    recoverInterruptedStorageOperation({
      recoveryRoot,
      resolveActivePath: () => databasePath,
      startBackend: async () => events.push("start"),
      stopBackend: async () => events.push("stop"),
      verifyState: async () => {
        events.push("verify");
        throw new Error("Releases API unavailable");
      },
    }),
    (error) =>
      error instanceof StorageTransactionError &&
      error.rule === "startup_recovery_restart" &&
      error.message ===
        `Startup recovery restored the previous files, but the previous backend did not become ready. Recovery is preserved at ${recovery.journalDirectory}.`,
  );
  assert.equal(fs.readFileSync(databasePath, "utf8"), "old database");
  assert.deepEqual(events, ["start", "verify", "stop"]);
  assert.equal(validateRecoveryJournal(recovery.journalDirectory).journal.state, "rollback_applied");
  assert.equal(
    JSON.parse(fs.readFileSync(path.join(recovery.journalDirectory, "failure.json"), "utf8")).rule,
    "startup_recovery_restart",
  );
});
