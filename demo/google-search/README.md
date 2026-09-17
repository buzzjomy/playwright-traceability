# Google Search Demo

A small real Playwright project testing google.com, written to generate
realistic data for testing Milestone 2 issue #7 (pulling requirement/story
data from Jira) against 10 real Jira stories — not synthetic fixtures like
`samples/`.

## The 10 requirements

Created in the `KAN` (DevTest) project on the real Jira site this repo is
connected to. Each has a description + Acceptance Criteria written in
proper Jira ADF, matching what a real ticket looks like (also useful later
for Milestone 5's semantic gap detection, which compares AC text against
test content).

| Jira key | Summary | Covered by |
|---|---|---|
| KAN-4 | Google homepage displays search box and logo | `tests/homepage.spec.ts` |
| KAN-5 | User can search and see results | `tests/search.spec.ts` |
| KAN-6 | Search box shows autocomplete suggestions while typing | `tests/search.spec.ts` |
| KAN-7 | "I'm Feeling Lucky" navigates directly to a result | `tests/results-filters.spec.ts` |
| KAN-8 | Search results page shows filter tabs (All, Images, News, Videos) | `tests/results-filters.spec.ts` |
| KAN-9 | Homepage footer exposes legal and info links | `tests/homepage.spec.ts` |
| KAN-10 | Interface language can be changed from the homepage | `tests/homepage.spec.ts` |
| KAN-11 | User can clear and re-run a search from the results page | `tests/search.spec.ts` |
| KAN-12 | Images tab displays a grid of image thumbnails | `tests/results-filters.spec.ts` |
| KAN-13 | Sign in link is visible for a logged-out visitor | `tests/homepage.spec.ts` |

## A finding worth noting: issue #8 may already be done

Each test has a plain `// KAN-4`-style comment above it, not the
`Trace(Jira:PROJ-13)` wrapper syntax the Milestone 1 issues originally
described. Running `parser.static_parser` against this directory already
correctly extracts all 10 keys — its `extract_jira_keys` regex matches a
bare issue key with no special wrapper required. So issue #8 ("code-
annotation linking parser") may need little to no new code — check this
before building it from scratch.

## Running these tests

```bash
npm install
npx playwright test --list   # validates syntax + discovery without hitting the network
npx playwright test          # actually runs against live https://www.google.com
```

**Known risk:** these hit the real, live google.com, not a sandbox. Google
actively challenges automated traffic (CAPTCHA / "unusual traffic"
interstitials), so runs can be flaky or blocked outright, especially from
a CI/cloud IP or when run repeatedly in a short window. Selectors here are
a best-effort based on Google's current DOM and may need adjustment if
Google's markup has changed since these were written. This is expected
and fine for this demo's purpose (generating realistic Jira + spec-file
data), not a target for 100% reliably green CI.

## Using this to test issue #7

Once issue #7 (pulling requirement/story data) exists, point it at this
repo's Jira connection and pull the `KAN` project - these 10 real stories,
with real descriptions and Acceptance Criteria, are the test data. If
issue #7 needs a run report too, use `parser.report_parser` /
`scripts/push_test_inventory.py` against this project's own `report.json`
after a real (or partial/flaky) run — a mix of pass/fail/blocked results
is realistic and fine for that purpose.
