const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const RECOVERY_APP = "LighthousePM";
const RECOVERY_VERSION = 1;
const JOURNAL_FILENAME = "journal.json";
const FAILURE_FILENAME = "failure.json";
const SNAPSHOT_DIRECTORY = "snapshot";
const TARGET_LOCATION_USER_DATA = "user-data";
const TARGET_LOCATION_APPLICATION_SIDECAR = "application-sidecar";
const TARGET_LOCATIONS = new Set([
  TARGET_LOCATION_USER_DATA,
  TARGET_LOCATION_APPLICATION_SIDECAR,
]);

const OPERATIONS = new Set(["restore", "clear-data", "factory-reset"]);
const STATES = new Set([
  "prepared",
  "mutating",
  "applied",
  "verifying",
  "rolling_back",
  "rollback_applied",
  "rolled_back",
  "committed",
]);
const TERMINAL_STATES = new Set(["rolled_back", "committed"]);
const ALLOWED_TRANSITIONS = new Map([
  ["prepared", new Set(["mutating", "rolling_back"])],
  ["mutating", new Set(["applied", "rolling_back"])],
  ["applied", new Set(["verifying", "rolling_back"])],
  ["verifying", new Set(["committed", "rolling_back"])],
  ["rolling_back", new Set(["rollback_applied"])],
  ["rollback_applied", new Set(["rolled_back", "rolling_back"])],
  ["rolled_back", new Set()],
  ["committed", new Set()],
]);

const DATABASE_PATHS = new Set([
  "data/lighthouse.db",
  "data/lighthouse.db-wal",
  "data/lighthouse.db-shm",
]);
const RESTORE_PATHS = new Set([
  ...DATABASE_PATHS,
  "backend.env",
  "secrets/jira-token.bin",
]);

class RecoveryJournalError extends Error {
  constructor(journalPath, rule, detail) {
    super(`Recovery journal failed for ${journalPath}: ${rule}: ${detail}`);
    this.name = "RecoveryJournalError";
    this.journalPath = journalPath;
    this.rule = rule;
    this.detail = detail;
  }
}

function fail(journalPath, rule, detail) {
  throw new RecoveryJournalError(journalPath, rule, detail);
}

function sha256File(filePath) {
  const hash = crypto.createHash("sha256");
  const descriptor = fs.openSync(filePath, "r");
  const buffer = Buffer.allocUnsafe(64 * 1024);
  try {
    let bytesRead;
    do {
      bytesRead = fs.readSync(descriptor, buffer, 0, buffer.length, null);
      if (bytesRead > 0) {
        hash.update(buffer.subarray(0, bytesRead));
      }
    } while (bytesRead > 0);
  } finally {
    fs.closeSync(descriptor);
  }
  return hash.digest("hex");
}

function isoTimestamp(value = new Date()) {
  const parsed = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(parsed.getTime())) {
    throw new TypeError("Recovery journal timestamp must be valid.");
  }
  return parsed.toISOString();
}

function validateOperationId(operationId, journalPath) {
  if (
    typeof operationId !== "string" ||
    !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(operationId) ||
    operationId === "." ||
    operationId === ".."
  ) {
    fail(journalPath, "operation_id", "operation id must be one safe path segment");
  }
}

function canonicalRelativePath(relativePath, journalPath) {
  if (
    typeof relativePath !== "string" ||
    relativePath.length === 0 ||
    relativePath.includes("\\") ||
    path.posix.isAbsolute(relativePath) ||
    path.posix.normalize(relativePath) !== relativePath ||
    relativePath.split("/").some((part) => !part || part === "." || part === "..")
  ) {
    fail(journalPath, "active_path", `invalid active path ${JSON.stringify(relativePath)}`);
  }
  return relativePath;
}

function isAllowedActivePath(operation, relativePath) {
  if (operation === "clear-data") {
    return DATABASE_PATHS.has(relativePath);
  }
  if (operation === "restore") {
    return RESTORE_PATHS.has(relativePath);
  }
  return RESTORE_PATHS.has(relativePath) || relativePath === "logs" || relativePath.startsWith("logs/");
}

