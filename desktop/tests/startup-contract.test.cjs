const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const MAIN_PATH = path.resolve(__dirname, "..", "src", "main.cjs");
const mainSource = fs.readFileSync(MAIN_PATH, "utf8");

function functionSource(name, nextName) {
  const startMarker = `function ${name}(`;
  const asyncStartMarker = `async function ${name}(`;
  const start = Math.max(mainSource.indexOf(startMarker), mainSource.indexOf(asyncStartMarker));
  assert.notEqual(start, -1, `${name} must exist`);

  if (!nextName) {
    return mainSource.slice(start);
  }

  const nextMarker = `function ${nextName}(`;
  const asyncNextMarker = `async function ${nextName}(`;
  const nextCandidates = [mainSource.indexOf(nextMarker, start + 1), mainSource.indexOf(asyncNextMarker, start + 1)]
    .filter((index) => index !== -1);
  assert.ok(nextCandidates.length > 0, `${nextName} must follow ${name}`);
  return mainSource.slice(start, Math.min(...nextCandidates));
}

function assertInOrder(source, markers) {
  let previousIndex = -1;
  for (const marker of markers) {
    const index = source.indexOf(marker);
    assert.ok(index > previousIndex, `${JSON.stringify(marker)} must occur in order`);
    previousIndex = index;
  }
}

test("backend readiness requires a running process and successful health response", () => {
  const healthSource = functionSource("checkBackendHealth", "waitForBackend");
  const waitSource = functionSource("waitForBackend", "startBackend");
  const startSource = functionSource("startBackend", "stopBackend");

  assert.match(healthSource, /response\.statusCode === 200/);
  assertInOrder(waitSource, [
    "if (!backendProcess || backendProcess.exitCode !== null)",
    "if (await checkBackendHealth(origin))",
    "return;",
  ]);
  assertInOrder(startSource, ["backendProcess = spawn(", "await waitForBackend(backendOrigin, logPath);"]);
});

test("desktop workspace remains behind the startup screen until backend readiness", () => {
  const source = functionSource("startApplication");

  assertInOrder(source, [
    "createMainWindow();",
    "await runApplicationStartup({",
    "recoverStorage: recoverDesktopStorageAtStartup",
    "startBackend,",
    "resolveRendererOrigin:",
    "loadRenderer:",
  ]);
  assert.match(source, /showBackendErrorScreen\("LighthousePM could not start the local backend\.", detail\)/);
});

test("direct backend restart waits for confirmed shutdown and the common readiness gate", () => {
  const restartFunctions = [["restartBackend", "fileSize"]];

  for (const [name, nextName] of restartFunctions) {
    const source = functionSource(name, nextName);
    assertInOrder(source, ["await stopBackend();", "await startBackend();"]);
    assert.doesNotMatch(source, /sleep\(400\)/);
  }
});

test("backend shutdown is confirmed before the process reference is released", () => {
  const source = functionSource("stopBackend", "restartBackend");

  assertInOrder(source, [
    "const processToStop = backendProcess;",
    "intentionallyStoppedBackendProcesses.add(processToStop);",
    "await stopProcessAndWait(processToStop, BACKEND_SHUTDOWN_TIMEOUT_MS);",
  ]);
  assert.ok(
    source.lastIndexOf("backendProcess = null;") >
      source.indexOf("await stopProcessAndWait(processToStop, BACKEND_SHUTDOWN_TIMEOUT_MS);"),
    "the live backend reference must be released only after confirmed process exit",
  );
});

