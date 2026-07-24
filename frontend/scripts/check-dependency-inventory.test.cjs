const assert = require("node:assert/strict");
const test = require("node:test");

const {
  inventoryErrors,
  packageName,
  scanPackage,
} = require("./check-dependency-inventory.cjs");

test("current frontend dependency inventory passes", () => {
  assert.deepEqual(scanPackage(), []);
});

test("package names preserve scoped roots and exclude local and built-in imports", () => {
  assert.equal(packageName("@scope/package/subpath"), "@scope/package");
  assert.equal(packageName("react-dom/client"), "react-dom");
  assert.equal(packageName("./local-module"), null);
  assert.equal(packageName("node:path"), null);
});

test("runtime imports require runtime dependency declarations", () => {
  assert.deepEqual(
    inventoryErrors({
      configuredDevPackages: new Set(),
      imports: [{ file: "src/main.tsx", packageName: "react", runtime: true }],
      manifest: { dependencies: {}, devDependencies: { react: "1.0.0" } },
    }),
    ["src/main.tsx: package 'react' is not declared as a direct runtime dependency"]
  );
});

test("component tests and test support may use declared dev dependencies", () => {
  assert.deepEqual(
    inventoryErrors({
      configuredDevPackages: new Set(),
      imports: [
        { file: "src/example.component.test.tsx", packageName: "vitest", runtime: false },
        { file: "src/test/setup.ts", packageName: "jest-axe", runtime: false },
      ],
      manifest: {
        dependencies: {},
        devDependencies: { "jest-axe": "1.0.0", vitest: "1.0.0" },
      },
    }),
    []
  );
});

test("configured command-only packages must be explicit dev dependencies", () => {
  assert.deepEqual(
    inventoryErrors({
      configuredDevPackages: new Set(["typescript"]),
      imports: [],
      manifest: { dependencies: {}, devDependencies: {} },
    }),
    ["package.json: configured test/build package 'typescript' is undeclared"]
  );
});
