"use strict";

const fs = require("fs");
const path = require("path");

/**
 * Walk upward from `start` looking for a `.git` entry; returns that directory
 * or null. Mirrors scripts/push_test_inventory.py's find_repo_root so a test
 * gets the same repo-relative path from the reporter as from the Python CLI -
 * which is what lets the backend reconcile a run with a source scan.
 */
function findRepoRoot(start) {
  let current = path.resolve(start);
  for (;;) {
    if (fs.existsSync(path.join(current, ".git"))) return current;
    const parent = path.dirname(current);
    if (parent === current) return null;
    current = parent;
  }
}

/**
 * `file` as a forward-slash path relative to `repoRoot`; unchanged (but
 * slash-normalised) if there is no repo root or the file lies outside it.
 */
function toRepoRelative(file, repoRoot) {
  const normalised = file.split(path.sep).join("/");
  if (!repoRoot) return normalised;
  const relative = path.relative(repoRoot, file);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return normalised;
  return relative.split(path.sep).join("/");
}

module.exports = { findRepoRoot, toRepoRelative };
