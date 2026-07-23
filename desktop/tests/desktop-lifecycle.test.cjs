const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const test = require("node:test");

const {
  attachBackendProcessObservers,
  createApplicationShutdownCoordinator,
  focusExistingWindow,
  runApplicationStartup,
} = require("../src/desktop-lifecycle.cjs");

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

function observedProcess({ ready = true, quitting = false, intentional = false } = {}) {
  const backendProcess = new EventEmitter();
  const intentionallyStoppedBackendProcesses = new WeakSet();
  if (intentional) {
    intentionallyStoppedBackendProcesses.add(backendProcess);
  }
  const errors = [];
  let cleared = false;
  attachBackendProcessObservers({
    backendProcess,
    intentionallyStoppedBackendProcesses,
    isBackendReady: () => ready,
    isQuitting: () => quitting,
    clearCurrentBackendProcess: (processToClear) => {
      assert.equal(processToClear, backendProcess);
      cleared = true;
    },
    showBackendError: (message, detail) => errors.push({ message, detail }),
    logPath: "C:/LighthousePM/logs/backend.log",
  });
  return {
    backendProcess,
    errors,
    intentionallyStoppedBackendProcesses,
    wasCleared: () => cleared,
  };
}

test("pre-readiness process failure remains owned by the startup boundary", () => {
  const observed = observedProcess({ ready: false });
  observed.backendProcess.emit("error", new Error("spawn failed"));
  observed.backendProcess.emit("exit", 1);

  assert.deepEqual(observed.errors, []);
  assert.equal(observed.wasCleared(), true);
});

test("unexpected ready-process failure reports once with the backend log path", () => {
  const observed = observedProcess();
  observed.backendProcess.emit("error", new Error("pipe failed"));
  observed.backendProcess.emit("exit", 7);

  assert.deepEqual(observed.errors, [{
    message: "The local backend could not continue: pipe failed",
    detail: "Log: C:/LighthousePM/logs/backend.log",
  }]);
  assert.equal(observed.wasCleared(), true);
});

test("intentional exit and application shutdown do not report unexpected failure", () => {
  const intentional = observedProcess({ intentional: true });
  intentional.backendProcess.emit("exit", 0);
  assert.deepEqual(intentional.errors, []);
  assert.equal(intentional.intentionallyStoppedBackendProcesses.has(intentional.backendProcess), false);

  const quitting = observedProcess({ quitting: true });
  quitting.backendProcess.emit("exit", 1);
  assert.deepEqual(quitting.errors, []);
});

test("second instance restores, shows, and focuses the existing window", () => {
  const calls = [];
  const mainWindow = {
    isDestroyed: () => false,
    isMinimized: () => true,
    restore: () => calls.push("restore"),
    show: () => calls.push("show"),
    focus: () => calls.push("focus"),
  };

  assert.equal(focusExistingWindow(mainWindow), true);
  assert.deepEqual(calls, ["restore", "show", "focus"]);
  assert.equal(focusExistingWindow(null), false);
  assert.equal(focusExistingWindow({ isDestroyed: () => true }), false);
});

test("application shutdown waits for confirmed backend termination and deduplicates requests", async () => {
  const backendStop = deferred();
  const calls = [];
  const coordinator = createApplicationShutdownCoordinator({
    stopBackend: () => {
      calls.push("stop-backend");
      return backendStop.promise;
    },
    closeRendererServer: () => calls.push("close-renderer"),
    quitApplication: () => calls.push("quit"),
    setQuitting: (value) => calls.push(`quitting:${value}`),
    onShutdownFailure: (error) => calls.push(`failure:${error.message}`),
  });
  let prevented = 0;
  const event = { preventDefault: () => { prevented += 1; } };

  const first = coordinator.handleBeforeQuit(event);
  const second = coordinator.handleBeforeQuit(event);
  assert.equal(first, second);
  assert.equal(prevented, 2);
  assert.deepEqual(calls, ["quitting:true", "close-renderer", "stop-backend"]);
  assert.equal(coordinator.isShutdownComplete(), false);

  backendStop.resolve();
  await first;
  assert.deepEqual(calls, ["quitting:true", "close-renderer", "stop-backend", "quit"]);
  assert.equal(coordinator.isShutdownComplete(), true);
  assert.equal(coordinator.handleBeforeQuit(event), null);
  assert.equal(prevented, 2);
});

test("failed shutdown remains fail-closed and permits a controlled retry", async () => {
  let attempt = 0;
  const calls = [];
  const coordinator = createApplicationShutdownCoordinator({
    stopBackend: async () => {
      attempt += 1;
      calls.push(`stop:${attempt}`);
      if (attempt === 1) {
        throw new Error("termination timeout");
      }
    },
    closeRendererServer: () => calls.push("close-renderer"),
    quitApplication: () => calls.push("quit"),
    setQuitting: (value) => calls.push(`quitting:${value}`),
    onShutdownFailure: (error) => calls.push(`failure:${error.message}`),
  });
  const event = { preventDefault: () => {} };

  await coordinator.handleBeforeQuit(event);
  assert.equal(coordinator.isShutdownComplete(), false);
  assert.deepEqual(calls, [
    "quitting:true",
    "close-renderer",
    "stop:1",
    "quitting:false",
    "failure:termination timeout",
  ]);

  await coordinator.handleBeforeQuit(event);
  assert.equal(coordinator.isShutdownComplete(), true);
  assert.deepEqual(calls.slice(-4), ["quitting:true", "close-renderer", "stop:2", "quit"]);
});

