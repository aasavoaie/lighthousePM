function attachBackendProcessObservers({
  backendProcess,
  intentionallyStoppedBackendProcesses,
  isBackendReady,
  isQuitting,
  clearCurrentBackendProcess,
  showBackendError,
  logPath,
}) {
  let failureReported = false;

  function reportFailure(message) {
    if (
      failureReported ||
      isQuitting() ||
      intentionallyStoppedBackendProcesses.has(backendProcess) ||
      !isBackendReady()
    ) {
      return;
    }
    failureReported = true;
    showBackendError(message, `Log: ${logPath}`);
  }

  backendProcess.once("error", (error) => {
    reportFailure(`The local backend could not continue: ${error.message}`);
  });

  backendProcess.once("exit", (code) => {
    const wasIntentionallyStopped = intentionallyStoppedBackendProcesses.has(backendProcess);
    const wasReady = isBackendReady();
    intentionallyStoppedBackendProcesses.delete(backendProcess);
    clearCurrentBackendProcess(backendProcess);
    if (!failureReported && !isQuitting() && !wasIntentionallyStopped && wasReady) {
      failureReported = true;
      showBackendError(
        `The local backend exited with code ${code ?? "unknown"}.`,
        `Log: ${logPath}`,
      );
    }
  });
}

function focusExistingWindow(mainWindow) {
  if (!mainWindow || (typeof mainWindow.isDestroyed === "function" && mainWindow.isDestroyed())) {
    return false;
  }
  if (mainWindow.isMinimized()) {
    mainWindow.restore();
  }
  mainWindow.show();
  mainWindow.focus();
  return true;
}

function createApplicationShutdownCoordinator({
  stopBackend,
  closeRendererServer,
  quitApplication,
  setQuitting,
  onShutdownFailure,
}) {
  let shutdownComplete = false;
  let shutdownPromise = null;

  async function runShutdown() {
    setQuitting(true);
    closeRendererServer();
    try {
      await stopBackend();
      shutdownComplete = true;
      quitApplication();
    } catch (error) {
      setQuitting(false);
      shutdownPromise = null;
      onShutdownFailure(error);
    }
  }

  function handleBeforeQuit(event) {
    if (shutdownComplete) {
      return null;
    }
    event.preventDefault();
    shutdownPromise ??= runShutdown();
    return shutdownPromise;
  }

  return {
    handleBeforeQuit,
    isShutdownComplete: () => shutdownComplete,
  };
}

async function runApplicationStartup({
  recoverStorage,
  startBackend,
  resolveRendererOrigin,
  setRendererOrigin,
  loadRenderer,
  configureUpdates,
}) {
  const recoveryResult = await recoverStorage();
  if (!recoveryResult.backendStarted) {
    await startBackend();
  }
  const rendererOrigin = await resolveRendererOrigin();
  setRendererOrigin(rendererOrigin);
  await loadRenderer(rendererOrigin);
  configureUpdates();
  return rendererOrigin;
}

module.exports = {
  attachBackendProcessObservers,
  createApplicationShutdownCoordinator,
  focusExistingWindow,
  runApplicationStartup,
};