function validateActivePath(operation, relativePath, journalPath) {
  const canonicalPath = canonicalRelativePath(relativePath, journalPath);
  if (!isAllowedActivePath(operation, canonicalPath)) {
    fail(
      journalPath,
      "active_path",
      `${canonicalPath} is not affected by ${operation}`,
    );
  }
  return canonicalPath;
}

function validateTargetLocation(relativePath, targetLocation, journalPath) {
  if (!TARGET_LOCATIONS.has(targetLocation)) {
    fail(
      journalPath,
      "target_location",
      `unsupported target location for ${relativePath}: ${JSON.stringify(targetLocation)}`,
    );
  }
  if (
    targetLocation === TARGET_LOCATION_APPLICATION_SIDECAR &&
    relativePath !== "backend.env"
  ) {
    fail(
      journalPath,
      "target_location",
      `application-sidecar is only supported for backend.env, not ${relativePath}`,
    );
  }
  return targetLocation;
}

function pathInside(root, relativePath, journalPath, rule) {
  const resolvedRoot = path.resolve(root);
  const resolvedPath = path.resolve(resolvedRoot, ...relativePath.split("/"));
  if (!resolvedPath.startsWith(`${resolvedRoot}${path.sep}`)) {
    fail(journalPath, rule, `${relativePath} escapes its recovery directory`);
  }
  return resolvedPath;
}

function atomicWriteJson(targetPath, value, mustNotExist = false) {
  if (mustNotExist && fs.existsSync(targetPath)) {
    fail(targetPath, "journal_exists", `${JOURNAL_FILENAME} already exists`);
  }
  const temporaryPath = path.join(
    path.dirname(targetPath),
    `.${path.basename(targetPath)}.${process.pid}.${crypto.randomBytes(8).toString("hex")}.tmp`,
  );
  let descriptor;
  try {
    descriptor = fs.openSync(temporaryPath, "wx");
    fs.writeFileSync(descriptor, `${JSON.stringify(value, null, 2)}\n`, "utf8");
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    fs.renameSync(temporaryPath, targetPath);
  } finally {
    if (descriptor !== undefined) {
      fs.closeSync(descriptor);
    }
    fs.rmSync(temporaryPath, { force: true });
  }
}

