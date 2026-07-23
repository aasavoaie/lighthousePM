const fs = require("node:fs");
const { builtinModules } = require("node:module");
const path = require("node:path");
const ts = require("typescript");

const PACKAGE_ROOT = path.resolve(__dirname, "..");
const CONFIGURED_DEV_PACKAGES = new Set([
  "@testing-library/dom",
  "@testing-library/user-event",
  "@types/react",
  "@types/react-dom",
  "@types/jest-axe",
  "jsdom",
  "typescript",
  "vite",
]);
const SOURCE_EXTENSIONS = new Set([".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"]);
const BUILTIN_MODULES = new Set(
  builtinModules.flatMap((moduleName) => [moduleName, `node:${moduleName}`])
);

function packageName(specifier) {
  if (
    !specifier ||
    specifier.startsWith(".") ||
    specifier.startsWith("/") ||
    specifier.startsWith("node:") ||
    BUILTIN_MODULES.has(specifier)
  ) {
    return null;
  }
  const parts = specifier.split("/");
  return specifier.startsWith("@") ? parts.slice(0, 2).join("/") : parts[0];
}

function collectFiles(directory) {
  if (!fs.existsSync(directory)) {
    return [];
  }
  const files = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectFiles(entryPath));
    } else if (entry.isFile() && SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
      files.push(entryPath);
    }
  }
  return files;
}

function importedSpecifiers(filePath) {
  const source = fs.readFileSync(filePath, "utf8");
  const preprocessed = ts.preProcessFile(source, true, true);
  const specifiers = preprocessed.importedFiles.map((entry) => entry.fileName);
  const requirePattern = /\brequire\s*\(\s*["']([^"']+)["']\s*\)/g;
  for (const match of source.matchAll(requirePattern)) {
    specifiers.push(match[1]);
  }
  return [...new Set(specifiers)].sort();
}

function inventoryErrors({ manifest, imports, configuredDevPackages = CONFIGURED_DEV_PACKAGES }) {
  const runtimeDeclared = new Set(Object.keys(manifest.dependencies || {}));
  const devDeclared = new Set(Object.keys(manifest.devDependencies || {}));
  const used = new Set(configuredDevPackages);
  const errors = [];

  for (const imported of imports) {
    used.add(imported.packageName);
    const declared = imported.runtime
      ? runtimeDeclared.has(imported.packageName)
      : runtimeDeclared.has(imported.packageName) || devDeclared.has(imported.packageName);
    if (!declared) {
      const scope = imported.runtime ? "runtime" : "runtime or dev";
      errors.push(
        `${imported.file}: package '${imported.packageName}' is not declared as a direct ${scope} dependency`
      );
    }
  }

  for (const packageName of [...configuredDevPackages].sort()) {
    if (!devDeclared.has(packageName)) {
      errors.push(`package.json: configured test/build package '${packageName}' is undeclared`);
    }
  }
  for (const packageName of [...runtimeDeclared, ...devDeclared].sort()) {
    if (!used.has(packageName)) {
      errors.push(`package.json: direct dependency '${packageName}' has no maintained use`);
    }
  }
  return [...new Set(errors)].sort();
}

function scanPackage(root = PACKAGE_ROOT) {
  const files = [
    ...collectFiles(path.join(root, "src")),
    ...collectFiles(path.join(root, "scripts")),
    path.join(root, "vite.config.ts"),
    path.join(root, "vitest.config.ts"),
  ]
    .filter((filePath) => fs.existsSync(filePath))
    .sort();
  const imports = [];
  for (const filePath of files) {
    const relativePath = path.relative(root, filePath).split(path.sep).join("/");
    const runtime =
      relativePath.startsWith("src/") &&
      !relativePath.startsWith("src/test/") &&
      !relativePath.endsWith(".test.ts") &&
      !relativePath.endsWith(".test.tsx");
    for (const specifier of importedSpecifiers(filePath)) {
      const importedPackage = packageName(specifier);
      if (importedPackage) {
        imports.push({ file: relativePath, packageName: importedPackage, runtime });
      }
    }
  }
  const manifest = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
  return inventoryErrors({ manifest, imports });
}

function main() {
  const errors = scanPackage();
  if (errors.length) {
    for (const error of errors) {
      console.error(error);
    }
    process.exitCode = 1;
    return;
  }
  console.log("Frontend dependency inventory passed.");
}

module.exports = { importedSpecifiers, inventoryErrors, packageName, scanPackage };

if (require.main === module) {
  main();
}
