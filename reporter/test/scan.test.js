"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");
const { findSpecFiles, scanSpecs } = require("../src/scan");

function project(files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "scan-"));
  for (const [name, content] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), content);
  }
  return root;
}

test("finds only .spec.ts files, skipping node_modules and dot-directories", () => {
  const root = project({ "a.spec.ts": "", "sub/b.spec.ts": "", "c.ts": "", "node_modules/x.spec.ts": "", ".hidden/y.spec.ts": "" });
  assert.deepEqual(findSpecFiles(root).map((f) => path.relative(root, f)), ["a.spec.ts", "sub/b.spec.ts"]);
});

test("returns the scanner's raw facts with repo-relative display paths", () => {
  const root = project({
    "tests/a.spec.ts": `import { test, expect } from "@playwright/test";\n// KAN-4\ntest("loads", async ({ page }) => { await expect(page).toHaveTitle(/Google/); });\n`,
  });
  const facts = scanSpecs(path.join(root, "tests"), root);
  assert.equal(facts.length, 1);
  assert.equal(facts[0].title, "loads");
  assert.equal(facts[0].file, "tests/a.spec.ts");
  assert.match(facts[0].leading_comment_text, /KAN-4/);
  assert.ok(facts[0].assertions.some((a) => a.includes("toHaveTitle")));
});

test("no specs (or no directory) is an empty scan", () => {
  assert.deepEqual(scanSpecs(path.join(os.tmpdir(), "does-not-exist-xyz"), null), []);
});
