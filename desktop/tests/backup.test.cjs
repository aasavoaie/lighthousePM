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
  createManifest,
  publishManifest,
  publishValidatedSettingsBackup,
  validateSettingsBackup,
} = require("../src/backup.cjs");

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "lighthouse-backup-test-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function writePayload(backupDirectory, relativePath, contents) {
  const payloadPath = path.join(backupDirectory, ...relativePath.split("/"));
  fs.mkdirSync(path.dirname(payloadPath), { recursive: true });
  fs.writeFileSync(payloadPath, contents);
  return payloadPath;
}

function validDatabaseResult() {
  return {
    valid: true,
    source_revision: "20260720_0017",
    revision_kind: "alembic",
  };
}

function validators(overrides = {}) {
  return {
    validateDatabase: () => validDatabaseResult(),
    validateConfig: () => ({ valid: true }),
    validateToken: () => ({ valid: true }),
    ...overrides,
  };
}

test("version 2 manifest is published last and validates every payload", (t) => {
  const backupDirectory = temporaryDirectory(t);
  writePayload(backupDirectory, DATABASE_PATH, "database bytes");
  writePayload(backupDirectory, CONFIG_PATH, "JIRA_SYNC_ENABLED=false\n");
  writePayload(backupDirectory, TOKEN_PATH, "encrypted token");

  const manifest = createManifest(
    backupDirectory,
    [DATABASE_PATH, CONFIG_PATH, TOKEN_PATH],
    validDatabaseResult(),
  );
  assert.equal(fs.existsSync(path.join(backupDirectory, "manifest.json")), false);

  publishManifest(backupDirectory, manifest);
  const validated = validateSettingsBackup(backupDirectory, validators());

  assert.equal(validated.manifest.app, "LighthousePM");
  assert.equal(validated.manifest.version, 2);
  assert.deepEqual(Object.keys(validated.manifest.files), [CONFIG_PATH, DATABASE_PATH, TOKEN_PATH]);
  assert.equal(
    fs.readdirSync(backupDirectory).some((name) => name.startsWith(".manifest.json.")),
    false,
  );
});

test("version 1 and unsupported manifest versions fail closed", (t) => {
  const backupDirectory = temporaryDirectory(t);
  for (const version of [1, 0, -1, 3, "2"]) {
    fs.writeFileSync(
      path.join(backupDirectory, "manifest.json"),
      JSON.stringify({ app: "LighthousePM", version, createdAt: new Date().toISOString(), files: {} }),
    );
    assert.throws(
      () => validateSettingsBackup(backupDirectory, validators()),
      (error) => error instanceof SettingsBackupValidationError && error.rule === "manifest_version",
    );
  }
});

test("missing, malformed, and foreign manifests are rejected", (t) => {
  const backupDirectory = temporaryDirectory(t);
  assert.throws(
    () => validateSettingsBackup(backupDirectory, validators()),
    (error) => error instanceof SettingsBackupValidationError && error.rule === "manifest_missing",
  );

  fs.writeFileSync(path.join(backupDirectory, "manifest.json"), "{not-json");
  assert.throws(
    () => validateSettingsBackup(backupDirectory, validators()),
    (error) => error instanceof SettingsBackupValidationError && error.rule === "manifest_json",
  );

  fs.writeFileSync(
    path.join(backupDirectory, "manifest.json"),
    JSON.stringify({ app: "AnotherApp", version: 2, createdAt: new Date().toISOString(), files: {} }),
  );
  assert.throws(
    () => validateSettingsBackup(backupDirectory, validators()),
    (error) => error instanceof SettingsBackupValidationError && error.rule === "manifest_app",
  );
});

test("changed size and checksum are rejected before payload validators run", (t) => {
  const backupDirectory = temporaryDirectory(t);
  const configPath = writePayload(backupDirectory, CONFIG_PATH, "JIRA_SYNC_ENABLED=false\n");
  publishManifest(backupDirectory, createManifest(backupDirectory, [CONFIG_PATH]));
  fs.appendFileSync(configPath, "changed=true\n");
  let validatorCalled = false;

  assert.throws(
    () =>
      validateSettingsBackup(
        backupDirectory,
        validators({
          validateConfig: () => {
            validatorCalled = true;
          },
        }),
      ),
    (error) => error instanceof SettingsBackupValidationError && error.rule === "payload_size",
  );
  assert.equal(validatorCalled, false);

  const manifest = JSON.parse(fs.readFileSync(path.join(backupDirectory, "manifest.json"), "utf8"));
  manifest.files[CONFIG_PATH].sizeBytes = fs.statSync(configPath).size;
  fs.writeFileSync(path.join(backupDirectory, "manifest.json"), JSON.stringify(manifest));
  assert.throws(
    () => validateSettingsBackup(backupDirectory, validators()),
    (error) => error instanceof SettingsBackupValidationError && error.rule === "payload_sha256",
  );
});

