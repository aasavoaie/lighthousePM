const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const DEFAULT_DESKTOP_ROOT = path.resolve(__dirname, "..");

function discoverNodeTests(testDirectory) {
  if (!fs.existsSync(testDirectory)) {
    return [];
  }
  return fs
    .readdirSync(testDirectory, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".test.cjs"))
    .map((entry) => path.join(testDirectory, entry.name))
    .sort();
}

function requireNodeTests(testFiles) {
  if (testFiles.length === 0) {
    throw new Error("Desktop test runner found no .test.cjs files.");
  }
}

function executeNodeTests(testFiles, desktopRoot, execute = execFileSync) {
  const orderedTests = [...testFiles].sort();
  execute(process.execPath, ["--test", ...orderedTests], {
    cwd: desktopRoot,
    stdio: "inherit",
  });
}

function runDesktopNodeTests(desktopRoot = DEFAULT_DESKTOP_ROOT) {
  const testFiles = discoverNodeTests(path.join(desktopRoot, "tests"));
  requireNodeTests(testFiles);
  executeNodeTests(testFiles, desktopRoot);
  return testFiles.length;
}

if (require.main === module) {
  const testCount = runDesktopNodeTests();
  console.log(`Ran ${testCount} desktop Node test files.`);
}

module.exports = {
  discoverNodeTests,
  executeNodeTests,
  requireNodeTests,
  runDesktopNodeTests,
};
