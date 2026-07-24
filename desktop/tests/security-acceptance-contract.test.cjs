const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const desktopRoot = path.resolve(__dirname, "..");
const packageJson = JSON.parse(fs.readFileSync(path.join(desktopRoot, "package.json"), "utf8"));
const verificationSource = fs.readFileSync(
  path.join(desktopRoot, "scripts", "verify-security.cjs"),
  "utf8",
);

test("Windows releases run security acceptance before packaging and artifact verification", () => {
  assert.equal(
    packageJson.scripts["release:windows"],
    "npm run verify:security && npm run make && npm run verify:release",
  );
  assert.equal(packageJson.scripts["verify:security"], "node scripts/verify-security.cjs");
});

test("security acceptance covers every implementation surface", () => {
  for (const marker of [
    '["-m", "pytest", "tests", "-q"]',
    '["-m", "ruff", "check", "app", "tests", "alembic"]',
    '"frontend tests"',
    '"frontend production build"',
    'run("desktop tests"',
  ]) {
    assert.ok(verificationSource.includes(marker), `${marker} must remain in the security gate`);
  }
});

test("available or explicitly required Docker makes container acceptance mandatory", () => {
  assert.match(verificationSource, /commandWorks\(\s*"docker",\s*\["info"/);
  assert.match(verificationSource, /dockerRequired && !dockerAvailable/);
  assert.match(
    verificationSource,
    /backendEnvironment\.LIGHTHOUSE_REQUIRE_DOCKER_SECURITY = "1"/,
  );
});
