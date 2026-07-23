const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const DEFAULT_ROOT_DIR = path.resolve(__dirname, "..");

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

  return files.sort();
}

function requireFiles(files, description) {
  if (files.length === 0) {
    throw new Error(`Frontend assertion runner found no ${description}.`);
  }
}

function relativeTestInventory(files, baseDir, sourceExtension) {
  return files.map((file) => {
    const relativePath = path.relative(baseDir, file);
    return relativePath.slice(0, -sourceExtension.length) + ".test.js";
  });
}

function assertCompiledInventory(sourceTestFiles, compiledTestFiles, sourceDir, outDir) {
  requireFiles(compiledTestFiles, "compiled .test.js files");

  const expected = relativeTestInventory(sourceTestFiles, sourceDir, ".test.ts");
  const actual = compiledTestFiles.map((file) => path.relative(outDir, file));

  if (expected.length !== actual.length || expected.some((file, index) => file !== actual[index])) {
    throw new Error(
      [
        "Frontend assertion runner produced a different compiled test inventory.",
        `Expected: ${expected.join(", ")}`,
        `Actual: ${actual.join(", ")}`,
      ].join("\n")
    );
  }
}

function executeCompiledTests(compiledTestFiles, outDir, execute = execFileSync) {
  for (const testFile of [...compiledTestFiles].sort()) {
    execute(process.execPath, [testFile], { cwd: outDir, stdio: "inherit" });
  }
}

function runFrontendAssertions(rootDir = DEFAULT_ROOT_DIR) {
  const sourceDir = path.join(rootDir, "src");
  const outDir = path.join(rootDir, ".tmp-tests");
  const tscPath = path.join(rootDir, "node_modules", "typescript", "bin", "tsc");
  const sourceTestFiles = collectFiles(sourceDir, ".test.ts");

  requireFiles(sourceTestFiles, "source .test.ts files");

  fs.rmSync(outDir, { recursive: true, force: true });
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(
    path.join(outDir, "package.json"),
    JSON.stringify({ type: "commonjs" }, null, 2)
  );

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

  execFileSync(process.execPath, [tscPath, "-p", testTsConfigPath], {
    cwd: rootDir,
    stdio: "inherit",
  });

  const compiledTestFiles = collectFiles(outDir, ".test.js");
  assertCompiledInventory(sourceTestFiles, compiledTestFiles, sourceDir, outDir);

  executeCompiledTests(compiledTestFiles, outDir);

  return compiledTestFiles.length;
}

if (require.main === module) {
  const testCount = runFrontendAssertions();
  console.log(`Ran ${testCount} frontend assertion files.`);
}

module.exports = {
  assertCompiledInventory,
  collectFiles,
  executeCompiledTests,
  relativeTestInventory,
  requireFiles,
  runFrontendAssertions,
};
