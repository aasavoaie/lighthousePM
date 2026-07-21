const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const BACKUP_APP = "LighthousePM";
const BACKUP_VERSION = 2;
const DATABASE_PATH = "data/lighthouse.db";
const CONFIG_PATH = "backend.env";
const TOKEN_PATH = "secrets/jira-token.bin";
const ALLOWED_PAYLOAD_PATHS = new Set([DATABASE_PATH, CONFIG_PATH, TOKEN_PATH]);

class SettingsBackupValidationError extends Error {
  constructor(backupPath, rule, detail) {
    super(`Backup validation failed for ${backupPath}: ${rule}: ${detail}`);
    this.name = "SettingsBackupValidationError";
    this.backupPath = backupPath;
    this.rule = rule;
    this.detail = detail;
  }
}

function sha256File(filePath) {
  const hash = crypto.createHash("sha256");
  const descriptor = fs.openSync(filePath, "r");
  const buffer = Buffer.allocUnsafe(64 * 1024);
  try {
    let bytesRead = 0;
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

function regularPayloadPath(backupDirectory, relativePath) {
  if (!ALLOWED_PAYLOAD_PATHS.has(relativePath)) {
    throw new SettingsBackupValidationError(
      backupDirectory,
      "payload_path",
      `unsupported payload path ${JSON.stringify(relativePath)}`,
    );
  }
  const root = path.resolve(backupDirectory);
  const payloadPath = path.resolve(root, ...relativePath.split("/"));
  if (!payloadPath.startsWith(`${root}${path.sep}`)) {
    throw new SettingsBackupValidationError(
      backupDirectory,
      "payload_path",
      `payload escapes backup directory: ${relativePath}`,
    );
  }
  let stats;
  try {
    stats = fs.lstatSync(payloadPath);
  } catch {
    throw new SettingsBackupValidationError(
      backupDirectory,
      "payload_missing",
      `declared payload is missing: ${relativePath}`,
    );
  }
  if (!stats.isFile() || stats.isSymbolicLink()) {
    throw new SettingsBackupValidationError(
      backupDirectory,
      "payload_type",
      `payload must be a regular file: ${relativePath}`,
    );
  }
  return { payloadPath, stats };
}

function payloadMetadata(backupDirectory, relativePath) {
  const { payloadPath, stats } = regularPayloadPath(backupDirectory, relativePath);
  return {
    sizeBytes: stats.size,
    sha256: sha256File(payloadPath),
  };
}

function createManifest(backupDirectory, relativePaths, databaseValidation = null) {
  const uniquePaths = [...new Set(relativePaths)].sort();
  if (uniquePaths.length === 0) {
    throw new SettingsBackupValidationError(
      backupDirectory,
      "payload_missing",
      "backup contains no supported payloads",
    );
  }
  const files = Object.fromEntries(
    uniquePaths.map((relativePath) => [relativePath, payloadMetadata(backupDirectory, relativePath)]),
  );
  const hasDatabase = Object.hasOwn(files, DATABASE_PATH);
  if (hasDatabase && !databaseValidation) {
    throw new SettingsBackupValidationError(
      backupDirectory,
      "database_revision",
      "database revision validation is missing",
    );
  }
  return {
    app: BACKUP_APP,
    version: BACKUP_VERSION,
    createdAt: new Date().toISOString(),
    files,
    database: hasDatabase
      ? {
          revision: databaseValidation.source_revision,
          revisionKind: databaseValidation.revision_kind,
        }
      : null,
  };
}

function publishManifest(backupDirectory, manifest) {
  const manifestPath = path.join(backupDirectory, "manifest.json");
  if (fs.existsSync(manifestPath)) {
    throw new SettingsBackupValidationError(
      backupDirectory,
      "manifest_exists",
      "manifest.json already exists",
    );
  }
  const temporaryPath = path.join(
    backupDirectory,
    `.manifest.json.${process.pid}.${crypto.randomBytes(8).toString("hex")}.tmp`,
  );
  const descriptor = fs.openSync(temporaryPath, "wx");
  try {
    fs.writeFileSync(descriptor, JSON.stringify(manifest, null, 2), "utf8");
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
  try {
    fs.renameSync(temporaryPath, manifestPath);
  } finally {
    fs.rmSync(temporaryPath, { force: true });
  }
  return manifestPath;
}

function publishValidatedSettingsBackup(
  backupDirectory,
  relativePaths,
  databaseValidation,
  validateBackup,
) {
  if (typeof validateBackup !== "function") {
    throw new TypeError("validateBackup callback is required.");
  }
  const manifest = createManifest(backupDirectory, relativePaths, databaseValidation);
  const manifestPath = publishManifest(backupDirectory, manifest);
  try {
    validateBackup(backupDirectory);
  } catch (error) {
    fs.rmSync(manifestPath, { force: true });
    throw error;
  }
  return manifestPath;
}

function readManifest(backupDirectory) {
  const manifestPath = path.join(backupDirectory, "manifest.json");
  let stats;
  try {
    stats = fs.lstatSync(manifestPath);
  } catch {
    throw new SettingsBackupValidationError(
      backupDirectory,
      "manifest_missing",
      "manifest.json is missing",
    );
  }
  if (!stats.isFile() || stats.isSymbolicLink()) {
    throw new SettingsBackupValidationError(
      backupDirectory,
      "manifest_type",
      "manifest.json must be a regular file",
    );
  }
  try {
    return JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  } catch (error) {
    throw new SettingsBackupValidationError(
      backupDirectory,
      "manifest_json",
      error instanceof Error ? error.message : "manifest is not valid JSON",
    );
  }
}

function validateManifestIdentity(backupDirectory, manifest) {
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) {
    throw new SettingsBackupValidationError(backupDirectory, "manifest_shape", "manifest must be an object");
  }
  if (manifest.app !== BACKUP_APP) {
    throw new SettingsBackupValidationError(
      backupDirectory,
      "manifest_app",
      `expected ${BACKUP_APP} application identity`,
    );
  }
  if (manifest.version === 1) {
    throw new SettingsBackupValidationError(
      backupDirectory,
      "manifest_version",
      "version 1 is an unverifiable legacy format without stored checksums",
    );
  }
  if (!Number.isInteger(manifest.version) || manifest.version !== BACKUP_VERSION) {
    throw new SettingsBackupValidationError(
      backupDirectory,
      "manifest_version",
      `supported manifest version is ${BACKUP_VERSION}`,
    );
  }
  if (typeof manifest.createdAt !== "string" || !Number.isFinite(Date.parse(manifest.createdAt))) {
    throw new SettingsBackupValidationError(
      backupDirectory,
      "manifest_created_at",
      "createdAt must be a valid timestamp",
    );
  }
  if (!manifest.files || typeof manifest.files !== "object" || Array.isArray(manifest.files)) {
    throw new SettingsBackupValidationError(backupDirectory, "manifest_files", "files must be an object");
  }
}

function validateSettingsBackup(backupDirectory, validators = {}) {
  const resolvedDirectory = path.resolve(backupDirectory);
  const manifest = readManifest(resolvedDirectory);
  validateManifestIdentity(resolvedDirectory, manifest);
  const relativePaths = Object.keys(manifest.files).sort();
  if (relativePaths.length === 0) {
    throw new SettingsBackupValidationError(resolvedDirectory, "payload_missing", "manifest declares no payloads");
  }

  const payloadPaths = {};
  for (const relativePath of relativePaths) {
    const metadata = manifest.files[relativePath];
    if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
      throw new SettingsBackupValidationError(
        resolvedDirectory,
        "payload_metadata",
        `invalid metadata for ${relativePath}`,
      );
    }
    const { payloadPath, stats } = regularPayloadPath(resolvedDirectory, relativePath);
    if (!Number.isSafeInteger(metadata.sizeBytes) || metadata.sizeBytes < 0 || metadata.sizeBytes !== stats.size) {
      throw new SettingsBackupValidationError(
        resolvedDirectory,
        "payload_size",
        `size mismatch for ${relativePath}`,
      );
    }
    if (!/^[a-f0-9]{64}$/.test(metadata.sha256) || metadata.sha256 !== sha256File(payloadPath)) {
      throw new SettingsBackupValidationError(
        resolvedDirectory,
        "payload_sha256",
        `SHA-256 mismatch for ${relativePath}`,
      );
    }
    payloadPaths[relativePath] = payloadPath;
  }

  if (payloadPaths[DATABASE_PATH]) {
    if (
      !manifest.database ||
      typeof manifest.database.revision !== "string" ||
      !["alembic", "recognized_legacy"].includes(manifest.database.revisionKind)
    ) {
      throw new SettingsBackupValidationError(
        resolvedDirectory,
        "database_revision",
        "database revision identity is missing or invalid",
      );
    }
    if (typeof validators.validateDatabase !== "function") {
      throw new SettingsBackupValidationError(
        resolvedDirectory,
        "database_validation",
        "database validator is unavailable",
      );
    }
    const databaseResult = validators.validateDatabase(payloadPaths[DATABASE_PATH]);
    if (
      databaseResult.source_revision !== manifest.database.revision ||
      databaseResult.revision_kind !== manifest.database.revisionKind
    ) {
      throw new SettingsBackupValidationError(
        resolvedDirectory,
        "database_revision",
        "database revision does not match the manifest",
      );
    }
  } else if (manifest.database !== null) {
    throw new SettingsBackupValidationError(
      resolvedDirectory,
      "database_revision",
      "manifest declares database metadata without a database payload",
    );
  }

  if (payloadPaths[CONFIG_PATH]) {
    if (typeof validators.validateConfig !== "function") {
      throw new SettingsBackupValidationError(resolvedDirectory, "config_validation", "config validator is unavailable");
    }
    validators.validateConfig(payloadPaths[CONFIG_PATH]);
  }
  if (payloadPaths[TOKEN_PATH]) {
    if (typeof validators.validateToken !== "function") {
      throw new SettingsBackupValidationError(resolvedDirectory, "token_validation", "token validator is unavailable");
    }
    validators.validateToken(payloadPaths[TOKEN_PATH]);
  }

  return { backupDirectory: resolvedDirectory, manifest, payloadPaths };
}

module.exports = {
  ALLOWED_PAYLOAD_PATHS,
  BACKUP_APP,
  BACKUP_VERSION,
  CONFIG_PATH,
  DATABASE_PATH,
  SettingsBackupValidationError,
  TOKEN_PATH,
  createManifest,
  payloadMetadata,
  publishManifest,
  publishValidatedSettingsBackup,
  sha256File,
  validateSettingsBackup,
};
