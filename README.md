# Playwright Report Parser (Milestone 1)

Covers the first issue of Milestone 1: *"Parse Playwright JSON reporter output
into structured test records (title, file, status, duration)."*

## Why parse the JSON reporter, not `.spec.ts` source files

The run report always contains real, resolved test titles and outcomes,
regardless of whether a test was hand-written, generated in a loop, or
authored through a BDD layer. Static source parsing (tags, `Trace(...)`
annotations, file location) is added as an **enrichment** layer on top of
this later — not as the primary source of truth. See the later issues in
Milestone 1 for that.

## Usage

```bash
# From your Playwright project:
npx playwright test --reporter=json > report.json

# From this project:
python -m parser.report_parser report.json
```

This prints a JSON array of flattened test records to stdout.

## What gets extracted per record

Each record is one **(spec × project)** combination — so a test that runs
under both `chromium` and `firefox` produces two records, since they can
have independently different outcomes.

| Field | Source |
|---|---|
| `title` / `full_title` | Spec title, with nested `describe` blocks and the file-level suite title joined by `>` |
| `file`, `line`, `column` | Spec location in source |
| `project` | Which Playwright project (browser) ran it |
| `tags` | Playwright's native `tags` field on the spec |
| `jira_keys` | Extracted from tags, `annotations`, and the title itself, matching patterns like `PROJ-13`, `@PROJ-13`, or `Jira:PROJ-13` |
| `status` | Final attempt's status (`passed`/`failed`/`timedOut`/etc) |
| `duration_ms` | Final attempt's duration |
| `retry_count` | Number of attempts beyond the first |
| `is_flaky` | True if any earlier attempt failed but the final attempt passed |
| `error_message` | First error message from the final attempt, if any |

## Design notes for whoever picks up the next issue

- `jira_keys` extraction currently only looks at tags/annotations/title on
  the JSON report. The next issue (static AST parser) should also catch
  `Trace(Jira:PROJ-13)`-style comments that don't show up in the run report
  at all (e.g. if the annotation isn't registered via `test.info().annotations`).
- `TestRecord` is a plain dataclass with no DB dependency on purpose — the
  Postgres model/ORM mapping should live in a separate module that imports
  this one, not be merged into it. Keeps this parseable/testable standalone.
- Multi-project specs are intentionally NOT collapsed into one record. If a
  test passes on chromium but fails on firefox, that's a real signal the
  dashboard (Milestone 3) needs to show separately, not average away.

## Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

14 tests, covering: nested describe flattening, multi-project specs,
retry/flakiness detection, and Jira key extraction across tag/annotation/
title sources.
