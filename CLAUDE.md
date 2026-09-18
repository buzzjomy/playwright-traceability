# Project Context for Claude Code

This file exists so a Claude Code session starting fresh in this repo has the
context that was worked out in a separate planning conversation. Read this
before making architectural decisions that contradict what's below — if
something here seems wrong given the current code, ask rather than silently
overriding it.

## What this is

A Playwright-native test management and requirements-traceability tool. The
core idea: teams using Playwright have no native way to see which Jira
requirements are actually covered by tests, whether that coverage is still
valid after a requirement changes, or whether test suites exist at all in a
parseable form. Existing tools either require manual re-entry into a
separate test management system (TestRail, Zephyr) or only check "is there
*a* linked test" without checking whether the test still matches what the
ticket asks for.

Builder context: solo developer (not a team), transitioning from a 19+ year
QA automation/test architecture career into building sellable products with
Claude Code. This is one venture under a "EDENTECH" umbrella, alongside a
white-label bakery app and a Moodle-based learning platform. Freelance/
Upwork work is also in the mix. Time and attention are split across
multiple things — favor scoping that ships an MVP fast over
gold-plating any one milestone.

## Why this product, and what was rejected

Two ideas were compared. A "flaky-test root-cause classifier" (diagnosing
*why* a test is flaky — async-state mismatch, shared-state pollution, CI
resource starvation, etc.) was rejected because it needs a training/labeled
dataset of test logs that isn't available. This traceability tool was
chosen instead because it's buildable from static analysis + LLM comparison
of text, with no training data requirement.

## The differentiator (don't lose sight of this)

Existing open-source tools (SAP's Continuous Traceability Monitor, Kiwi TCMS
+ requirements plugin) only check "is a test tagged to this Jira key."
Neither checks whether the test's actual content still matches the
requirement's actual content. The planned differentiator is:

1. **Semantic gap detection** — LLM comparison of a Jira ticket's
   acceptance criteria against the titles/assertions of its linked tests,
   flagging specific uncovered criteria (not just "ticket has >=1 test").
2. **Suspect-link detection** — hash a requirement's substantive fields
   (description, AC) at link time; when Jira content changes, flip linked
   tests to a "Suspect" state until a human reviews and re-confirms them.
   This must stay human-in-the-loop on purpose — auto-clearing the flag
   would hide the exact problem this feature exists to surface.

## Tech stack

- **Backend:** FastAPI (Python) — built, see `backend/`.
- **Database:** Postgres — stores test inventory, run history, and
  requirement↔test link state (Covered / Suspect / Stale / Orphaned).
  Currently defaults to local SQLite via `DATABASE_URL` for zero-setup
  dev; swapping in a Postgres connection string needs no code changes
  (see `backend/README.md` for why).
- **Frontend:** React (dashboard) — built with Vite + TypeScript, see
  `frontend/`. Deliberately minimal so far: no router (tabs via local
  component state), no state management library, no CSS/component
  framework.
