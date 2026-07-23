const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const test = require("node:test");

const {
  assertCompiledInventory,
  collectFiles,
  executeCompiledTests,
  requireFiles,
} = require("./run-tests.cjs");

test("source test discovery must not be empty", () => {
  assert.throws(
    () => requireFiles([], "source .test.ts files"),
    /found no source \.test\.ts files/
  );
});

test("compiled test discovery must not be empty", () => {
  const sourceDir = path.join("workspace", "src");
  const outDir = path.join("workspace", ".tmp-tests");

  assert.throws(
    () =>
      assertCompiledInventory(
        [path.join(sourceDir, "example.test.ts")],
        [],
        sourceDir,
        outDir
      ),
    /found no compiled \.test\.js files/
  );
});

test("compiled tests must match the source test inventory", () => {
  const sourceDir = path.join("workspace", "src");
  const outDir = path.join("workspace", ".tmp-tests");

  assert.throws(
    () =>
      assertCompiledInventory(
        [path.join(sourceDir, "expected.test.ts")],
        [path.join(outDir, "unexpected.test.js")],
        sourceDir,
        outDir
      ),
    /different compiled test inventory/
  );
});

test("test discovery and execution order are deterministic", (context) => {
  const fixtureDir = fs.mkdtempSync(path.join(os.tmpdir(), "lighthouse-frontend-runner-"));
  context.after(() => fs.rmSync(fixtureDir, { recursive: true, force: true }));

  fs.mkdirSync(path.join(fixtureDir, "nested"));
  fs.writeFileSync(path.join(fixtureDir, "z.test.ts"), "");
  fs.writeFileSync(path.join(fixtureDir, "a.test.ts"), "");
  fs.writeFileSync(path.join(fixtureDir, "nested", "m.test.ts"), "");

  const discovered = collectFiles(fixtureDir, ".test.ts");
  assert.deepStrictEqual(discovered, [...discovered].sort());

  const executed = [];
  executeCompiledTests(
    [path.join(fixtureDir, "z.test.js"), path.join(fixtureDir, "a.test.js")],
    fixtureDir,
    (_executable, arguments_) => executed.push(path.basename(arguments_[0]))
  );
  assert.deepStrictEqual(executed, ["a.test.js", "z.test.js"]);
});

test("a failing compiled assertion is propagated", () => {
  const expectedFailure = new Error("assertion failed");

  assert.throws(
    () =>
      executeCompiledTests(["failing.test.js"], "output", () => {
        throw expectedFailure;
      }),
    (error) => error === expectedFailure
  );
});
