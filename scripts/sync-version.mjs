/**
 * Syncs the version from package.json into pyproject.toml.
 *
 * Called automatically after `changeset version` bumps package.json,
 * so that pyproject.toml always stays in sync.
 */
import { readFileSync, writeFileSync } from "node:fs";

const pkg = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8")
);
const version = pkg.version;

const pyprojectPath = new URL("../pyproject.toml", import.meta.url);
let pyproject = readFileSync(pyprojectPath, "utf8");

const versionPattern = /^(version\s*=\s*")([^"]+)(")/m;

if (!versionPattern.test(pyproject)) {
  console.error("Could not find version field in pyproject.toml");
  process.exit(1);
}

pyproject = pyproject.replace(versionPattern, `$1${version}$3`);
writeFileSync(pyprojectPath, pyproject);

console.log(`Synced version ${version} to pyproject.toml`);