- Jira auth is **API token + email over HTTP Basic Auth**, not OAuth
  2.0 — OAuth was deferred (needs a registered app + public redirect
  URI, real overhead before there's even a backend deployed anywhere).
  See `backend/README.md` for the full reasoning; revisit if this ever
  needs to become a real multi-tenant "Connect your Jira" product.
- Chosen to match the stack already used on the bakery app project, so
  there's no new stack to learn mid-build.

## Milestone plan (tracked in GitHub Issues/Milestones, not Jira)

Deliberately using GitHub Issues on this repo instead of Jira for planning
this project itself — solo builder, no team to coordinate, and it avoids
the irony of needing this not-yet-built tool's own target integration just
to plan the build.

1. **Test Inventory** — parse Playwright JSON reporter output (primary
   source of truth — always has real, resolved test titles regardless of
   how tests were authored) + static `.spec.ts` AST parsing (enrichment:
   tags, `Trace(...)` annotations) + `.feature` file parsing for BDD teams.
   Must gracefully handle teams with zero existing Playwright suite.
2. **Jira Integration** — REST API auth, pull requirement/story data,
   two ways to link tests to requirements (inline code annotation like
   `Trace(Jira:PROJ-13)`, or a JSON mapping file for teams that won't touch
   test code), webhook subscription for live updates with polling fallback.
3. **Traceability Dashboard** — read-only views: test inventory,
   requirement coverage (which Jira keys have zero linked tests), pass/fail
   trends, flaky-test flagging.
4. **Requirement-Change Detection** — the suspect-link mechanism described
   above.
5. **Semantic Gap Detection** — the LLM-based differentiator described
   above. Per-criterion tracking (vs. whole-ticket) is v2.
6. **Defect Linking (v2)** — auto-file a ticket when a previously-passing,
   requirement-linked test fails N times in a row.

Build order: 1 → 2 → 3 first (gets to a demoable product without needing
the LLM layer yet), then 4, then 5 (the actual moat), then 6 last.

## A known gap to design around

Not all teams write tests as plain hand-authored `.spec.ts` files:
- **BDD/Cucumber (playwright-bdd)** — human-readable scenarios live in
  `.feature` files; actual Playwright code is in separate step definitions.
- **Data-driven/generated tests** — a single `test()` call inside a loop
  produces many real test titles only visible in the *run report*, not in
  static source.
- **No-code layers on top of Playwright** (QA Wolf, Shiplight, Checkly) —
  no local spec file exists at all; would need per-platform API integration
  if ever supported.

This is why the JSON reporter output is the primary parse target, not
`.spec.ts` source — see `README.md` for the reasoning already written up
for Milestone 1.

## Current status (last updated 2026-09-18)

**Milestone 1 (Test Inventory): fully done, issues #1-#5.** Three parsers
(`parser/report_parser.py`, `parser/static_parser.py` + real TypeScript
AST via Node, `parser/feature_parser.py` using `gherkin-official`) each
turn Playwright test data into structured records; all three degrade to
`[]` gracefully with no tests found. `scripts/push_test_inventory.py`
pushes all three to the backend. See `README.md` for field-level docs.

**Milestone 2 (Jira Integration): fully done, issues #6-#11.** First
backend service (`backend/`, FastAPI + SQLAlchemy). Covers Jira Cloud
auth + connection setup, pulling requirement/story data (with parsed
Acceptance Criteria — there's no dedicated AC field on Jira Cloud; ACs
are parsed from a heading + bullet list in the description), an ingest
endpoint for pushed test data, receiving Jira webhook events, and a
polling fallback for instances without webhook access. Issue #8
(code-annotation linking) needed zero new code — Milestone 1's parsers
already covered it. See `backend/README.md` for the real Jira API
findings this surfaced (a removed search endpoint, webhook
self-registration needing OAuth, a JQL date-literal bug) and how each was
verified against the live Jira site, not just mocks.

**Milestone 3 (Traceability Dashboard): fully done, issues #12-#15.**
First frontend (`frontend/`, Vite + React + TypeScript): a test inventory
view (issue #12 — this is also where `TestRecord`/`StaticTestRecord`
reconciliation, mentioned as a design question in earlier planning,
actually got built: a plain `(file, title)` match), a requirement
coverage view (issue #13), a per-test pass/fail trend (issue #14 —
`TestRunRecord`'s already-append-only history rendered as a row of
colored dots on the inventory table, no new model needed), and flaky-run
flagging (issue #15 — Playwright's own retry-based `test.status ==
"flaky"`, parsed since Milestone 1 but not surfaced until now).
Milestone 3 is complete.

**Milestone 4 (Requirement-Change Detection): fully done, issues #16-#20.**
The suspect-link mechanism this product exists to differentiate on. A new
persisted `RequirementLink` table hashes a requirement's substantive
fields (summary/description/AC) the first time a test is seen linking to
it (issue #16); the webhook and polling delivery paths both feed a shared
`detect_drift_for_issue` (issue #17) that re-pulls live content and flips
a link to Suspect on a hash mismatch. `stale`/`orphaned` (issue #18) are
derived at read time from current inventory/Jira data rather than stored,
since only Suspect needs event-driven detection. Issue #19 (an LLM
plain-language "what changed" summary, via `claude-opus-5`) is enrichment
only - it's skipped gracefully without `ANTHROPIC_API_KEY` and never blocks
the Suspect flag itself. Issue #20's manual "Reviewed" action is the only
way a Suspect link is ever cleared - no auto-clear path exists anywhere,
on purpose. Surfaced in the dashboard as a "Link Health" table below the
existing coverage view. See `backend/README.md`'s "Requirement-change
detection and suspect links" section for the full design, and verified
end-to-end against the real `demo/google-search` Jira project (KAN-4
manually flipped to Suspect, then cleared via a real "Mark reviewed" call
that re-pulled live Jira content).

Next up is Milestone 5 (Semantic Gap Detection - the actual moat).

**Real demo data exists** for testing all of the above against a real
Jira site, not synthetic fixtures: `demo/google-search/` — 10 real Story
issues in Jira (project "KAN"/"DevTest") with real Acceptance Criteria,
plus 10 real Playwright tests against live google.com, linked via plain
`// KAN-4`-style comments. There's also a real-Jira integration test
suite (`tests/integration/`, skipped without credentials) and a daily
scheduled GitHub Action running it, added after a real bug (an absolute
JQL date literal that silently matched nothing) slipped past every mocked
test — see `tests/integration/README.md`.

Full backlog for all 6 milestones is in this repo's GitHub Issues, labeled
`mvp` or `v2`. Milestones 4 (Requirement-Change Detection) and 5
(Semantic Gap Detection — the actual differentiator) haven't started.