function copySnapshotFile(sourcePath, snapshotPath, journalPath) {
  fs.mkdirSync(path.dirname(snapshotPath), { recursive: true });
  fs.copyFileSync(sourcePath, snapshotPath, fs.constants.COPYFILE_EXCL);
  const descriptor = fs.openSync(snapshotPath, "r+");
  try {
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
  const stats = fs.lstatSync(snapshotPath);
  if (!stats.isFile() || stats.isSymbolicLink()) {
    fail(journalPath, "snapshot_type", `snapshot is not a regular file: ${snapshotPath}`);
  }
  return {
    sizeBytes: stats.size,
    sha256: sha256File(snapshotPath),
  };
}

function capturePath({ operation, journalDirectory, relativePath, activePath, entries }) {
  const canonicalPath = validateActivePath(operation, relativePath, journalDirectory);
  if (Object.hasOwn(entries, canonicalPath)) {
    fail(journalDirectory, "active_path_duplicate", `active path is duplicated: ${canonicalPath}`);
  }

  let stats;
  try {
    stats = fs.lstatSync(activePath);
  } catch (error) {
    if (error && error.code === "ENOENT") {
      entries[canonicalPath] = { present: false };
      return;
    }
    throw error;
  }

  if (stats.isSymbolicLink()) {
    fail(journalDirectory, "active_path_type", `symbolic links are not supported: ${canonicalPath}`);
  }
  if (stats.isFile()) {
    const payloadPath = `${SNAPSHOT_DIRECTORY}/${canonicalPath}`;
    const snapshotPath = pathInside(journalDirectory, payloadPath, journalDirectory, "snapshot_path");
    entries[canonicalPath] = {
      present: true,
      kind: "file",
      payloadPath,
      ...copySnapshotFile(activePath, snapshotPath, journalDirectory),
    };
    return;
  }
  if (stats.isDirectory()) {
    entries[canonicalPath] = { present: true, kind: "directory" };
    fs.mkdirSync(
      pathInside(
        journalDirectory,
        `${SNAPSHOT_DIRECTORY}/${canonicalPath}`,
        journalDirectory,
        "snapshot_path",
      ),
      { recursive: true },
    );
    const children = fs.readdirSync(activePath, { withFileTypes: true }).sort((left, right) =>
      left.name.localeCompare(right.name),
    );
    for (const child of children) {
      capturePath({
        operation,
        journalDirectory,
        relativePath: `${canonicalPath}/${child.name}`,
        activePath: path.join(activePath, child.name),
        entries,
      });
    }
    return;
  }
  fail(journalDirectory, "active_path_type", `unsupported active path type: ${canonicalPath}`);
}

function readJournal(journalDirectory) {
  const journalPath = path.join(journalDirectory, JOURNAL_FILENAME);
  let stats;
  try {
    stats = fs.lstatSync(journalPath);
  } catch (error) {
    if (error && error.code === "ENOENT") {
      fail(journalDirectory, "journal_missing", `${JOURNAL_FILENAME} is missing`);
    }
    throw error;
  }
  if (!stats.isFile() || stats.isSymbolicLink()) {
    fail(journalDirectory, "journal_type", `${JOURNAL_FILENAME} must be a regular file`);
  }
  try {
    return JSON.parse(fs.readFileSync(journalPath, "utf8"));
  } catch (error) {
    fail(
      journalDirectory,
      "journal_json",
      error instanceof Error ? error.message : `${JOURNAL_FILENAME} is not valid JSON`,
    );
  }
}

function validateJournalIdentity(journalDirectory, journal) {
  if (!journal || typeof journal !== "object" || Array.isArray(journal)) {
    fail(journalDirectory, "journal_shape", "journal must be an object");
  }
  if (journal.app !== RECOVERY_APP) {
    fail(journalDirectory, "journal_app", `expected ${RECOVERY_APP} application identity`);
  }
  if (journal.version !== RECOVERY_VERSION) {
    fail(journalDirectory, "journal_version", `supported journal version is ${RECOVERY_VERSION}`);
  }
  validateOperationId(journal.operationId, journalDirectory);
  if (path.basename(path.resolve(journalDirectory)) !== journal.operationId) {
    fail(journalDirectory, "operation_id", "operation id does not match the recovery directory");
  }
  if (!OPERATIONS.has(journal.operation)) {
    fail(journalDirectory, "operation", "operation is not supported");
  }
  if (!STATES.has(journal.state)) {
    fail(journalDirectory, "state", "journal state is not supported");
  }
  if (
    typeof journal.createdAt !== "string" ||
    !Number.isFinite(Date.parse(journal.createdAt)) ||
    typeof journal.lastTransitionAt !== "string" ||
    !Number.isFinite(Date.parse(journal.lastTransitionAt)) ||
    Date.parse(journal.lastTransitionAt) < Date.parse(journal.createdAt)
  ) {
    fail(journalDirectory, "timestamp", "journal timestamps are invalid or out of order");
  }
  if (!journal.paths || typeof journal.paths !== "object" || Array.isArray(journal.paths)) {
    fail(journalDirectory, "paths", "paths must be an object");
  }
  if (
    !journal.targetLocations ||
    typeof journal.targetLocations !== "object" ||
    Array.isArray(journal.targetLocations)
  ) {
    fail(journalDirectory, "target_locations", "targetLocations must be an object");
  }
}

function validateTargetLocations(journalDirectory, journal, relativePaths) {
  const targetRoots = Object.keys(journal.targetLocations).sort();
  if (targetRoots.length === 0) {
    fail(journalDirectory, "target_locations", "journal contains no target locations");
  }
  for (const [index, targetRoot] of targetRoots.entries()) {
    validateActivePath(journal.operation, targetRoot, journalDirectory);
    validateTargetLocation(targetRoot, journal.targetLocations[targetRoot], journalDirectory);
    if (!Object.hasOwn(journal.paths, targetRoot)) {
      fail(
        journalDirectory,
        "target_locations",
        `target-location root is not an affected path: ${targetRoot}`,
      );
    }
    for (const earlierRoot of targetRoots.slice(0, index)) {
      if (targetRoot.startsWith(`${earlierRoot}/`)) {
        fail(
          journalDirectory,
          "target_locations",
          `target-location roots overlap: ${earlierRoot} and ${targetRoot}`,
        );
      }
    }
  }
  for (const relativePath of relativePaths) {
    const matchingRoots = targetRoots.filter(
      (targetRoot) => relativePath === targetRoot || relativePath.startsWith(`${targetRoot}/`),
    );
    if (matchingRoots.length !== 1) {
      fail(
        journalDirectory,
        "target_locations",
        `affected path must have exactly one target location: ${relativePath}`,
      );
    }
  }
}

function targetLocationForPath(journal, relativePath) {
  const targetRoot = Object.keys(journal.targetLocations).find(
    (candidate) => relativePath === candidate || relativePath.startsWith(`${candidate}/`),
  );
  return journal.targetLocations[targetRoot];
}

function validateSnapshotEntry(journalDirectory, operation, relativePath, metadata) {
  validateActivePath(operation, relativePath, journalDirectory);
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
    fail(journalDirectory, "path_metadata", `invalid metadata for ${relativePath}`);
  }
  if (typeof metadata.present !== "boolean") {
    fail(journalDirectory, "path_presence", `presence is missing for ${relativePath}`);
  }
  if (!metadata.present) {
    if (Object.keys(metadata).length !== 1) {
      fail(journalDirectory, "path_metadata", `absent path has payload metadata: ${relativePath}`);
    }
    return;
  }
  if (metadata.kind === "directory") {
    if (Object.keys(metadata).sort().join(",") !== "kind,present") {
      fail(journalDirectory, "path_metadata", `directory metadata is invalid: ${relativePath}`);
    }
    const snapshotPath = pathInside(
      journalDirectory,
      `${SNAPSHOT_DIRECTORY}/${relativePath}`,
      journalDirectory,
      "snapshot_path",
    );
    let stats;
    try {
      stats = fs.lstatSync(snapshotPath);
    } catch {
      fail(journalDirectory, "snapshot_missing", `directory snapshot is missing: ${relativePath}`);
    }
    if (!stats.isDirectory() || stats.isSymbolicLink()) {
      fail(journalDirectory, "snapshot_type", `directory snapshot is invalid: ${relativePath}`);
    }
    return;
  }
  if (metadata.kind !== "file") {
    fail(journalDirectory, "path_kind", `unsupported path kind for ${relativePath}`);
  }
  const expectedPayloadPath = `${SNAPSHOT_DIRECTORY}/${relativePath}`;
  if (metadata.payloadPath !== expectedPayloadPath) {
    fail(journalDirectory, "snapshot_path", `unexpected snapshot path for ${relativePath}`);
  }
  const snapshotPath = pathInside(
    journalDirectory,
    metadata.payloadPath,
    journalDirectory,
    "snapshot_path",
  );
  let stats;
  try {
    stats = fs.lstatSync(snapshotPath);
  } catch {
    fail(journalDirectory, "snapshot_missing", `file snapshot is missing: ${relativePath}`);
  }
  if (!stats.isFile() || stats.isSymbolicLink()) {
    fail(journalDirectory, "snapshot_type", `file snapshot is invalid: ${relativePath}`);
  }
  if (
    !Number.isSafeInteger(metadata.sizeBytes) ||
    metadata.sizeBytes < 0 ||
    metadata.sizeBytes !== stats.size
  ) {
    fail(journalDirectory, "snapshot_size", `snapshot size mismatch for ${relativePath}`);
  }
  if (!/^[a-f0-9]{64}$/.test(metadata.sha256) || metadata.sha256 !== sha256File(snapshotPath)) {
    fail(journalDirectory, "snapshot_sha256", `snapshot SHA-256 mismatch for ${relativePath}`);
  }
}

