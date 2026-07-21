class BackendShutdownError extends Error {
  constructor(rule, detail) {
    super(`Backend shutdown failed: ${rule}: ${detail}`);
    this.name = "BackendShutdownError";
    this.rule = rule;
    this.detail = detail;
  }
}

class DesktopOperationBusyError extends Error {
  constructor(requestedOperation, activeOperation) {
    super(
      `Cannot start ${requestedOperation}: another desktop storage operation is already running (${activeOperation}).`,
    );
    this.name = "DesktopOperationBusyError";
    this.requestedOperation = requestedOperation;
    this.activeOperation = activeOperation;
  }
}

function createDesktopOperationLock() {
  let activeOperation = null;
  return {
    get activeOperation() {
      return activeOperation;
    },
    async run(operation, task) {
      if (activeOperation !== null) {
        throw new DesktopOperationBusyError(operation, activeOperation);
      }
      if (typeof operation !== "string" || operation.length === 0 || typeof task !== "function") {
        throw new TypeError("Desktop operation and task are required.");
      }
      activeOperation = operation;
      try {
        return await task();
      } finally {
        activeOperation = null;
      }
    },
  };
}

function stopProcessAndWait(childProcess, timeoutMs) {
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs <= 0) {
    return Promise.reject(
      new BackendShutdownError("timeout_invalid", "shutdown timeout must be a positive integer"),
    );
  }
  if (!childProcess) {
    return Promise.resolve({ alreadyExited: true, exitCode: null, signal: null });
  }
  if (
    typeof childProcess.once !== "function" ||
    typeof childProcess.removeListener !== "function" ||
    typeof childProcess.kill !== "function"
  ) {
    return Promise.reject(
      new BackendShutdownError("process_invalid", "backend process handle is invalid"),
    );
  }
  if (childProcess.exitCode !== null) {
    return Promise.resolve({ alreadyExited: true, exitCode: childProcess.exitCode, signal: null });
  }

  return new Promise((resolve, reject) => {
    let settled = false;
    let timeout;

    const cleanup = () => {
      clearTimeout(timeout);
      childProcess.removeListener("exit", onExit);
      childProcess.removeListener("error", onError);
    };
    const succeed = (exitCode, signal) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      resolve({ alreadyExited: false, exitCode, signal });
    };
    const fail = (rule, detail) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      reject(new BackendShutdownError(rule, detail));
    };
    const onExit = (exitCode, signal) => succeed(exitCode, signal);
    const onError = (error) =>
      fail("process_error", error instanceof Error ? error.message : "backend process emitted an error");

    childProcess.once("exit", onExit);
    childProcess.once("error", onError);
    timeout = setTimeout(
      () => fail("exit_timeout", `backend process did not exit within ${timeoutMs} ms`),
      timeoutMs,
    );

    try {
      const killAccepted = childProcess.kill();
      if (!killAccepted && childProcess.exitCode === null) {
        fail("kill_rejected", "operating system did not accept the backend termination request");
      } else if (childProcess.exitCode !== null) {
        succeed(childProcess.exitCode, childProcess.signalCode ?? null);
      }
    } catch (error) {
      fail("kill_failed", error instanceof Error ? error.message : "backend termination request failed");
    }
  });
}

module.exports = {
  BackendShutdownError,
  DesktopOperationBusyError,
  createDesktopOperationLock,
  stopProcessAndWait,
};
