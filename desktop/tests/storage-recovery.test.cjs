const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  JOURNAL_FILENAME,
  RECOVERY_VERSION,
  RecoveryJournalError,
  TARGET_LOCATION_APPLICATION_SIDECAR,
  TARGET_LOCATION_USER_DATA,
  createRecoveryJournal,
  inspectRecoveryRoot,
  removeCompletedRecoveryJournal,
  restoreRecoverySnapshot,
  transitionRecoveryJournal,
  validateRecoveryJournal,
  writeRecoveryDiagnostic,
} = require("../src/storage-recovery.cjs");

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "lighthouse-recovery-test-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function writeFile(filePath, contents) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, contents);
  return filePath;
}

function expectRule(rule) {
  return (error) => error instanceof RecoveryJournalError && error.rule === rule;
}

test("creates and validates a prepared recovery journal with file, directory, and absence evidence", (t) => {
  const root = temporaryDirectory(t);
  const activeRoot = path.join(root, "active");
  const recoveryRoot = path.join(root, "recovery");
  const databasePath = writeFile(path.join(activeRoot, "data", "lighthouse.db"), "database-state");
  const logsPath = path.join(activeRoot, "logs");
  writeFile(path.join(logsPath, "backend.log"), "first log");
  writeFile(path.join(logsPath, "archive", "backend.1.log"), "older log");

  const result = createRecoveryJournal(recoveryRoot, {
    operationId: "operation-1",
    operation: "factory-reset",
    now: "2026-07-21T10:00:00.000Z",
    activePaths: [
      { relativePath: "data/lighthouse.db", activePath: databasePath },
      { relativePath: "backend.env", activePath: path.join(activeRoot, "backend.env") },
      { relativePath: "logs", activePath: logsPath },
    ],
  });

  assert.equal(result.journal.version, RECOVERY_VERSION);
  assert.equal(result.journal.state, "prepared");
  assert.deepEqual(result.journal.targetLocations, {
    "backend.env": TARGET_LOCATION_USER_DATA,
    "data/lighthouse.db": TARGET_LOCATION_USER_DATA,
    logs: TARGET_LOCATION_USER_DATA,
  });
  assert.deepEqual(result.journal.paths["backend.env"], { present: false });
  assert.equal(result.journal.paths["data/lighthouse.db"].present, true);
  assert.equal(result.journal.paths["data/lighthouse.db"].sizeBytes, 14);
  assert.match(result.journal.paths["data/lighthouse.db"].sha256, /^[a-f0-9]{64}$/);
  assert.deepEqual(result.journal.paths.logs, { present: true, kind: "directory" });
  assert.equal(result.journal.paths["logs/archive/backend.1.log"].present, true);
  assert.equal(
    fs.readFileSync(path.join(result.journalDirectory, "snapshot", "logs", "backend.log"), "utf8"),
    "first log",
  );
  assert.deepEqual(inspectRecoveryRoot(recoveryRoot), result);
  assert.equal(
    fs.readdirSync(result.journalDirectory).some((name) => name.startsWith(".journal.json.")),
    false,
  );
});

test("publishes only valid forward state transitions and leaves no temporary journal", (t) => {
  const root = temporaryDirectory(t);
  const databasePath = writeFile(path.join(root, "active.db"), "old database");
  const created = createRecoveryJournal(path.join(root, "recovery"), {
    operationId: "operation-2",
    operation: "clear-data",
    now: "2026-07-21T10:00:00.000Z",
    activePaths: [{ relativePath: "data/lighthouse.db", activePath: databasePath }],
  });

  const mutating = transitionRecoveryJournal(
    created.journalDirectory,
    "mutating",
    "2026-07-21T10:00:01.000Z",
  );
  assert.equal(mutating.journal.state, "mutating");
  assert.equal(mutating.journal.lastTransitionAt, "2026-07-21T10:00:01.000Z");
  assert.throws(
    () => transitionRecoveryJournal(created.journalDirectory, "committed"),
    expectRule("state_transition"),
  );
  assert.throws(
    () => transitionRecoveryJournal(created.journalDirectory, "applied", "2026-07-21T09:59:59.000Z"),
    expectRule("timestamp"),
  );
  assert.equal(
    fs.readdirSync(created.journalDirectory).some((name) => name.startsWith(".journal.json.")),
    false,
  );
});

