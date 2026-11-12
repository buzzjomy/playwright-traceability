"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");
const { findRepoRoot, toRepoRelative } = require("../src/paths");

test("findRepoRoot finds the nearest ancestor with .git", () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "repo-")));
  fs.mkdirSync(path.join(root, ".git"));
  fs.mkdirSync(path.join(root, "a", "b"), { recursive: true });
  assert.equal(findRepoRoot(path.join(root, "a", "b")), root);
});

test("findRepoRoot is null when no ancestor has .git", () => {
  const lonely = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "norepo-")));
  assert.equal(findRepoRoot(lonely), null);
});

test("toRepoRelative makes forward-slash repo-relative paths", () => {
  const root = path.join(path.sep, "repo");
  assert.equal(toRepoRelative(path.join(root, "tests", "a.spec.ts"), root), "tests/a.spec.ts");
});

test("toRepoRelative leaves paths alone with no repo root or outside it", () => {
  const outside = path.join(path.sep, "elsewhere", "a.spec.ts");
  assert.equal(toRepoRelative(outside, null), "/elsewhere/a.spec.ts");
  assert.equal(toRepoRelative(outside, path.join(path.sep, "repo")), "/elsewhere/a.spec.ts");
});
