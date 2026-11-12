"use strict";
const assert = require("node:assert/strict");
const path = require("node:path");
const { test } = require("node:test");
const { buildReport } = require("../src/serialize");

const ROOT = path.join(path.sep, "repo");
const file = (name) => path.join(ROOT, "tests", name);

/** A minimal stand-in for Playwright's Suite/TestCase objects. */
function fakeSuite(tests) {
  return { allTests: () => tests };
}
function fakeTest({ title, projects = "chromium", describes = [], file: f = "a.spec.ts", line = 3, tags = [], annotations = [], outcome = "expected", results = [{ status: "passed", duration: 10.4, errors: [] }], id = "id" }) {
  let parent = { type: "project", title: projects, parent: { type: "root" } };
  for (const d of describes) parent = { type: "describe", title: d, parent };
  return { id, title, location: { file: file(f), line, column: 1 }, parent, tags, annotations, outcome: () => outcome, results };
}

test("one spec per test with a tests entry per project, like the JSON reporter", () => {
  const report = buildReport(fakeSuite([fakeTest({ title: "t", projects: "chromium" }), fakeTest({ title: "t", projects: "firefox" })]), ROOT);
  assert.equal(report.suites.length, 1);
  const spec = report.suites[0].specs[0];
  assert.deepEqual(spec.tests.map((t) => t.projectName), ["chromium", "firefox"]);
  assert.equal(spec.file, "tests/a.spec.ts"); // repo-relative, forward slashes
  assert.equal(report.suites[0].title, "tests/a.spec.ts");
});

test("describe blocks nest suites; different lines are different specs", () => {
  const report = buildReport(fakeSuite([fakeTest({ title: "x", describes: ["Outer", "Inner"] }), fakeTest({ title: "x", line: 9 })]), ROOT);
  const top = report.suites[0];
  assert.equal(top.specs.length, 1);
  assert.equal(top.suites[0].title, "Outer");
  assert.equal(top.suites[0].suites[0].title, "Inner");
  assert.equal(top.suites[0].suites[0].specs[0].title, "x");
});

test("keeps outcome, retries, rounded durations, tags, annotations and error messages", () => {
  const results = [
    { status: "failed", duration: 5.6, errors: [{ message: "boom", stack: "ignored" }] },
    { status: "passed", duration: 7.2, errors: [] },
  ];
  const report = buildReport(
    fakeSuite([fakeTest({ title: "flaky", outcome: "flaky", results, tags: ["@smoke"], annotations: [{ type: "jira", description: "KAN-4" }] })]),
    ROOT,
  );
  const spec = report.suites[0].specs[0];
  const t = spec.tests[0];
  assert.equal(t.status, "flaky");
  assert.deepEqual(t.results.map((r) => [r.status, r.duration]), [["failed", 6], ["passed", 7]]);
  assert.deepEqual(t.results[0].errors, [{ message: "boom" }]);
  assert.deepEqual(spec.tags, ["@smoke"]);
  assert.deepEqual(t.annotations, [{ type: "jira", description: "KAN-4" }]);
});

test("no tests is an empty report, not an error", () => {
  assert.deepEqual(buildReport(fakeSuite([]), ROOT), { suites: [] });
});