test("detects changed, missing, and linked snapshot payloads", (t) => {
  const root = temporaryDirectory(t);
  const databasePath = writeFile(path.join(root, "active.db"), "old database");
  const created = createRecoveryJournal(path.join(root, "recovery"), {
    operationId: "operation-3",
    operation: "restore",
    activePaths: [{ relativePath: "data/lighthouse.db", activePath: databasePath }],
  });
  const snapshotPath = path.join(created.journalDirectory, "snapshot", "data", "lighthouse.db");

  fs.writeFileSync(snapshotPath, "bad database");
  assert.throws(() => validateRecoveryJournal(created.journalDirectory), expectRule("snapshot_sha256"));

  fs.writeFileSync(snapshotPath, "changed database");
  assert.throws(() => validateRecoveryJournal(created.journalDirectory), expectRule("snapshot_size"));

  fs.rmSync(snapshotPath);
  assert.throws(() => validateRecoveryJournal(created.journalDirectory), expectRule("snapshot_missing"));

  try {
    fs.symlinkSync(databasePath, snapshotPath);
  } catch {
    return;
  }
  assert.throws(() => validateRecoveryJournal(created.journalDirectory), expectRule("snapshot_type"));
});

test("rejects missing, malformed, and unsupported journals", (t) => {
  const root = temporaryDirectory(t);
  const journalDirectory = path.join(root, "recovery", "operation-4");
  fs.mkdirSync(journalDirectory, { recursive: true });

  assert.throws(() => validateRecoveryJournal(journalDirectory), expectRule("journal_missing"));
  fs.writeFileSync(path.join(journalDirectory, JOURNAL_FILENAME), "{invalid-json");
  assert.throws(() => validateRecoveryJournal(journalDirectory), expectRule("journal_json"));

  fs.writeFileSync(
    path.join(journalDirectory, JOURNAL_FILENAME),
    JSON.stringify({
      app: "LighthousePM",
      version: RECOVERY_VERSION + 1,
      operation: "restore",
      operationId: "operation-4",
      state: "prepared",
      createdAt: new Date().toISOString(),
      lastTransitionAt: new Date().toISOString(),
      paths: {},
    }),
  );
  assert.throws(() => validateRecoveryJournal(journalDirectory), expectRule("journal_version"));
});

test("recovery-root inspection distinguishes none, one, and ambiguous journals", (t) => {
  const root = temporaryDirectory(t);
  const recoveryRoot = path.join(root, "recovery");
  assert.equal(inspectRecoveryRoot(recoveryRoot), null);
  fs.mkdirSync(recoveryRoot);
  assert.equal(inspectRecoveryRoot(recoveryRoot), null);

  const databasePath = writeFile(path.join(root, "active.db"), "old database");
  const first = createRecoveryJournal(recoveryRoot, {
    operationId: "operation-5",
    operation: "clear-data",
    activePaths: [{ relativePath: "data/lighthouse.db", activePath: databasePath }],
  });
  assert.equal(inspectRecoveryRoot(recoveryRoot).journal.operationId, "operation-5");

  assert.throws(
    () =>
      createRecoveryJournal(recoveryRoot, {
        operationId: "operation-6",
        operation: "clear-data",
        activePaths: [{ relativePath: "data/lighthouse.db", activePath: databasePath }],
      }),
    expectRule("recovery_exists"),
  );

  fs.mkdirSync(path.join(recoveryRoot, "operation-6"));
  assert.throws(() => inspectRecoveryRoot(recoveryRoot), expectRule("multiple_journals"));
  fs.rmSync(path.join(recoveryRoot, "operation-6"), { recursive: true });

  fs.rmSync(first.journalDirectory, { recursive: true });
  fs.writeFileSync(path.join(recoveryRoot, "unexpected-file"), "not a journal");
  assert.throws(() => inspectRecoveryRoot(recoveryRoot), expectRule("recovery_entry_type"));
});