function validateRecoveryJournal(journalDirectory) {
  const resolvedDirectory = path.resolve(journalDirectory);
  let directoryStats;
  try {
    directoryStats = fs.lstatSync(resolvedDirectory);
  } catch {
    fail(resolvedDirectory, "journal_directory_missing", "recovery directory is missing");
  }
  if (!directoryStats.isDirectory() || directoryStats.isSymbolicLink()) {
    fail(resolvedDirectory, "journal_directory_type", "recovery path must be a regular directory");
  }
  const journal = readJournal(resolvedDirectory);
  validateJournalIdentity(resolvedDirectory, journal);
  const relativePaths = Object.keys(journal.paths).sort();
  if (relativePaths.length === 0) {
    fail(resolvedDirectory, "paths", "journal contains no affected paths");
  }
  validateTargetLocations(resolvedDirectory, journal, relativePaths);
  for (const relativePath of relativePaths) {
    validateSnapshotEntry(resolvedDirectory, journal.operation, relativePath, journal.paths[relativePath]);
  }
  return {
    journalDirectory: resolvedDirectory,
    journalPath: path.join(resolvedDirectory, JOURNAL_FILENAME),
    journal,
  };
}

function createRecoveryJournal(recoveryRoot, { operationId, operation, activePaths, now = new Date() }) {
  const resolvedRoot = path.resolve(recoveryRoot);
  const candidateDirectory = path.join(resolvedRoot, String(operationId));
  validateOperationId(operationId, candidateDirectory);
  if (!OPERATIONS.has(operation)) {
    fail(candidateDirectory, "operation", "operation is not supported");
  }
  if (!Array.isArray(activePaths) || activePaths.length === 0) {
    fail(candidateDirectory, "paths", "at least one active path is required");
  }
  fs.mkdirSync(resolvedRoot, { recursive: true });
  const existingJournal = inspectRecoveryRoot(resolvedRoot);
  if (existingJournal) {
    fail(
      resolvedRoot,
      "recovery_exists",
      `unfinished or unremoved recovery operation ${existingJournal.journal.operationId} already exists`,
    );
  }
  fs.mkdirSync(candidateDirectory);
  try {
    const entries = {};
    const targetLocations = {};
    const declarations = activePaths.map((activePath) => {
      if (
        !activePath ||
        typeof activePath.relativePath !== "string" ||
        typeof activePath.activePath !== "string"
      ) {
        fail(candidateDirectory, "active_path", "active path declaration is invalid");
      }
      const relativePath = validateActivePath(
        operation,
        activePath.relativePath,
        candidateDirectory,
      );
      const targetLocation = validateTargetLocation(
        relativePath,
        activePath.targetLocation ?? TARGET_LOCATION_USER_DATA,
        candidateDirectory,
      );
      return { ...activePath, relativePath, targetLocation };
    });
    declarations.sort((left, right) => left.relativePath.localeCompare(right.relativePath));
    for (const [index, activePath] of declarations.entries()) {
      if (Object.hasOwn(targetLocations, activePath.relativePath)) {
        fail(
          candidateDirectory,
          "active_path_duplicate",
          `active path is duplicated: ${activePath.relativePath}`,
        );
      }
      for (const earlierPath of declarations.slice(0, index)) {
        if (activePath.relativePath.startsWith(`${earlierPath.relativePath}/`)) {
          fail(
            candidateDirectory,
            "active_path_duplicate",
            `active path overlaps another declaration: ${activePath.relativePath}`,
          );
        }
      }
      targetLocations[activePath.relativePath] = activePath.targetLocation;
      capturePath({
        operation,
        journalDirectory: candidateDirectory,
        relativePath: activePath.relativePath,
        activePath: activePath.activePath,
        entries,
      });
    }
    const timestamp = isoTimestamp(now);
    const journal = {
      app: RECOVERY_APP,
      version: RECOVERY_VERSION,
      operation,
      operationId,
      state: "prepared",
      createdAt: timestamp,
      lastTransitionAt: timestamp,
      targetLocations,
      paths: Object.fromEntries(Object.entries(entries).sort(([left], [right]) => left.localeCompare(right))),
    };
    atomicWriteJson(path.join(candidateDirectory, JOURNAL_FILENAME), journal, true);
    return validateRecoveryJournal(candidateDirectory);
  } catch (error) {
    fs.rmSync(candidateDirectory, { recursive: true, force: true });
    throw error;
  }
}