test("restore verification uses authenticated release and sprint API contracts", () => {
  const requestSource = functionSource("requestBackendJson", "validateCollectionResponse");
  const verificationSource = functionSource("getVerifiedCoreCollections", "verifyRestoredBackendState");

  assert.match(requestSource, /Authorization: `Bearer \$\{localApiToken\}`/);
  assert.match(requestSource, /response\.statusCode !== 200/);
  assert.match(requestSource, /request\.setTimeout\(3000/);
  assertInOrder(verificationSource, [
    'requestBackendJson("/releases?skip=0&limit=1")',
    'validateCollectionResponse("Releases", releases)',
    'requestBackendJson("/sprints?skip=0&limit=1")',
    'validateCollectionResponse("Sprints", sprints)',
  ]);
});

test("startup recovery runs before normal backend start and uses the authenticated core verification", () => {
  const recoverySource = functionSource("recoverDesktopStorageAtStartup", "captureFactoryResetFailure");
  const startupSource = functionSource("startApplication");

  assertInOrder(recoverySource, [
    "recoverInterruptedStorageOperation({",
    "resolveStartupRecoveryPath(paths, relativePath, targetLocation)",
    "startBackend,",
    "stopBackend,",
    "verifyState: verifyRestoredBackendState",
  ]);
  assertInOrder(startupSource, [
    "await runApplicationStartup({",
    "recoverStorage: recoverDesktopStorageAtStartup",
    "startBackend,",
  ]);
});

test("startup recovery maps journaled logical locations to allowlisted desktop paths", () => {
  const configSource = functionSource("getBackendConfigPaths", "getBackendEnvFile");
  const resolverSource = functionSource("resolveStartupRecoveryPath", "recoverDesktopStorageAtStartup");
  const restorePlanSource = functionSource("buildSettingsRestorePlan", "timestampForBackup");
  const factoryPlanSource = functionSource("buildFactoryResetPlan", "resolveStartupRecoveryPath");

  assert.match(configSource, /TARGET_LOCATION_APPLICATION_SIDECAR/);
  assert.match(configSource, /TARGET_LOCATION_USER_DATA/);
  assert.match(resolverSource, /return paths\.userConfigPath/);
  assert.match(resolverSource, /return paths\.sidecarConfigPath/);
  assert.match(resolverSource, /databaseRecoveryPathMap\(paths\)/);
  assert.match(resolverSource, /BACKUP_TOKEN_PATH, paths\.tokenPath/);
  assert.match(resolverSource, /relativePath\.startsWith\("logs\/"\)/);
  assert.match(restorePlanSource, /targetLocation: paths\.configLocation/);
  assert.match(factoryPlanSource, /targetLocation: paths\.configLocation/);
});

test("desktop storage IPC handlers use one exclusive operation lock", () => {
  const source = functionSource("configureIpcHandlers", "showBackendErrorScreen");

  for (const operation of ["backup", "restore", "clear-data", "factory-reset"]) {
    assert.match(source, new RegExp(`desktopStorageOperations\\.run\\("${operation}"`));
  }
});

test("Settings backup publishes a versioned standalone database without WAL or SHM payloads", () => {
  const source = functionSource("createDesktopBackup", "resolveBackupDirectory");

  assertInOrder(source, [
    '"--create-sqlite-backup"',
    "publishValidatedSettingsBackup(",
    "databaseValidation,",
    "validateDesktopBackup,",
  ]);
  assert.doesNotMatch(source, /lighthouse\.db-(wal|shm)/);
  assert.match(source, /return \{ ok: true, message: "Backup created\.", path: backupDirectory \}/);
});

test("Settings restore validates before shutdown and removes stale database companions", () => {
  const planSource = functionSource("buildSettingsRestorePlan", "timestampForBackup");
  const source = functionSource("restoreDesktopBackup", "clearDesktopData");

  assertInOrder(source, [
    "resolveBackupDirectory(result.filePaths[0])",
    "validateDesktopBackup(backupDirectory)",
    "buildSettingsRestorePlan(validatedBackup, paths)",
    "await runStorageTransaction({",
    "stopBackend,",
    "verifyState: verifyRestoredBackendState",
    'handleStorageTransactionFailure(error, "Settings Restore")',
  ]);
  assertInOrder(planSource, [
    "RECOVERY_DATABASE_WAL_PATH",
    "RECOVERY_DATABASE_SHM_PATH",
    "deletePaths.push(paths.databasePath, `${paths.databasePath}-wal`, `${paths.databasePath}-shm`)",
    "applyFileReplacementPlan({ deletePaths, replacements })",
  ]);
});

test("transaction failure handling closes unsafe workspaces and reopens verified rollbacks", () => {
  const source = functionSource("handleStorageTransactionFailure", "timestampForBackup");

  assert.match(source, /error\.recoveryRequired/);
  assert.match(source, /showBackendErrorScreen/);
  assert.match(source, /error\.previousStateRestored && rendererOrigin && mainWindow/);
  assert.match(source, /await mainWindow\.loadURL\(rendererOrigin\)/);
});

test("Clear Data and Factory Reset use distinct transactional deletion and verification contracts", () => {
  const clearPlanSource = functionSource("buildClearDataPlan", "buildFactoryResetPlan");
  const factoryPlanSource = functionSource("buildFactoryResetPlan", "captureFactoryResetFailure");
  const clearSource = functionSource("clearDesktopData", "factoryResetDesktopData");
  const factorySource = functionSource("factoryResetDesktopData", "revealDesktopDataFolder");
  const emptyVerificationSource = functionSource("verifyEmptyBackendState", "verifyFactoryResetState");
  const factoryVerificationSource = functionSource("verifyFactoryResetState", "startBackend");

  assert.match(clearPlanSource, /databaseRecoveryPathMap\(paths\)/);
  assert.doesNotMatch(clearPlanSource, /configPath|tokenPath|logsDirectory|dataDirectory/);
  assert.match(factoryPlanSource, /BACKUP_CONFIG_PATH, paths\.configPath/);
  assert.match(factoryPlanSource, /BACKUP_TOKEN_PATH, paths\.tokenPath/);
  assert.match(factoryPlanSource, /activePathMap\.set\("logs", paths\.logsDirectory\)/);
  assert.doesNotMatch(factoryPlanSource, /dataDirectory/);

  assertInOrder(clearSource, [
    "buildClearDataPlan(paths)",
    "await runStorageTransaction({",
    'operation: "clear-data"',
    "verifyState: verifyEmptyBackendState",
  ]);
  assertInOrder(factorySource, [
    "buildFactoryResetPlan(paths)",
    "await runStorageTransaction({",
    'operation: "factory-reset"',
    "verifyState: verifyFactoryResetState",
    "captureOperationDiagnostic:",
    "preserveRollbackDiagnostic:",
  ]);
  assert.match(emptyVerificationSource, /releases\.total !== 0/);
  assert.match(emptyVerificationSource, /sprints\.total !== 0/);
  assert.match(factoryVerificationSource, /requestBackendJson\("\/config\/jira"\)/);
  assert.match(factoryVerificationSource, /configuration\.is_complete !== false/);
  assert.match(factoryVerificationSource, /configuration\.jira_api_token_configured !== false/);
});

test("storage operations retain exact user-facing success outcomes", () => {
  const restoreSource = functionSource("restoreDesktopBackup", "clearDesktopData");
  const clearSource = functionSource("clearDesktopData", "factoryResetDesktopData");
  const factorySource = functionSource("factoryResetDesktopData", "revealDesktopDataFolder");

  assert.match(
    restoreSource,
    /return \{ ok: true, message: "Backup restored\.", path: backupDirectory \}/,
  );
  assert.match(clearSource, /return \{ ok: true, message: "Local synced data cleared\." \}/);
  assert.match(factorySource, /return \{ ok: true, message: "Factory reset complete\." \}/);
});