test("rejects paths outside the operation contract and cleans failed journal creation", (t) => {
  const root = temporaryDirectory(t);
  const recoveryRoot = path.join(root, "recovery");
  const configPath = writeFile(path.join(root, "backend.env"), "JIRA_SYNC_ENABLED=false\n");

  assert.throws(
    () =>
      createRecoveryJournal(recoveryRoot, {
        operationId: "operation-7",
        operation: "clear-data",
        activePaths: [{ relativePath: "backend.env", activePath: configPath }],
      }),
    expectRule("active_path"),
  );
  assert.deepEqual(fs.readdirSync(recoveryRoot), []);

  assert.throws(
    () =>
      createRecoveryJournal(recoveryRoot, {
        operationId: "operation-7b",
        operation: "restore",
        activePaths: [null],
      }),
    expectRule("active_path"),
  );
  assert.deepEqual(fs.readdirSync(recoveryRoot), []);

  assert.throws(
    () =>
      createRecoveryJournal(recoveryRoot, {
        operationId: "../operation-8",
        operation: "restore",
        activePaths: [{ relativePath: "backend.env", activePath: configPath }],
      }),
    expectRule("operation_id"),
  );
});

test("does not remove recovery evidence before a terminal state", (t) => {
  const root = temporaryDirectory(t);
  const databasePath = writeFile(path.join(root, "active.db"), "old database");
  let journal = createRecoveryJournal(path.join(root, "recovery"), {
    operationId: "operation-9",
    operation: "clear-data",
    activePaths: [{ relativePath: "data/lighthouse.db", activePath: databasePath }],
  });
  assert.throws(
    () => removeCompletedRecoveryJournal(journal.journalDirectory),
    expectRule("journal_not_terminal"),
  );

  for (const state of ["mutating", "applied", "verifying", "committed"]) {
    journal = transitionRecoveryJournal(journal.journalDirectory, state);
  }
  removeCompletedRecoveryJournal(journal.journalDirectory);
  assert.equal(fs.existsSync(journal.journalDirectory), false);
});

test("restores exact file, directory, and originally absent state from a validated snapshot", (t) => {
  const root = temporaryDirectory(t);
  const activeRoot = path.join(root, "active");
  const databasePath = writeFile(path.join(activeRoot, "data", "lighthouse.db"), "original database");
  const configPath = path.join(activeRoot, "backend.env");
  const logsPath = path.join(activeRoot, "logs");
  writeFile(path.join(logsPath, "backend.log"), "original log");
  writeFile(path.join(logsPath, "archive", "backend.1.log"), "original archive");
  const journal = createRecoveryJournal(path.join(root, "recovery"), {
    operationId: "operation-10",
    operation: "factory-reset",
    activePaths: [
      { relativePath: "data/lighthouse.db", activePath: databasePath },
      { relativePath: "backend.env", activePath: configPath },
      { relativePath: "logs", activePath: logsPath },
    ],
  });

  fs.writeFileSync(databasePath, "replacement database");
  writeFile(configPath, "new config");
  fs.rmSync(logsPath, { recursive: true });
  writeFile(path.join(logsPath, "new.log"), "new log");

  restoreRecoverySnapshot(journal.journalDirectory, (relativePath) =>
    path.join(activeRoot, ...relativePath.split("/")),
  );

  assert.equal(fs.readFileSync(databasePath, "utf8"), "original database");
  assert.equal(fs.existsSync(configPath), false);
  assert.equal(fs.readFileSync(path.join(logsPath, "backend.log"), "utf8"), "original log");
  assert.equal(
    fs.readFileSync(path.join(logsPath, "archive", "backend.1.log"), "utf8"),
    "original archive",
  );
  assert.equal(fs.existsSync(path.join(logsPath, "new.log")), false);
  validateRecoveryJournal(journal.journalDirectory);
});

test("restores backend configuration to its journaled allowlisted location", (t) => {
  const root = temporaryDirectory(t);
  const sidecarConfigPath = writeFile(
    path.join(root, "application", "backend.env"),
    "JIRA_SYNC_ENABLED=true\n",
  );
  const userConfigPath = path.join(root, "user-data", "backend.env");
  const journal = createRecoveryJournal(path.join(root, "recovery"), {
    operationId: "operation-10b",
    operation: "restore",
    activePaths: [
      {
        relativePath: "backend.env",
        activePath: sidecarConfigPath,
        targetLocation: TARGET_LOCATION_APPLICATION_SIDECAR,
      },
    ],
  });
  fs.writeFileSync(sidecarConfigPath, "JIRA_SYNC_ENABLED=false\n");
  const resolverCalls = [];

  restoreRecoverySnapshot(journal.journalDirectory, (relativePath, targetLocation) => {
    resolverCalls.push({ relativePath, targetLocation });
    return targetLocation === TARGET_LOCATION_APPLICATION_SIDECAR
      ? sidecarConfigPath
      : userConfigPath;
  });

  assert.deepEqual(resolverCalls, [
    {
      relativePath: "backend.env",
      targetLocation: TARGET_LOCATION_APPLICATION_SIDECAR,
    },
  ]);
  assert.equal(fs.readFileSync(sidecarConfigPath, "utf8"), "JIRA_SYNC_ENABLED=true\n");
  assert.equal(fs.existsSync(userConfigPath), false);
});

