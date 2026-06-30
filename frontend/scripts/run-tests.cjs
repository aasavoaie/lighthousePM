const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const rootDir = path.resolve(__dirname, "..");
const outDir = path.join(rootDir, ".tmp-tests");
const tscPath = path.join(rootDir, "node_modules", "typescript", "bin", "tsc");

function collectFiles(dir, extension) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectFiles(fullPath, extension));
    } else if (entry.isFile() && entry.name.endsWith(extension)) {
      files.push(fullPath);
    }
  }

  return files;
}

fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, "package.json"), JSON.stringify({ type: "commonjs" }, null, 2));

const sourceTestFiles = collectFiles(path.join(rootDir, "src"), ".test.ts").sort();
const testTsConfigPath = path.join(outDir, "tsconfig.tests.json");
fs.writeFileSync(
  testTsConfigPath,
  JSON.stringify(
    {
      extends: path.join(rootDir, "tsconfig.app.json"),
      compilerOptions: {
        module: "commonjs",
        outDir,
        noEmit: false,
        incremental: false,
      },
      include: [],
      files: sourceTestFiles,
    },
    null,
    2
  )
);

execFileSync(
  process.execPath,
  [
    tscPath,
    "-p",
    testTsConfigPath,
  ],
  { cwd: rootDir, stdio: "inherit" }
);

const testFiles = collectFiles(outDir, ".test.js").sort();
for (const testFile of testFiles) {
  execFileSync(process.execPath, [testFile], { cwd: outDir, stdio: "inherit" });
}

console.log(`Ran ${testFiles.length} frontend assertion files.`);
