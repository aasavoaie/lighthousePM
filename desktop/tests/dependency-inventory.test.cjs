const assert = require("node:assert/strict");
const test = require("node:test");

const {
  inventoryErrors,
  packageName,
  scanPackage,
} = require("../scripts/check-dependency-inventory.cjs");

test("current desktop dependency inventory passes", () => {
  assert.deepEqual(scanPackage(), []);
});

test("package names preserve scoped roots and exclude local and Node imports", () => {
  assert.equal(packageName("@electron-forge/maker-zip"), "@electron-forge/maker-zip");
  assert.equal(packageName("electron/main"), "electron");
  assert.equal(packageName("../src/main.cjs"), null);
  assert.equal(packageName("node:test"), null);
});

test("ordinary runtime imports cannot rely on dev dependencies", () => {
  assert.deepEqual(
    inventoryErrors({
      configuredDevPackages: new Set(),
      devRuntimeExceptions: new Set(),
      imports: [{ file: "src/main.cjs", packageName: "runtime-package", runtime: true }],
      manifest: { dependencies: {}, devDependencies: { "runtime-package": "1.0.0" } },
    }),
    [
      "src/main.cjs: package 'runtime-package' is not declared as a direct runtime dependency",
    ]
  );
});

test("Electron may remain an explicit dev dependency for the packaged runtime", () => {
  assert.deepEqual(
    inventoryErrors({
      configuredDevPackages: new Set(),
      devRuntimeExceptions: new Set(["electron"]),
      imports: [{ file: "src/main.cjs", packageName: "electron", runtime: true }],
      manifest: { dependencies: {}, devDependencies: { electron: "1.0.0" } },
    }),
    []
  );
});

test("configured makers and command-only tools require direct declarations", () => {
  assert.deepEqual(
    inventoryErrors({
      configuredDevPackages: new Set(["cross-env"]),
      imports: [],
      makerPackages: new Set(["@electron-forge/maker-zip"]),
      manifest: { dependencies: {}, devDependencies: {} },
    }),
    [
      "package.json: configured build package '@electron-forge/maker-zip' is undeclared",
      "package.json: configured build package 'cross-env' is undeclared",
    ]
  );
});