function transitionRecoveryJournal(journalDirectory, nextState, now = new Date()) {
  const validated = validateRecoveryJournal(journalDirectory);
  if (!STATES.has(nextState)) {
    fail(validated.journalDirectory, "state", `unsupported next state ${JSON.stringify(nextState)}`);
  }
  const allowed = ALLOWED_TRANSITIONS.get(validated.journal.state);
  if (!allowed.has(nextState)) {
    fail(
      validated.journalDirectory,
      "state_transition",
      `${validated.journal.state} cannot transition to ${nextState}`,
    );
  }
  const lastTransitionAt = isoTimestamp(now);
  if (Date.parse(lastTransitionAt) < Date.parse(validated.journal.lastTransitionAt)) {
    fail(validated.journalDirectory, "timestamp", "state transition timestamp moved backwards");
  }
  const journal = { ...validated.journal, state: nextState, lastTransitionAt };
  atomicWriteJson(validated.journalPath, journal);
  return validateRecoveryJournal(validated.journalDirectory);
}

function inspectRecoveryRoot(recoveryRoot) {
  const resolvedRoot = path.resolve(recoveryRoot);
  let rootStats;
  try {
    rootStats = fs.lstatSync(resolvedRoot);
  } catch (error) {
    if (error && error.code === "ENOENT") {
      return null;
    }
    throw error;
  }
  if (!rootStats.isDirectory() || rootStats.isSymbolicLink()) {
    fail(resolvedRoot, "recovery_root_type", "recovery root must be a regular directory");
  }
  const entries = fs.readdirSync(resolvedRoot, { withFileTypes: true });
  if (entries.length === 0) {
    return null;
  }
  if (entries.length !== 1) {
    fail(resolvedRoot, "multiple_journals", "exactly one recovery operation may be present");
  }
  const entry = entries[0];
  if (!entry.isDirectory() || entry.isSymbolicLink()) {
    fail(resolvedRoot, "recovery_entry_type", "recovery root contains a non-directory entry");
  }
  return validateRecoveryJournal(path.join(resolvedRoot, entry.name));
}