test("unsupported, missing, and linked payloads are rejected", (t) => {
  const backupDirectory = temporaryDirectory(t);
  writePayload(backupDirectory, CONFIG_PATH, "valid=true\n");
  const manifest = createManifest(backupDirectory, [CONFIG_PATH]);
  manifest.files["../outside.env"] = manifest.files[CONFIG_PATH];
  fs.writeFileSync(path.join(backupDirectory, "manifest.json"), JSON.stringify(manifest));
  assert.throws(
    () => validateSettingsBackup(backupDirectory, validators()),
    (error) => error instanceof SettingsBackupValidationError && error.rule === "payload_path",
  );

  delete manifest.files["../outside.env"];
  manifest.files[DATABASE_PATH] = manifest.files[CONFIG_PATH];
  fs.writeFileSync(path.join(backupDirectory, "manifest.json"), JSON.stringify(manifest));
  assert.throws(
    () => validateSettingsBackup(backupDirectory, validators()),
    (error) => error instanceof SettingsBackupValidationError && error.rule === "payload_missing",
  );

  delete manifest.files[DATABASE_PATH];
  const outsidePath = path.join(backupDirectory, "outside.env");
  fs.writeFileSync(outsidePath, "outside=true\n");
  const configPath = path.join(backupDirectory, CONFIG_PATH);
  fs.rmSync(configPath);
  try {
    fs.symlinkSync(outsidePath, configPath);
  } catch {
    return;
  }
  fs.writeFileSync(path.join(backupDirectory, "manifest.json"), JSON.stringify(manifest));
  assert.throws(
    () => validateSettingsBackup(backupDirectory, validators()),
    (error) => error instanceof SettingsBackupValidationError && error.rule === "payload_type",
  );
});

test("database revision must match the validated database", (t) => {
  const backupDirectory = temporaryDirectory(t);
  writePayload(backupDirectory, DATABASE_PATH, "database bytes");
  publishManifest(
    backupDirectory,
    createManifest(backupDirectory, [DATABASE_PATH], validDatabaseResult()),
  );

  assert.throws(
    () =>
      validateSettingsBackup(
        backupDirectory,
        validators({
          validateDatabase: () => ({
            valid: true,
            source_revision: "20260717_0016",
            revision_kind: "alembic",
          }),
        }),
      ),
    (error) => error instanceof SettingsBackupValidationError && error.rule === "database_revision",
  );
});

test("configuration and token validators run only after manifest integrity passes", (t) => {
  const backupDirectory = temporaryDirectory(t);
  writePayload(backupDirectory, CONFIG_PATH, "JIRA_SYNC_ENABLED=false\n");
  writePayload(backupDirectory, TOKEN_PATH, "encrypted token");
  publishManifest(
    backupDirectory,
    createManifest(backupDirectory, [CONFIG_PATH, TOKEN_PATH]),
  );
  const events = [];

  validateSettingsBackup(
    backupDirectory,
    validators({
      validateConfig: () => events.push("config"),
      validateToken: () => events.push("token"),
    }),
  );

  assert.deepEqual(events, ["config", "token"]);
});

test("validated backup publication leaves a selectable manifest only after final validation", (t) => {
  const root = temporaryDirectory(t);
  const successfulDirectory = path.join(root, "successful");
  fs.mkdirSync(successfulDirectory);
  writePayload(successfulDirectory, DATABASE_PATH, "database bytes");
  const events = [];

  const manifestPath = publishValidatedSettingsBackup(
    successfulDirectory,
    [DATABASE_PATH],
    validDatabaseResult(),
    (backupDirectory) => {
      events.push("validate");
      assert.equal(fs.existsSync(path.join(backupDirectory, "manifest.json")), true);
      validateSettingsBackup(backupDirectory, validators());
    },
  );

  assert.deepEqual(events, ["validate"]);
  assert.equal(fs.existsSync(manifestPath), true);
});

test("backup failures before or during final validation never leave a selectable manifest", (t) => {
  const root = temporaryDirectory(t);
  const prePublicationDirectory = path.join(root, "pre-publication");
  fs.mkdirSync(prePublicationDirectory);
  writePayload(prePublicationDirectory, DATABASE_PATH, "database bytes");

  assert.throws(
    () =>
      publishValidatedSettingsBackup(
        prePublicationDirectory,
        [DATABASE_PATH, CONFIG_PATH],
        validDatabaseResult(),
        () => assert.fail("validation must not run"),
      ),
    (error) =>
      error instanceof SettingsBackupValidationError &&
      error.rule === "payload_missing",
  );
  assert.equal(fs.existsSync(path.join(prePublicationDirectory, "manifest.json")), false);

  const finalValidationDirectory = path.join(root, "final-validation");
  fs.mkdirSync(finalValidationDirectory);
  writePayload(finalValidationDirectory, DATABASE_PATH, "database bytes");
  assert.throws(
    () =>
      publishValidatedSettingsBackup(
        finalValidationDirectory,
        [DATABASE_PATH],
        validDatabaseResult(),
        () => {
          throw new Error("final backup validation failed");
        },
      ),
    /final backup validation failed/,
  );
  assert.equal(fs.existsSync(path.join(finalValidationDirectory, "manifest.json")), false);
});
