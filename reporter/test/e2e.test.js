"use strict";
// Runs the REAL Playwright against test/fixture with the reporter attached and
// a fake backend, and checks what was uploaded. Set UPDATE_FIXTURE=1 to rewrite
// the sample payload the Python backend tests are checked against.
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const { after, before, test } = require("node:test");

const FIXTURE = path.join(__dirname, "fixture");
const SAMPLE = path.join(__dirname, "sample-payload.json");

let server;
let requests;
let port;

before(async () => {
  requests = [];
  server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      requests.push({ url: req.url, auth: req.headers.authorization, body: body ? JSON.parse(body) : null });
      const status = req.headers.authorization === "Bearer good-key" ? 200 : 401;
      res.writeHead(status, { "content-type": "application/json" });
      res.end(JSON.stringify(status === 200 ? { ok: true } : { detail: "Missing or invalid API key" }));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  port = server.address().port;
});
after(() => server.close());

/** Run the fixture suite in a child process (async, so the fake server can answer). */
function runPlaywright(env, options = {}) {
  return new Promise((resolve) => {
    const { spawn } = require("node:child_process");
    const child = spawn(process.execPath, [require.resolve("@playwright/test/cli"), "test", "--config", path.join(FIXTURE, "playwright.config.js")], {
      cwd: FIXTURE,
      env: { ...process.env, TRACEABILITY_TEST_OPTIONS: JSON.stringify(options), TRACEABILITY_INGEST_KEY: "", INGEST_API_KEY: "", ...env },
    });
    let output = "";
    child.stdout.on("data", (c) => (output += c));
    child.stderr.on("data", (c) => (output += c));
    child.on("close", (code) => resolve({ code, output }));
  });
}

test("uploads results and a source scan, and does not change the run's exit code", async () => {
  requests.length = 0;
  const { code, output } = await runPlaywright({ TRACEABILITY_INGEST_KEY: "good-key", TRACEABILITY_URL: `http://127.0.0.1:${port}` });

  assert.equal(code, 1, "the suite has an always-failing test, so Playwright itself must still exit 1\n" + output);
  assert.match(output, /\[traceability\] uploaded \d+ test results/);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "/api/ingest/playwright");
  assert.equal(requests[0].auth, "Bearer good-key");

  const { report, static_facts: facts } = requests[0].body;
  const specs = report.suites.flatMap((s) => [...s.specs, ...s.suites.flatMap((d) => d.specs)]);
  const byTitle = Object.fromEntries(specs.map((s) => [s.title, s]));

  // Two projects were configured, so each spec carries two `tests` entries.
  assert.deepEqual(byTitle["passes everywhere"].tests.map((t) => t.projectName), ["alpha", "beta"]);
  assert.equal(byTitle["passes everywhere"].tests[0].status, "expected");
  assert.equal(byTitle["fails always"].tests[0].status, "unexpected");
  assert.equal(byTitle["fails always"].tests[0].results.length, 2); // 1 retry configured
  assert.equal(byTitle["flaky until retried"].tests[0].status, "flaky");
  assert.equal(byTitle["is skipped"].tests[0].status, "skipped");
  assert.deepEqual(byTitle["fails always"].tags, ["@broken"]);
  assert.deepEqual(byTitle["has a Jira annotation"].tests[0].annotations, [{ type: "jira", description: "SHOP-7" }]);
  assert.match(byTitle["passes everywhere"].file, /reporter\/test\/fixture\/tests\/basic\.spec\.ts$/); // repo-relative

  // The scan found the test definitions, including one with a Jira comment.
  const passes = facts.find((f) => f.title === "passes everywhere");
  assert.match(passes.leading_comment_text, /KAN-4/);
  assert.equal(passes.file, byTitle["passes everywhere"].file); // same string -> reconciles

  if (process.env.UPDATE_FIXTURE) fs.writeFileSync(SAMPLE, JSON.stringify(requests[0].body, null, 2) + "\n");
});

test("with no key it skips with a hint and uploads nothing", async () => {
  requests.length = 0;
  const { output } = await runPlaywright({});
  assert.match(output, /\[traceability\] skipped: set TRACEABILITY_INGEST_KEY/);
  assert.equal(requests.length, 0);
});

test("a wrong key is reported clearly and the run is unaffected", async () => {
  const { code, output } = await runPlaywright({ TRACEABILITY_INGEST_KEY: "wrong", TRACEABILITY_URL: `http://127.0.0.1:${port}` });
  assert.equal(code, 1);
  assert.match(output, /ingest key is missing or wrong/);
});

test("an unreachable server is a warning, not a failure of the reporter", async () => {
  const { code, output } = await runPlaywright({ TRACEABILITY_INGEST_KEY: "k", TRACEABILITY_URL: "http://127.0.0.1:1" });
  assert.equal(code, 1);
  assert.match(output, /upload failed/);
});

test("scanSpecs: false uploads results only, leaving the source snapshot untouched", async () => {
  requests.length = 0;
  await runPlaywright({ TRACEABILITY_INGEST_KEY: "good-key", TRACEABILITY_URL: `http://127.0.0.1:${port}` }, { scanSpecs: false });
  assert.equal(requests[0].body.static_facts, null);
});

test("outputFile writes the payload for debugging, without needing a key", async () => {
  const out = path.join(os.tmpdir(), `payload-${process.pid}.json`);
  await runPlaywright({}, { outputFile: out });
  const written = JSON.parse(fs.readFileSync(out, "utf8"));
  assert.ok(written.report.suites.length > 0 && Array.isArray(written.static_facts));
  fs.unlinkSync(out);
});