function resolveActiveTargets(validated, resolveActivePath) {
  if (typeof resolveActivePath !== "function") {
    fail(validated.journalDirectory, "active_path_resolver", "active path resolver is unavailable");
  }
  const targets = new Map();
  const resolvedTargets = new Set();
  for (const relativePath of Object.keys(validated.journal.paths).sort()) {
    const targetPath = resolveActivePath(
      relativePath,
      targetLocationForPath(validated.journal, relativePath),
    );
    if (typeof targetPath !== "string" || !path.isAbsolute(targetPath)) {
      fail(
        validated.journalDirectory,
        "active_path_resolver",
        `active path resolver returned an invalid target for ${relativePath}`,
      );
    }
    const resolvedTarget = path.resolve(targetPath);
    if (resolvedTargets.has(resolvedTarget)) {
      fail(
        validated.journalDirectory,
        "active_path_resolver",
        `multiple recovery paths resolve to ${resolvedTarget}`,
      );
    }
    resolvedTargets.add(resolvedTarget);
    targets.set(relativePath, resolvedTarget);
  }
  return targets;
}

function copyRecoveredFile(snapshotPath, targetPath, metadata, journalDirectory) {
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  const temporaryPath = path.join(
    path.dirname(targetPath),
    `.${path.basename(targetPath)}.${process.pid}.${crypto.randomBytes(8).toString("hex")}.recovery.tmp`,
  );
  try {
    fs.copyFileSync(snapshotPath, temporaryPath, fs.constants.COPYFILE_EXCL);
    const descriptor = fs.openSync(temporaryPath, "r+");
    try {
      fs.fsyncSync(descriptor);
    } finally {
      fs.closeSync(descriptor);
    }
    const stats = fs.lstatSync(temporaryPath);
    if (stats.size !== metadata.sizeBytes || sha256File(temporaryPath) !== metadata.sha256) {
      fail(journalDirectory, "recovery_copy", `recovered copy validation failed for ${targetPath}`);
    }
    fs.renameSync(temporaryPath, targetPath);
  } finally {
    fs.rmSync(temporaryPath, { force: true });
  }
}

