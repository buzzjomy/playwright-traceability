# Real-Jira Integration Tests

Regression tests against a real, live Jira Cloud site — not mocks.

## Why this exists

Issue #11's first polling implementation built an absolute JQL date
literal (`updated >= "2026-09-17 07:28"`). It looked completely
reasonable, and every mocked unit test for it passed. Tested against the
real Jira API, it **silently matched zero issues** — no error, just
nothing, forever. Every mocked test in `tests/` encodes *our own*
assumptions about how Jira behaves; none of them can catch Jira's *actual*
behavior diverging from those assumptions. This suite exists specifically
to catch that class of bug — see `test_real_jira.py`'s module docstring
for the full story.

## What it's allowed to do

Unlike the rest of this repo's tests, these are allowed to make real
writes — but only to one dedicated scratch issue (`KAN-14`,
"`[Integration Test Scratch Issue - DO NOT EDIT MANUALLY]`"), never to the
real demo data in `KAN-4`..`KAN-13`. `test_polling_detects_a_real_change`
edits that scratch issue's summary with a fresh nonce on every run, to
produce a genuine `updated` timestamp change for polling to detect —
there's no way to test "does polling actually detect a change" without
actually making one.

## Running locally

Requires real credentials as environment variables — never commit these,
never paste them into chat/logs:

```bash
export JIRA_SITE_URL="https://your-site.atlassian.net"
export JIRA_EMAIL="you@example.com"
export JIRA_API_TOKEN="..."          # from id.atlassian.com
export JIRA_TEST_PROJECT_KEY="KAN"   # defaults to KAN if omitted
export JIRA_TEST_ISSUE_KEY="KAN-14"  # the dedicated scratch issue

python -m pytest tests/integration/ -v
```

Without those set, every test in this directory **auto-skips** (see
`conftest.py`) — running the normal `pytest tests/` suite is completely
unaffected whether or not real credentials are available, so this never
blocks a contributor who doesn't have them.

## Running in CI

`.github/workflows/real-jira-integration.yml` runs this suite daily
(and on manual trigger) using repo secrets/variables for the credentials
above, so a future Jira API change gets noticed automatically instead of
waiting for the next time someone happens to touch this code.