test("rejects missing, unsupported, misplaced, and overlapping target locations", (t) => {
  const root = temporaryDirectory(t);
  const configPath = writeFile(path.join(root, "backend.env"), "JIRA_SYNC_ENABLED=false\n");
  const journal = createRecoveryJournal(path.join(root, "recovery"), {
    operationId: "operation-10c",
    operation: "restore",
    activePaths: [{ relativePath: "backend.env", activePath: configPath }],
  });
  const journalPath = path.join(journal.journalDirectory, JOURNAL_FILENAME);
  const original = JSON.parse(fs.readFileSync(journalPath, "utf8"));

  const assertTamperingRejected = (targetLocations, rule = "target_locations") => {
    fs.writeFileSync(journalPath, `${JSON.stringify({ ...original, targetLocations })}\n`);
    assert.throws(() => validateRecoveryJournal(journal.journalDirectory), expectRule(rule));
  };

  assertTamperingRejected(undefined);
  assertTamperingRejected({ "backend.env": "absolute-path" }, "target_location");
  assertTamperingRejected(
    { "backend.env": TARGET_LOCATION_USER_DATA, logs: TARGET_LOCATION_USER_DATA },
    "active_path",
  );

  fs.rmSync(journal.journalDirectory, { recursive: true });
  assert.throws(
    () =>
      createRecoveryJournal(path.join(root, "recovery"), {
        operationId: "operation-10d",
        operation: "factory-reset",
        activePaths: [
          {
            relativePath: "data/lighthouse.db",
            activePath: path.join(root, "missing.db"),
            targetLocation: TARGET_LOCATION_APPLICATION_SIDECAR,
          },
        ],
      }),
    expectRule("target_location"),
  );

  const logsPath = path.join(root, "logs");
  writeFile(path.join(logsPath, "backend.log"), "log");
  const logsJournal = createRecoveryJournal(path.join(root, "recovery"), {
    operationId: "operation-10e",
    operation: "factory-reset",
    activePaths: [{ relativePath: "logs", activePath: logsPath }],
  });
  const logsJournalPath = path.join(logsJournal.journalDirectory, JOURNAL_FILENAME);
  const logsPayload = JSON.parse(fs.readFileSync(logsJournalPath, "utf8"));
  logsPayload.targetLocations["logs/backend.log"] = TARGET_LOCATION_USER_DATA;
  fs.writeFileSync(logsJournalPath, `${JSON.stringify(logsPayload)}\n`);
  assert.throws(() => validateRecoveryJournal(logsJournal.journalDirectory), expectRule("target_locations"));
});

test("writes bounded rollback diagnostics without invalidating recovery evidence", (t) => {
  const root = temporaryDirectory(t);
  const databasePath = writeFile(path.join(root, "active.db"), "old database");
  const journal = createRecoveryJournal(path.join(root, "recovery"), {
    operationId: "operation-11",
    operation: "restore",
    activePaths: [{ relativePath: "data/lighthouse.db", activePath: databasePath }],
  });

  const diagnostic = writeRecoveryDiagnostic(
    journal.journalDirectory,
    "rollback_copy",
    new Error("copy failed"),
    "2026-07-21T11:00:00.000Z",
  );

  assert.deepEqual(diagnostic, {
    operationId: "operation-11",
    operation: "restore",
    state: "prepared",
    failedAt: "2026-07-21T11:00:00.000Z",
    rule: "rollback_copy",
    detail: "copy failed",
  });
  assert.deepEqual(
    JSON.parse(fs.readFileSync(path.join(journal.journalDirectory, "failure.json"), "utf8")),
    diagnostic,
  );
  validateRecoveryJournal(journal.journalDirectory);
});