test("startup keeps renderer loading behind recovery and backend readiness", async () => {
  const calls = [];
  const origin = await runApplicationStartup({
    recoverStorage: async () => {
      calls.push("recover");
      return { backendStarted: false };
    },
    startBackend: async () => calls.push("start-backend"),
    resolveRendererOrigin: async () => {
      calls.push("resolve-renderer");
      return "http://127.0.0.1:51234";
    },
    setRendererOrigin: (value) => calls.push(`set-renderer:${value}`),
    loadRenderer: async (value) => calls.push(`load-renderer:${value}`),
    configureUpdates: () => calls.push("configure-updates"),
  });

  assert.equal(origin, "http://127.0.0.1:51234");
  assert.deepEqual(calls, [
    "recover",
    "start-backend",
    "resolve-renderer",
    "set-renderer:http://127.0.0.1:51234",
    "load-renderer:http://127.0.0.1:51234",
    "configure-updates",
  ]);
});

test("startup failure before readiness never resolves or loads the renderer", async () => {
  for (const failureMessage of [
    "backend not ready",
    "database migration failed",
    "backend configuration invalid",
  ]) {
    const calls = [];
    await assert.rejects(
      runApplicationStartup({
        recoverStorage: async () => {
          calls.push("recover");
          return { backendStarted: false };
        },
        startBackend: async () => {
          calls.push("start-backend");
          throw new Error(failureMessage);
        },
        resolveRendererOrigin: async () => {
          calls.push("resolve-renderer");
          return "http://127.0.0.1:51234";
        },
        setRendererOrigin: () => calls.push("set-renderer"),
        loadRenderer: async () => calls.push("load-renderer"),
        configureUpdates: () => calls.push("configure-updates"),
      }),
      new RegExp(failureMessage),
    );
    assert.deepEqual(calls, ["recover", "start-backend"]);
  }
});

test("recovered backend state skips an ordinary second backend start", async () => {
  const calls = [];
  await runApplicationStartup({
    recoverStorage: async () => {
      calls.push("recover");
      return { backendStarted: true };
    },
    startBackend: async () => calls.push("start-backend"),
    resolveRendererOrigin: async () => {
      calls.push("resolve-renderer");
      return "http://127.0.0.1:51234";
    },
    setRendererOrigin: () => calls.push("set-renderer"),
    loadRenderer: async () => calls.push("load-renderer"),
    configureUpdates: () => calls.push("configure-updates"),
  });

  assert.deepEqual(calls, [
    "recover",
    "resolve-renderer",
    "set-renderer",
    "load-renderer",
    "configure-updates",
  ]);
});

test("recovery failure prevents backend startup and every renderer step", async () => {
  const calls = [];
  await assert.rejects(
    runApplicationStartup({
      recoverStorage: async () => {
        calls.push("recover");
        throw new Error("recovery evidence invalid");
      },
      startBackend: async () => calls.push("start-backend"),
      resolveRendererOrigin: async () => calls.push("resolve-renderer"),
      setRendererOrigin: () => calls.push("set-renderer"),
      loadRenderer: async () => calls.push("load-renderer"),
      configureUpdates: () => calls.push("configure-updates"),
    }),
    /recovery evidence invalid/,
  );
  assert.deepEqual(calls, ["recover"]);
});

test("renderer startup and loading failures do not execute later startup steps", async () => {
  const rendererStartCalls = [];
  await assert.rejects(
    runApplicationStartup({
      recoverStorage: async () => {
        rendererStartCalls.push("recover");
        return { backendStarted: false };
      },
      startBackend: async () => rendererStartCalls.push("start-backend"),
      resolveRendererOrigin: async () => {
        rendererStartCalls.push("resolve-renderer");
        throw new Error("renderer server failed");
      },
      setRendererOrigin: () => rendererStartCalls.push("set-renderer"),
      loadRenderer: async () => rendererStartCalls.push("load-renderer"),
      configureUpdates: () => rendererStartCalls.push("configure-updates"),
    }),
    /renderer server failed/,
  );
  assert.deepEqual(rendererStartCalls, ["recover", "start-backend", "resolve-renderer"]);

  const rendererLoadCalls = [];
  await assert.rejects(
    runApplicationStartup({
      recoverStorage: async () => {
        rendererLoadCalls.push("recover");
        return { backendStarted: false };
      },
      startBackend: async () => rendererLoadCalls.push("start-backend"),
      resolveRendererOrigin: async () => {
        rendererLoadCalls.push("resolve-renderer");
        return "http://127.0.0.1:51234";
      },
      setRendererOrigin: () => rendererLoadCalls.push("set-renderer"),
      loadRenderer: async () => {
        rendererLoadCalls.push("load-renderer");
        throw new Error("renderer load failed");
      },
      configureUpdates: () => rendererLoadCalls.push("configure-updates"),
    }),
    /renderer load failed/,
  );
  assert.deepEqual(rendererLoadCalls, [
    "recover",
    "start-backend",
    "resolve-renderer",
    "set-renderer",
    "load-renderer",
  ]);
});
