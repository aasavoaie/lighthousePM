const fs = require("node:fs");
const { builtinModules } = require("node:module");
const path = require("node:path");

const PACKAGE_ROOT = path.resolve(__dirname, "..");
const CONFIGURED_DEV_PACKAGES = new Set([
  "@electron-forge/cli",
  "concurrently",
  "cross-env",
  "wait-on",
]);
const DEV_RUNTIME_EXCEPTIONS = new Set(["electron"]);
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
    } else if (entry.isFile() && [".cjs", ".js", ".mjs"].includes(path.extname(entry.name))) {
      files.push(entryPath);
    }
  }
  return files;
}

function importedSpecifiers(filePath) {
  const source = fs.readFileSync(filePath, "utf8");
  const patterns = [
    /\brequire\s*\(\s*["']([^"']+)["']\s*\)/g,
    /\bimport\s*\(\s*["']([^"']+)["']\s*\)/g,
  ];
  const specifiers = [];
  for (const pattern of patterns) {
    for (const match of source.matchAll(pattern)) {
      specifiers.push(match[1]);
    }
  }
  return [...new Set(specifiers)].sort();
}

function configuredMakerPackages(forgeConfigPath) {
  const source = fs.readFileSync(forgeConfigPath, "utf8");
  return new Set(
    [...source.matchAll(/\bname\s*:\s*["'](@electron-forge\/maker-[^"']+)["']/g)].map(
      (match) => match[1]
    )
  );
}

function inventoryErrors({
  manifest,
  imports,
  configuredDevPackages = CONFIGURED_DEV_PACKAGES,
  devRuntimeExceptions = DEV_RUNTIME_EXCEPTIONS,
  makerPackages = new Set(),
}) {
  const runtimeDeclared = new Set(Object.keys(manifest.dependencies || {}));
  const devDeclared = new Set(Object.keys(manifest.devDependencies || {}));
  const configuredPackages = new Set([...configuredDevPackages, ...makerPackages]);
  const used = new Set(configuredPackages);
  const errors = [];

  for (const imported of imports) {
    used.add(imported.packageName);
    const devRuntimeAllowed = devRuntimeExceptions.has(imported.packageName);
    const declared = imported.runtime && !devRuntimeAllowed
      ? runtimeDeclared.has(imported.packageName)
      : runtimeDeclared.has(imported.packageName) || devDeclared.has(imported.packageName);
    if (!declared) {
      const scope = imported.runtime && !devRuntimeAllowed ? "runtime" : "runtime or dev";
      errors.push(
        `${imported.file}: package '${imported.packageName}' is not declared as a direct ${scope} dependency`
      );
    }
  }

  for (const packageName of [...configuredPackages].sort()) {
    if (!devDeclared.has(packageName)) {
      errors.push(`package.json: configured build package '${packageName}' is undeclared`);
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
  const forgeConfigPath = path.join(root, "forge.config.cjs");
  const files = [
    ...collectFiles(path.join(root, "src")),
    ...collectFiles(path.join(root, "scripts")),
    ...collectFiles(path.join(root, "tests")),
    forgeConfigPath,
  ]
    .filter((filePath) => fs.existsSync(filePath))
    .sort();
  const imports = [];
  for (const filePath of files) {
    const relativePath = path.relative(root, filePath).split(path.sep).join("/");
    const runtime = relativePath.startsWith("src/");
    for (const specifier of importedSpecifiers(filePath)) {
      const importedPackage = packageName(specifier);
      if (importedPackage) {
        imports.push({ file: relativePath, packageName: importedPackage, runtime });
      }
    }
  }
  const manifest = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
  const makerPackages = configuredMakerPackages(forgeConfigPath);
  return inventoryErrors({ manifest, imports, makerPackages });
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
  console.log("Desktop dependency inventory passed.");
}

module.exports = {
  configuredMakerPackages,
  importedSpecifiers,
  inventoryErrors,
  packageName,
  scanPackage,
};

if (require.main === module) {
  main();
}
