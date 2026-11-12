# playwright-traceability-reporter

A Playwright reporter that uploads your test results - and a scan of your spec
files - to **Playwright Traceability**, so each Jira requirement can be checked
against the tests that actually cover it. Add it to your config; there is no
script to run and nothing else to install.

> Status: not published to npm yet (`"private": true`). Until it is, install it
> from this repository (`npm install ./reporter`).

## Set up (2 minutes)

1. In Jira, open the Traceability app, go to **Settings** and choose
   **Generate ingest key**. Copy it - it is shown once.
2. Store it as a CI secret named `TRACEABILITY_INGEST_KEY`. **Do not** put it in
   `playwright.config.ts`: that file is committed.
3. Add the reporter:

```ts
// playwright.config.ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  reporter: [["list"], ["playwright-traceability-reporter"]],
});
```

That's all. After each run, the results appear in the app's Test Inventory, and
Jira keys found in your tests link them to requirements.

## What it sends

- **The run:** each test's title, file, project, tags, annotations, final
  status, retries, duration and first error message.
- **A scan of your `*.spec.ts` files:** test titles, the comment just above a
  test (where `// KAN-4` is picked up), tags, and the text of `expect(...)`
  calls - which is what lets the app check whether a requirement's acceptance
  criteria are really asserted.

It does **not** send your source code beyond those assertion lines, your test
output, traces, screenshots or environment variables.

## Linking tests to Jira requirements

Any of these work, anywhere in a test's title, tags, annotations or the comment
above it: `// KAN-4`, `@KAN-4`, `Jira:KAN-4`,
`test.info().annotations.push({ type: "jira", description: "KAN-4" })`.

## Options

```ts
reporter: [["playwright-traceability-reporter", {
  url: "https://your-backend.example.com", // default: the hosted service
  specsDir: "tests",      // default: your testDir
  scanSpecs: false,       // upload results only, leave the source scan as it was
  outputFile: "payload.json", // also write what would be sent, for debugging
  timeoutMs: 20000,
}]]
```

Environment: `TRACEABILITY_INGEST_KEY` (or `INGEST_API_KEY`), `TRACEABILITY_URL`.

## It never fails your run

The reporter prints one `[traceability] ...` line and **never changes your
tests' exit code**. A missing key, a wrong key, an unreachable server or a scan
error is a warning. With no key set it uploads nothing, so local runs are fine.

## Good to know

- **Sharding:** each shard uploads its own results; the app keeps the latest
  result per test, so a full set of shards ends up complete.
- **Static scan covers `*.spec.ts`.** Tests with a dynamically built title
  (inside a loop) still appear from the run; they just have no source scan.
  `.feature` files and a Jira mapping file are handled by the Python CLI
  (`scripts/push_test_inventory.py`).
- Needs Node 18+ and `@playwright/test` 1.42+.

## How it fits together

The reporter sends the *raw* material (a report in Playwright's JSON-reporter
shape, and the scanner's raw facts) to `POST /api/ingest/playwright`. The
backend interprets both with the same Python parsers as the CLI, so there is one
copy of the rules. `src/parse_specs.js` is a copy of `static_parser/parse_specs.js`;
a test keeps them identical.

## Development

```bash
cd reporter && npm install && npm test
UPDATE_FIXTURE=1 npm test   # regenerate test/sample-payload.json (the Python tests use it)
```
