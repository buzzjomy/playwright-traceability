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

- **Backend:** FastAPI (Python)
- **Database:** Postgres — stores test inventory, run history, and
  requirement↔test link state (Covered / Suspect / Stale / Orphaned)
- **Frontend:** React (dashboard)
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
`.spec.ts` source — see `parser/README.md` for the reasoning already
written up for Milestone 1.

## Current status

Milestone 1, issue 1 ("Parse Playwright JSON reporter output into
structured test records") is done: see `parser/report_parser.py`,
`parser/models.py`, `tests/test_report_parser.py` (14 passing tests), and
`samples/sample-report.json`. Read `README.md` in that same folder for
field-level documentation and design notes for whoever (Claude Code
included) picks up the next issue.

Remaining Milestone 1 issues, in the GitHub milestone "1. Test Inventory":
- Static AST parser for `.spec.ts` files (tags, file path, `Trace(...)`
  annotations) — needs to catch annotations that don't show up in the JSON
  run report at all.
- `.feature` file parser for BDD/Gherkin teams.
- Handle the zero-test-suite case gracefully in the dashboard.
- CLI or GitHub Action snippet so users can push run output to the service.

Full backlog for all 6 milestones is in this repo's GitHub Issues, labeled
`mvp` or `v2`.
