const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const test = require("node:test");

const {
  BackendShutdownError,
  DesktopOperationBusyError,
  createDesktopOperationLock,
  stopProcessAndWait,
} = require("../src/operation-control.cjs");

class FakeChildProcess extends EventEmitter {
  constructor(killBehavior = () => true) {
    super();
    this.exitCode = null;
    this.signalCode = null;
    this.killCalls = 0;
    this.killBehavior = killBehavior;
  }

  kill() {
    this.killCalls += 1;
    return this.killBehavior(this);
  }

  exit(code = 0, signal = null) {
    this.exitCode = code;
    this.signalCode = signal;
    this.emit("exit", code, signal);
  }
}

function expectShutdownRule(rule) {
  return (error) => error instanceof BackendShutdownError && error.rule === rule;
}

test("confirmed shutdown resolves only after the child process exits", async () => {
  const child = new FakeChildProcess(() => true);
  let settled = false;

  const shutdown = stopProcessAndWait(child, 1000);
  void shutdown.then(() => {
    settled = true;
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(settled, false);

  child.exit(0, "SIGTERM");
  const result = await shutdown;

  assert.equal(settled, true);
  assert.deepEqual(result, { alreadyExited: false, exitCode: 0, signal: "SIGTERM" });
  assert.equal(child.killCalls, 1);
  assert.equal(child.listenerCount("exit"), 0);
  assert.equal(child.listenerCount("error"), 0);
});

test("already-exited and absent processes need no termination request", async () => {
  const child = new FakeChildProcess();
  child.exitCode = 4;

  assert.deepEqual(await stopProcessAndWait(child, 1000), {
    alreadyExited: true,
    exitCode: 4,
    signal: null,
  });
  assert.equal(child.killCalls, 0);
  assert.deepEqual(await stopProcessAndWait(null, 1000), {
    alreadyExited: true,
    exitCode: null,
    signal: null,
  });
});

test("rejected and failed termination requests fail explicitly", async () => {
  await assert.rejects(stopProcessAndWait({ exitCode: null }, 1000), expectShutdownRule("process_invalid"));

  const rejectedChild = new FakeChildProcess(() => false);
  await assert.rejects(stopProcessAndWait(rejectedChild, 1000), expectShutdownRule("kill_rejected"));

  const failedChild = new FakeChildProcess(() => {
    throw new Error("access denied");
  });
  await assert.rejects(stopProcessAndWait(failedChild, 1000), expectShutdownRule("kill_failed"));
});

test("process errors and exit timeouts clean up temporary listeners", async () => {
  const errorChild = new FakeChildProcess((process) => {
    queueMicrotask(() => process.emit("error", new Error("termination error")));
    return true;
  });
  await assert.rejects(stopProcessAndWait(errorChild, 1000), expectShutdownRule("process_error"));
  assert.equal(errorChild.listenerCount("exit"), 0);
  assert.equal(errorChild.listenerCount("error"), 0);

  const hangingChild = new FakeChildProcess(() => true);
  await assert.rejects(stopProcessAndWait(hangingChild, 10), expectShutdownRule("exit_timeout"));
  assert.equal(hangingChild.listenerCount("exit"), 0);
  assert.equal(hangingChild.listenerCount("error"), 0);
});

test("operation lock rejects concurrency and releases after success", async () => {
  const lock = createDesktopOperationLock();
  let releaseFirst;
  const firstCanFinish = new Promise((resolve) => {
    releaseFirst = resolve;
  });
  const first = lock.run("backup", async () => {
    await firstCanFinish;
    return "complete";
  });

  assert.equal(lock.activeOperation, "backup");
  await assert.rejects(
    lock.run("restore", async () => "not-run"),
    (error) =>
      error instanceof DesktopOperationBusyError &&
      error.requestedOperation === "restore" &&
      error.activeOperation === "backup",
  );
  releaseFirst();
  assert.equal(await first, "complete");
  assert.equal(lock.activeOperation, null);
  assert.equal(await lock.run("restore", async () => "restored"), "restored");
});

test("operation lock releases after task failure", async () => {
  const lock = createDesktopOperationLock();
  await assert.rejects(
    lock.run("clear-data", async () => {
      throw new Error("clear failed");
    }),
    /clear failed/,
  );

  assert.equal(lock.activeOperation, null);
  assert.equal(await lock.run("factory-reset", async () => "reset"), "reset");
});
