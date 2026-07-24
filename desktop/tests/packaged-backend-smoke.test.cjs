const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const desktopRoot = path.resolve(__dirname, "..");
const packageJson = JSON.parse(fs.readFileSync(path.join(desktopRoot, "package.json"), "utf8"));
const {
  LOOPBACK_HOST,
  backendExecutablePath,
  diagnosticText,
  removeTemporaryDirectory,
  requireBackendExecutable,
  reserveLoopbackPort,
  sanitizedBackendEnvironment,
  terminateBackend,
  validateAnonymousResponse,
  validateEmptyReleasesResponse,
  validateHealthResponse,
  waitForHealth,
} = require("../scripts/smoke-packaged-backend.cjs");

test("packaged backend path and package commands remain explicit", () => {
  assert.equal(
    backendExecutablePath("repository"),
    path.join(
      "repository",
      "backend",
      "dist",
      "lighthousepm-backend",
      "lighthousepm-backend.exe"
    )
  );
  assert.equal(packageJson.scripts["smoke:backend"], "node scripts/smoke-packaged-backend.cjs");
  assert.equal(packageJson.scripts["test:node"], "node scripts/run-node-tests.cjs");
  assert.equal(packageJson.scripts.test, "npm run lint && npm run test:node");
  assert.match(packageJson.scripts.lint, /node --check scripts\/run-node-tests\.cjs/);
  assert.match(packageJson.scripts.lint, /node --check scripts\/smoke-packaged-backend\.cjs/);
});

test("missing executable fails before smoke startup", (context) => {
  const fixtureDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "lighthouse-smoke-path-"));
  context.after(() => fs.rmSync(fixtureDirectory, { recursive: true, force: true }));

  assert.throws(
    () => requireBackendExecutable(path.join(fixtureDirectory, "missing.exe")),
    /Packaged backend not found/
  );
});

test("smoke environment removes inherited credentials and deployment configuration", () => {
  const environment = sanitizedBackendEnvironment("synthetic-token", {
    Path: "system-path",
    APP_ENV: "dev",
    DATABASE_URL: "postgresql://secret",
    DEPLOYMENT_MODE: "docker",
    ELECTRON_RUN_AS_NODE: "1",
    JIRA_API_TOKEN: "jira-secret",
    LIGHTHOUSE_API_TOKEN: "old-token",
    LIGHTHOUSE_API_TOKEN_FILE: "token-file",
    LIGHTHOUSE_CONFIG_FILE: "config-file",
    POSTGRES_PASSWORD: "database-secret",
  });

  assert.deepEqual(environment, {
    Path: "system-path",
    LIGHTHOUSE_API_TOKEN: "synthetic-token",
  });
});

test("smoke diagnostics always redact the synthetic token", () => {
  const token = "token-that-must-not-appear";
  const diagnostic = diagnosticText(
    { stdout: `started ${token}`, stderr: `failed ${token}` },
    token
  );

  assert.doesNotMatch(diagnostic, new RegExp(token));
  assert.equal(diagnostic.match(/\[REDACTED\]/g)?.length, 2);
});

test("health, authentication, and empty releases require exact contracts", () => {
  assert.doesNotThrow(() => validateHealthResponse({ statusCode: 200, body: { status: "ok" } }));
  assert.doesNotThrow(() =>
    validateAnonymousResponse({
      statusCode: 401,
      body: { detail: "API authentication failed." },
    })
  );
  assert.doesNotThrow(() =>
    validateEmptyReleasesResponse({
      statusCode: 200,
      body: { items: [], skip: 0, limit: 1, total: 0 },
    })
  );

  assert.throws(
    () => validateHealthResponse({ statusCode: 200, body: { status: "starting" } }),
    /health response was not ready/
  );
  assert.throws(
    () => validateAnonymousResponse({ statusCode: 200, body: { items: [] } }),
    /did not enforce authentication/
  );
  assert.throws(
    () =>
      validateEmptyReleasesResponse({
        statusCode: 200,
        body: { items: [], skip: 0, limit: 1, total: 0, unexpected: true },
      }),
    /expected empty releases response/
  );
});

test("health waiting detects readiness, early exit, and bounded timeout", async () => {
  await waitForHealth(
    { exitCode: null },
    12345,
    100,
    async () => ({ statusCode: 200, body: { status: "ok" } }),
    async () => {}
  );

  await assert.rejects(
    waitForHealth({ exitCode: 7 }, 12345, 100, async () => {
      throw new Error("must not request");
    }),
    /exited early with code 7/
  );
  await assert.rejects(
    waitForHealth({ exitCode: null }, 12345, 0, async () => {
      throw new Error("unavailable");
    }),
    /did not become healthy within 0 ms/
  );
});

test("loopback port selection and process termination are explicit", async () => {
  const port = await reserveLoopbackPort();
  assert.equal(LOOPBACK_HOST, "127.0.0.1");
  assert.ok(Number.isInteger(port) && port > 0 && port <= 65535);

  class FakeChildProcess extends EventEmitter {
    constructor() {
      super();
      this.exitCode = null;
      this.pid = 12345;
      this.killCalls = 0;
    }

    kill() {
      this.killCalls += 1;
      setImmediate(() => {
        this.exitCode = 0;
        this.emit("exit", 0, null);
      });
      return true;
    }
  }

  const childProcess = new FakeChildProcess();
  await terminateBackend(childProcess, 100);
  assert.equal(childProcess.killCalls, 1);
  assert.equal(childProcess.exitCode, 0);
});

test("temporary smoke data is removed and cleanup is idempotent", () => {
  const fixtureDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "lighthouse-smoke-cleanup-"));
  fs.writeFileSync(path.join(fixtureDirectory, "lighthouse.db"), "temporary");

  removeTemporaryDirectory(fixtureDirectory);
  removeTemporaryDirectory(fixtureDirectory);
  assert.equal(fs.existsSync(fixtureDirectory), false);
});