function validateRecoveredTargets(validated, targets) {
  for (const [relativePath, metadata] of Object.entries(validated.journal.paths)) {
    const targetPath = targets.get(relativePath);
    let stats;
    try {
      stats = fs.lstatSync(targetPath);
    } catch (error) {
      if (error && error.code === "ENOENT" && !metadata.present) {
        continue;
      }
      fail(validated.journalDirectory, "recovery_verify", `active path is missing: ${relativePath}`);
    }
    if (!metadata.present) {
      fail(validated.journalDirectory, "recovery_verify", `originally absent path exists: ${relativePath}`);
    }
    if (metadata.kind === "directory") {
      if (!stats.isDirectory() || stats.isSymbolicLink()) {
        fail(validated.journalDirectory, "recovery_verify", `directory was not restored: ${relativePath}`);
      }
      continue;
    }
    if (
      !stats.isFile() ||
      stats.isSymbolicLink() ||
      stats.size !== metadata.sizeBytes ||
      sha256File(targetPath) !== metadata.sha256
    ) {
      fail(validated.journalDirectory, "recovery_verify", `file was not restored exactly: ${relativePath}`);
    }
  }
}

function restoreRecoverySnapshot(journalDirectory, resolveActivePath) {
  const validated = validateRecoveryJournal(journalDirectory);
  const targets = resolveActiveTargets(validated, resolveActivePath);
  const deepestFirst = [...targets.keys()].sort((left, right) => {
    const depthDifference = right.split("/").length - left.split("/").length;
    return depthDifference || right.localeCompare(left);
  });
  for (const relativePath of deepestFirst) {
    fs.rmSync(targets.get(relativePath), { recursive: true, force: true });
  }

  const shallowestFirst = [...targets.keys()].sort((left, right) => {
    const depthDifference = left.split("/").length - right.split("/").length;
    return depthDifference || left.localeCompare(right);
  });
  for (const relativePath of shallowestFirst) {
    const metadata = validated.journal.paths[relativePath];
    if (!metadata.present) {
      continue;
    }
    const targetPath = targets.get(relativePath);
    if (metadata.kind === "directory") {
      fs.mkdirSync(targetPath, { recursive: true });
      continue;
    }
    const snapshotPath = pathInside(
      validated.journalDirectory,
      metadata.payloadPath,
      validated.journalDirectory,
      "snapshot_path",
    );
    copyRecoveredFile(snapshotPath, targetPath, metadata, validated.journalDirectory);
  }
  validateRecoveredTargets(validated, targets);
  return validated;
}

function writeRecoveryDiagnostic(journalDirectory, rule, error, now = new Date()) {
  const validated = validateRecoveryJournal(journalDirectory);
  const detail = (error instanceof Error ? error.message : String(error)).slice(0, 4096);
  const diagnostic = {
    operationId: validated.journal.operationId,
    operation: validated.journal.operation,
    state: validated.journal.state,
    failedAt: isoTimestamp(now),
    rule,
    detail,
  };
  atomicWriteJson(path.join(validated.journalDirectory, FAILURE_FILENAME), diagnostic);
  return diagnostic;
}

function removeCompletedRecoveryJournal(journalDirectory) {
  const validated = validateRecoveryJournal(journalDirectory);
  if (!TERMINAL_STATES.has(validated.journal.state)) {
    fail(
      validated.journalDirectory,
      "journal_not_terminal",
      `cannot remove journal in ${validated.journal.state} state`,
    );
  }
  fs.rmSync(validated.journalDirectory, { recursive: true });
}

module.exports = {
  ALLOWED_TRANSITIONS,
  FAILURE_FILENAME,
  JOURNAL_FILENAME,
  OPERATIONS,
  RECOVERY_APP,
  RECOVERY_VERSION,
  RecoveryJournalError,
  SNAPSHOT_DIRECTORY,
  STATES,
  TARGET_LOCATION_APPLICATION_SIDECAR,
  TARGET_LOCATION_USER_DATA,
  TERMINAL_STATES,
  createRecoveryJournal,
  inspectRecoveryRoot,
  removeCompletedRecoveryJournal,
  restoreRecoverySnapshot,
  transitionRecoveryJournal,
  validateRecoveryJournal,
  writeRecoveryDiagnostic,
};
