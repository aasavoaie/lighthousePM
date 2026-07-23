const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  discoverNodeTests,
  executeNodeTests,
  requireNodeTests,
} = require("../scripts/run-node-tests.cjs");

test("desktop test discovery fails closed when no test files exist", () => {
  assert.throws(
    () => requireNodeTests([]),
    /Desktop test runner found no \.test\.cjs files/,
  );
});

test("desktop test discovery includes only sorted direct test files", (context) => {
  const testDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "lighthouse-desktop-runner-"));
  context.after(() => fs.rmSync(testDirectory, { recursive: true, force: true }));
  fs.writeFileSync(path.join(testDirectory, "z.test.cjs"), "");
  fs.writeFileSync(path.join(testDirectory, "a.test.cjs"), "");
  fs.writeFileSync(path.join(testDirectory, "helper.cjs"), "");
  fs.mkdirSync(path.join(testDirectory, "nested"));
  fs.writeFileSync(path.join(testDirectory, "nested", "ignored.test.cjs"), "");

  assert.deepEqual(
    discoverNodeTests(testDirectory).map((filePath) => path.basename(filePath)),
    ["a.test.cjs", "z.test.cjs"],
  );
});

test("desktop test execution passes a deterministic inventory to Node", () => {
  let invocation = null;
  executeNodeTests(
    ["C:/tests/z.test.cjs", "C:/tests/a.test.cjs"],
    "C:/desktop",
    (executable, arguments_, options) => {
      invocation = { executable, arguments_, options };
    },
  );

  assert.equal(invocation.executable, process.execPath);
  assert.deepEqual(invocation.arguments_, [
    "--test",
    "C:/tests/a.test.cjs",
    "C:/tests/z.test.cjs",
  ]);
  assert.deepEqual(invocation.options, {
    cwd: "C:/desktop",
    stdio: "inherit",
  });
});

test("desktop test execution propagates runner failures", () => {
  const expectedFailure = new Error("Node test failure");
  assert.throws(
    () => executeNodeTests(["failing.test.cjs"], "desktop", () => {
      throw expectedFailure;
    }),
    (error) => error === expectedFailure,
  );
});
