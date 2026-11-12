"use strict";

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const { toRepoRelative } = require("./paths");

const SCANNER = path.join(__dirname, "parse_specs.js");

/** Every `*.spec.ts` under `dir`, sorted for stable output (matches the Python CLI's rule). */
function findSpecFiles(dir) {
  const found = [];
  const walk = (current) => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith(".spec.ts")) found.push(full);
    }
  };
  if (fs.existsSync(dir)) walk(dir);
  return found.sort();
}

/**
 * Statically scan the specs under `dir` for test definitions, Jira comments
 * and assertions, returning the scanner's raw facts - the backend interprets
 * them (parser/static_parser.py's records_from_raw), so no business rule is
 * duplicated here. Paths are reported repo-relative. Returns [] for no specs.
 * Throws if the scanner itself fails; callers decide whether that matters.
 */
function scanSpecs(dir, repoRoot) {
  const files = findSpecFiles(dir);
  if (files.length === 0) return [];

  const pairs = files.map((f) => [f, toRepoRelative(f, repoRoot)]);
  const result = spawnSync(process.execPath, [SCANNER, "--stdin"], {
    cwd: __dirname,
    input: JSON.stringify(pairs),
    encoding: "utf8",
    maxBuffer: 256 * 1024 * 1024,
  });
  if (result.status !== 0) {
    throw new Error(`spec scanner exited with ${result.status}: ${(result.stderr || "").slice(0, 300)}`);
  }
  return JSON.parse(result.stdout);
}

module.exports = { scanSpecs, findSpecFiles };
