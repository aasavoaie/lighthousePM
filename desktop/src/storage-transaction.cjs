const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const {
  createRecoveryJournal,
  inspectRecoveryRoot,
  removeCompletedRecoveryJournal,
  restoreRecoverySnapshot,
  transitionRecoveryJournal,
  writeRecoveryDiagnostic,
} = require("./storage-recovery.cjs");

class StorageTransactionError extends Error {
  constructor(message, options = {}) {
    super(message, options.cause ? { cause: options.cause } : undefined);
    this.name = "StorageTransactionError";
    this.rule = options.rule ?? "storage_transaction";
    this.previousStateRestored = options.previousStateRestored === true;
    this.recoveryRequired = options.recoveryRequired === true;
    this.recoveryPath = options.recoveryPath ?? null;
  }
}

function errorDetail(error) {
  return error instanceof Error ? error.message : String(error);
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

function requireRegularSource(sourcePath) {
  let stats;
  try {
    stats = fs.lstatSync(sourcePath);
  } catch {
    throw new Error(`Replacement source is missing: ${sourcePath}`);
  }
  if (!stats.isFile() || stats.isSymbolicLink()) {
    throw new Error(`Replacement source must be a regular file: ${sourcePath}`);
  }
  return stats;
}

function replaceFileAtomically(sourcePath, targetPath) {
  const sourceStats = requireRegularSource(sourcePath);
  const sourceHash = sha256File(sourcePath);
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  const temporaryPath = path.join(
    path.dirname(targetPath),
    `.${path.basename(targetPath)}.${process.pid}.${crypto.randomBytes(8).toString("hex")}.restore.tmp`,
  );
  try {
    fs.copyFileSync(sourcePath, temporaryPath, fs.constants.COPYFILE_EXCL);
    const descriptor = fs.openSync(temporaryPath, "r+");
    try {
      fs.fsyncSync(descriptor);
    } finally {
      fs.closeSync(descriptor);
    }
    const copiedStats = fs.lstatSync(temporaryPath);
    if (copiedStats.size !== sourceStats.size || sha256File(temporaryPath) !== sourceHash) {
      throw new Error(`Replacement copy validation failed for ${targetPath}`);
    }
    fs.rmSync(targetPath, { recursive: true, force: true });
    fs.renameSync(temporaryPath, targetPath);
  } finally {
    fs.rmSync(temporaryPath, { force: true });
  }
}

function applyFileReplacementPlan({ deletePaths = [], replacements = [] }) {
  if (!Array.isArray(deletePaths) || !Array.isArray(replacements)) {
    throw new TypeError("File replacement plan must contain arrays.");
  }
  for (const targetPath of deletePaths) {
    if (typeof targetPath !== "string" || !path.isAbsolute(targetPath)) {
      throw new TypeError("Deletion target must be an absolute path.");
    }
    fs.rmSync(targetPath, { recursive: true, force: true });
  }
  for (const replacement of replacements) {
    if (
      !replacement ||
      typeof replacement.sourcePath !== "string" ||
      typeof replacement.targetPath !== "string" ||
      !path.isAbsolute(replacement.sourcePath) ||
      !path.isAbsolute(replacement.targetPath)
    ) {
      throw new TypeError("Replacement source and target must be absolute paths.");
    }
    replaceFileAtomically(replacement.sourcePath, replacement.targetPath);
  }
}

function validateTransactionOptions(options) {
  for (const callbackName of [
    "applyChanges",
    "resolveActivePath",
    "startBackend",
    "stopBackend",
    "verifyState",
  ]) {
    if (typeof options[callbackName] !== "function") {
      throw new TypeError(`${callbackName} callback is required.`);
    }
  }
  if (!Array.isArray(options.activePaths) || options.activePaths.length === 0) {
    throw new TypeError("At least one active path is required.");
  }
  if (
    options.captureOperationDiagnostic !== undefined &&
    typeof options.captureOperationDiagnostic !== "function"
  ) {
    throw new TypeError("captureOperationDiagnostic must be a function when provided.");
  }
  if (
    options.preserveRollbackDiagnostic !== undefined &&
    typeof options.preserveRollbackDiagnostic !== "function"
  ) {
    throw new TypeError("preserveRollbackDiagnostic must be a function when provided.");
  }
}

function recordDiagnostic(journalDirectory, rule, error) {
  try {
    writeRecoveryDiagnostic(journalDirectory, rule, error);
  } catch {
    // The original journal and snapshots remain the authoritative recovery evidence.
  }
}

function validateStartupRecoveryOptions(options) {
  for (const callbackName of ["resolveActivePath", "startBackend", "stopBackend", "verifyState"]) {
    if (typeof options[callbackName] !== "function") {
      throw new TypeError(`${callbackName} callback is required.`);
    }
  }
  if (typeof options.recoveryRoot !== "string" || !path.isAbsolute(options.recoveryRoot)) {
    throw new TypeError("recoveryRoot must be an absolute path.");
  }
}

async function stopBackendAfterRecoveryFailure(stopBackend) {
  try {
    await stopBackend();
  } catch {
    // The primary recovery failure remains the actionable error and journal evidence is preserved.
  }
}

async function recoverInterruptedStorageOperation(options) {
  validateStartupRecoveryOptions(options);
  const { recoveryRoot, resolveActivePath, startBackend, stopBackend, verifyState } = options;
  let recovery;
  try {
    recovery = inspectRecoveryRoot(recoveryRoot);
  } catch (inspectionError) {
    throw new StorageTransactionError(
      `Startup recovery could not validate recovery state. Recovery is preserved at ${recoveryRoot}.`,
      {
        cause: inspectionError,
        rule: "startup_recovery_invalid",
        recoveryRequired: true,
        recoveryPath: recoveryRoot,
      },
    );
  }
  if (!recovery) {
    return { backendStarted: false, recoveredOperationId: null };
  }

  if (recovery.journal.state === "committed" || recovery.journal.state === "rolled_back") {
    try {
      removeCompletedRecoveryJournal(recovery.journalDirectory);
    } catch (cleanupError) {
      recordDiagnostic(recovery.journalDirectory, "startup_recovery_cleanup", cleanupError);
      throw new StorageTransactionError(
        `Startup recovery could not remove completed recovery evidence. Recovery is preserved at ${recovery.journalDirectory}.`,
        {
          cause: cleanupError,
          rule: "startup_recovery_cleanup",
          recoveryRequired: true,
          recoveryPath: recovery.journalDirectory,
        },
      );
    }
    return {
      backendStarted: false,
      recoveredOperationId: recovery.journal.operationId,
    };
  }

  try {
    if (recovery.journal.state !== "rolling_back") {
      recovery = transitionRecoveryJournal(recovery.journalDirectory, "rolling_back");
    }
    restoreRecoverySnapshot(recovery.journalDirectory, resolveActivePath);
    recovery = transitionRecoveryJournal(recovery.journalDirectory, "rollback_applied");
  } catch (restoreError) {
    recordDiagnostic(recovery.journalDirectory, "startup_recovery_restore", restoreError);
    throw new StorageTransactionError(
      `Startup recovery could not restore the previous files. Recovery is preserved at ${recovery.journalDirectory}.`,
      {
        cause: restoreError,
        rule: "startup_recovery_restore",
        recoveryRequired: true,
        recoveryPath: recovery.journalDirectory,
      },
    );
  }

  try {
    await startBackend();
    await verifyState();
  } catch (restartError) {
    await stopBackendAfterRecoveryFailure(stopBackend);
    recordDiagnostic(recovery.journalDirectory, "startup_recovery_restart", restartError);
    throw new StorageTransactionError(
      `Startup recovery restored the previous files, but the previous backend did not become ready. Recovery is preserved at ${recovery.journalDirectory}.`,
      {
        cause: restartError,
        rule: "startup_recovery_restart",
        recoveryRequired: true,
        recoveryPath: recovery.journalDirectory,
      },
    );
  }

  try {
    recovery = transitionRecoveryJournal(recovery.journalDirectory, "rolled_back");
    removeCompletedRecoveryJournal(recovery.journalDirectory);
  } catch (cleanupError) {
    await stopBackendAfterRecoveryFailure(stopBackend);
    recordDiagnostic(recovery.journalDirectory, "startup_recovery_cleanup", cleanupError);
    throw new StorageTransactionError(
      `Startup recovery restored the previous state, but cleanup did not finish. Recovery is preserved at ${recovery.journalDirectory}.`,
      {
        cause: cleanupError,
        rule: "startup_recovery_cleanup",
        previousStateRestored: true,
        recoveryRequired: true,
        recoveryPath: recovery.journalDirectory,
      },
    );
  }

  return {
    backendStarted: true,
    recoveredOperationId: recovery.journal.operationId,
  };
}

async function failWithRollback({
  captureOperationDiagnostic,
  operationLabel,
  operationError,
  preserveRollbackDiagnostic,
  recovery,
  resolveActivePath,
  startBackend,
  stopBackend,
  verifyState,
}) {
  try {
    await stopBackend();
  } catch (rollbackShutdownError) {
    recordDiagnostic(recovery.journalDirectory, "rollback_shutdown", rollbackShutdownError);
    throw new StorageTransactionError(
      `${operationLabel} failed and automatic rollback could not stop the backend. Recovery is preserved at ${recovery.journalDirectory}.`,
      {
        cause: rollbackShutdownError,
        rule: "rollback_shutdown",
        recoveryRequired: true,
        recoveryPath: recovery.journalDirectory,
      },
    );
  }
  recordDiagnostic(recovery.journalDirectory, "operation_failure", operationError);
  if (captureOperationDiagnostic) {
    try {
      await captureOperationDiagnostic(recovery.journalDirectory, operationError);
    } catch (diagnosticError) {
      recordDiagnostic(recovery.journalDirectory, "diagnostic_capture", diagnosticError);
    }
  }

  try {
    recovery = transitionRecoveryJournal(recovery.journalDirectory, "rolling_back");
    restoreRecoverySnapshot(recovery.journalDirectory, resolveActivePath);
    recovery = transitionRecoveryJournal(recovery.journalDirectory, "rollback_applied");
  } catch (rollbackCopyError) {
    recordDiagnostic(recovery.journalDirectory, "rollback_copy", rollbackCopyError);
    throw new StorageTransactionError(
      `${operationLabel} failed and automatic rollback could not restore the previous files. Recovery is preserved at ${recovery.journalDirectory}.`,
      {
        cause: rollbackCopyError,
        rule: "rollback_copy",
        recoveryRequired: true,
        recoveryPath: recovery.journalDirectory,
      },
    );
  }

  try {
    await startBackend();
    await verifyState();
  } catch (rollbackRestartError) {
    recordDiagnostic(recovery.journalDirectory, "rollback_restart", rollbackRestartError);
    throw new StorageTransactionError(
      `${operationLabel} failed and the previous files were restored, but the previous backend did not become ready. Recovery is preserved at ${recovery.journalDirectory}.`,
      {
        cause: rollbackRestartError,
        rule: "rollback_restart",
        recoveryRequired: true,
        recoveryPath: recovery.journalDirectory,
      },
    );
  }

  if (preserveRollbackDiagnostic) {
    try {
      await preserveRollbackDiagnostic(recovery.journalDirectory, operationError);
    } catch (diagnosticError) {
      recordDiagnostic(recovery.journalDirectory, "rollback_diagnostic", diagnosticError);
      throw new StorageTransactionError(
        `${operationLabel} failed; previous state restored. Recovery diagnostics remain at ${recovery.journalDirectory}.`,
        {
          cause: diagnosticError,
          rule: "rollback_diagnostic",
          previousStateRestored: true,
          recoveryPath: recovery.journalDirectory,
        },
      );
    }
  }

  try {
    recovery = transitionRecoveryJournal(recovery.journalDirectory, "rolled_back");
    removeCompletedRecoveryJournal(recovery.journalDirectory);
  } catch (rollbackCleanupError) {
    recordDiagnostic(recovery.journalDirectory, "rollback_cleanup", rollbackCleanupError);
    throw new StorageTransactionError(
      `${operationLabel} failed; previous state restored. Recovery cleanup remains at ${recovery.journalDirectory}.`,
      {
        cause: rollbackCleanupError,
        rule: "rollback_cleanup",
        previousStateRestored: true,
        recoveryPath: recovery.journalDirectory,
      },
    );
  }

  throw new StorageTransactionError(
    `${operationLabel} failed; previous state restored. Cause: ${errorDetail(operationError)}`,
    {
      cause: operationError,
      rule: "operation_rolled_back",
      previousStateRestored: true,
    },
  );
}

async function runStorageTransaction(options) {
  validateTransactionOptions(options);
  const {
    activePaths,
    applyChanges,
    captureOperationDiagnostic,
    operation,
    operationId,
    operationLabel,
    preserveRollbackDiagnostic,
    recoveryRoot,
    resolveActivePath,
    startBackend,
    stopBackend,
    verifyState,
  } = options;

  let existingRecovery;
  try {
    existingRecovery = inspectRecoveryRoot(recoveryRoot);
  } catch (recoveryStateError) {
    throw new StorageTransactionError(
      `${operationLabel} was not started because recovery state is invalid. Recovery is preserved at ${recoveryRoot}.`,
      {
        cause: recoveryStateError,
        rule: "recovery_state_invalid",
        recoveryRequired: true,
        recoveryPath: recoveryRoot,
      },
    );
  }
  if (existingRecovery) {
    throw new StorageTransactionError(
      `${operationLabel} was not started because recovery operation ${existingRecovery.journal.operationId} is unfinished. Recovery is preserved at ${existingRecovery.journalDirectory}.`,
      {
        rule: "recovery_pending",
        recoveryRequired: true,
        recoveryPath: existingRecovery.journalDirectory,
      },
    );
  }

  try {
    await stopBackend();
  } catch (shutdownError) {
    throw new StorageTransactionError(
      `${operationLabel} was not started because backend shutdown was not confirmed.`,
      { cause: shutdownError, rule: "shutdown_unconfirmed" },
    );
  }

  let recovery;
  try {
    recovery = createRecoveryJournal(recoveryRoot, {
      operationId,
      operation,
      activePaths,
    });
  } catch (snapshotError) {
    let recoveryAfterFailure;
    try {
      recoveryAfterFailure = inspectRecoveryRoot(recoveryRoot);
    } catch (recoveryStateError) {
      throw new StorageTransactionError(
        `${operationLabel} could not publish recovery evidence because recovery state became invalid. Recovery is preserved at ${recoveryRoot}.`,
        {
          cause: recoveryStateError,
          rule: "recovery_state_changed",
          recoveryRequired: true,
          recoveryPath: recoveryRoot,
        },
      );
    }
    if (recoveryAfterFailure) {
      throw new StorageTransactionError(
        `${operationLabel} could not publish recovery evidence because operation ${recoveryAfterFailure.journal.operationId} appeared concurrently. Recovery is preserved at ${recoveryAfterFailure.journalDirectory}.`,
        {
          cause: snapshotError,
          rule: "recovery_state_changed",
          recoveryRequired: true,
          recoveryPath: recoveryAfterFailure.journalDirectory,
        },
      );
    }
    try {
      await startBackend();
      await verifyState();
    } catch (restartError) {
      throw new StorageTransactionError(
        `${operationLabel} could not create recovery evidence, and the unchanged backend did not restart.`,
        { cause: restartError, rule: "snapshot_restart", recoveryRequired: true },
      );
    }
    throw new StorageTransactionError(
      `${operationLabel} failed before active files changed; previous state remains unchanged.`,
      { cause: snapshotError, rule: "snapshot_failed" },
    );
  }

  try {
    recovery = transitionRecoveryJournal(recovery.journalDirectory, "mutating");
    await applyChanges();
    recovery = transitionRecoveryJournal(recovery.journalDirectory, "applied");
    await startBackend();
    recovery = transitionRecoveryJournal(recovery.journalDirectory, "verifying");
    await verifyState();
    recovery = transitionRecoveryJournal(recovery.journalDirectory, "committed");
  } catch (operationError) {
    return failWithRollback({
      captureOperationDiagnostic,
      operationLabel,
      operationError,
      preserveRollbackDiagnostic,
      recovery,
      resolveActivePath,
      startBackend,
      stopBackend,
      verifyState,
    });
  }

  try {
    removeCompletedRecoveryJournal(recovery.journalDirectory);
  } catch (cleanupError) {
    recordDiagnostic(recovery.journalDirectory, "commit_cleanup", cleanupError);
    throw new StorageTransactionError(
      `${operationLabel} completed, but recovery cleanup remains at ${recovery.journalDirectory}.`,
      {
        cause: cleanupError,
        rule: "commit_cleanup",
        recoveryPath: recovery.journalDirectory,
      },
    );
  }
  return { recoveryPath: recovery.journalDirectory };
}

module.exports = {
  StorageTransactionError,
  applyFileReplacementPlan,
  recoverInterruptedStorageOperation,
  replaceFileAtomically,
  runStorageTransaction,
};
