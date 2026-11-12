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
- Jira auth has two modes (`backend/jira_client.py`, chosen per request by
  `backend/jira_access.py`): **API token + email over HTTP Basic Auth** for
  local dev, the standalone `frontend/` and the owner's own tenant (OAuth 2.0
  was deferred - see `backend/README.md`), and the **Forge app system token**
  for every Marketplace customer (issue #41) - the app reads Jira as its own
  bot user, so a customer never hands over credentials.
- `reporter/` is a Node package (a Playwright reporter, issue #44), alongside
  the Python backend/parsers, the React `frontend/` and the Forge UI Kit
  `forge-app/`.
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

## A known scaling gap: the coverage/link dashboards assume a small project

`GET /api/coverage` and `GET /api/requirement-links` (Milestones 3 and 4)
both live-pull *every* requirement in a Jira project and return the whole
result in one JSON response; `CoverageView.tsx` renders all of it in one
unpaginated table, with no filtering beyond the project-key input. This is
fine at demo scale (`demo/google-search`'s 14 requirements) but breaks
down for a project with hundreds or thousands of requirements: a slow
full-project Jira pull and a huge payload on every load, and a table the
user has no way to narrow down beyond scrolling.

If this ever needs to support a real project at that scale, the fix is
server-side pagination and filtering on both endpoints (`page`/`page_size`
plus a `state=uncovered|suspect|gap` filter, most likely), with the
frontend becoming a paginated/filtered table driven by those params — not
just a client-side search box, which doesn't address the underlying
full-project fetch. Flagged here rather than built, since it's not needed
for the current MVP/demo scope — raised during a design discussion on
2026-09-18, not from an actual customer hitting this limit yet.

## Current status (last updated 2026-11-12, end of session)

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

**Milestone 5 (Semantic Gap Detection): issues #21/#22 done, #23 deferred
as v2 (as originally scoped).** The actual moat. The static parser now
also extracts each test's `expect(...)` assertion source text (issue #21,
static-only - `.feature` files can't statically resolve assertions, same
known gap as before), and `backend/semantic_gap.py` sends a requirement's
acceptance criteria plus its linked tests' titles/assertions to Claude,
judging each criterion covered/uncovered individually with a reason
(issue #22) - not just "this ticket has ≥1 test." Runs on-demand per
requirement (an "Analyze Gaps" button in the dashboard), since each call
is a real LLM request; there's no non-LLM fallback for this one (unlike
issue #19's enrichment-only change summary) - a `400`/`502` on
misconfiguration or a bad LLM response, never a silently-wrong verdict.
Issue #23 (persisting and suspect-tracking gap results per criterion, the
way issue #17 does for whole links) stays v2, unbuilt, per CLAUDE.md's
original scoping. Verified against real data: re-pushed
`demo/google-search`'s specs for real assertions, then confirmed KAN-4's
three criteria matched correctly to specific assertions, and a "Dummy"
criterion manually added to KAN-9 was correctly flagged as an uncovered
gap. See `backend/README.md`'s "Semantic gap detection" section for the
full design.

Milestone 6 (Defect Linking, v2) is what's left in the original 6-milestone
plan.

**Milestones 7-9 (Atlassian Forge app) are a new, additive track
(issues #25-#39; plan approved 2026-11-11).** `frontend/` (the standalone
dashboard) is NOT being replaced: `forge-app/` is a second frontend,
Forge **UI Kit** (not Custom UI), against the same FastAPI backend called
as a Forge **Remote**. Decided: Forge over Connect; UI Kit over Custom UI
(full rewrite - no CSS/JSX reuse, no custom hex colors, so the pale-yellow
row highlight etc. don't carry over); a Remote forfeits "Runs on
Atlassian" eligibility (accepted).

**Status: Milestones 7 and 8 done (#25-#34); Milestone 9 (Marketplace) is blocked on the Multi-Tenancy milestone.**
- #25/#26 `backend/forge_auth.py`: verifies Forge Invocation Tokens (RS256,
  Atlassian JWKS, `iss`/`aud`/`app.id`) on the 10 dashboard routes, off by
  default behind `REQUIRE_FORGE_AUTH` + `FORGE_APP_ID` (the full
  `ari:cloud:ecosystem::app/<uuid>` from `forge-app/manifest.yml`).
  Verified with a real token.
- #27 backend live on Fly.io: https://playwright-traceability.fly.dev
  (app `playwright-traceability`, region sin, Postgres `upg-ambered-dust-003`
  via psycopg v3, scale-to-zero). Manual `fly deploy` only - the
  auto-generated fly-deploy.yml was removed on purpose.
- #28 `forge-app/` installed on pwtrace.atlassian.net (development
  environment), verified end to end. `requestRemote()` runs in the BROWSER,
  so the backend has opt-in CORS (`CORS_ALLOW_ORIGINS` /
  `CORS_ALLOW_ORIGIN_REGEX`); the origin is the customer's own Jira site.
- #29 CI job `forge-app-lint` (npm ci + ESLint + `npm test`, Node 22, no
  secrets; `forge lint` needs a login so it is NOT in CI).
- #30 `InventoryView` ported to UI Kit (`forge-app/src/frontend/
  InventoryView.jsx`, pure logic in `lib/inventory.js` with `node --test`
  unit tests), deployed to development as 2.2.0 and visually verified.
- #31/#32 `CoverageView.jsx` ported (requirements table, Key-cell Button
  for selection - `primary` appearance when selected, detail panel with
  Analyze gaps / Show links / Close, link sub-table with Mark reviewed),
  pure logic in `lib/health.js`. Deployed as 2.4.0 and verified in Chrome
  against KAN (13 requirements; KAN-4 gap analysis returned 3 covered
  criteria).
- #33 `CoverageView` auto-detects the Jira project via `useProductContext`
  (`lib/projectContext.js`, `extension.project.key`); the Textfield is a
  manual override. Deployed as 2.5.0, verified in SAM1.
- #34 manual E2E pass done on the live site, including the full suspect
  flow: a Jira edit, then `POST /api/jira/poll` (needs INGEST_API_KEY as
  `Authorization: Bearer`; the FIRST poll only sets the baseline, so a
  change must come after it), then Suspect with an AI change summary, then
  "Mark reviewed", then Covered. Not exercised: the orphaned-row panel
  (logic is unit-tested; verify if orphaned data shows up).

**Current live state of the Fly deployment** (not in git): secrets set
there are DATABASE_URL, INGEST_API_KEY (was missing once; re-generated), the three JIRA_* ones,
REQUIRE_FORGE_AUTH=true, FORGE_APP_ID, CORS_ALLOW_ORIGINS=
https://pwtrace.atlassian.net. The demo project's data was pushed once
(`scripts.push_test_inventory` with demo/google-search report + specs, run
id 1). The Fly backend HAS a Jira connection (JIRA_SITE_URL, JIRA_EMAIL,
JIRA_API_TOKEN set as Fly secrets; the env bootstrap in `backend/main.py`
stored it on startup; verified - Jira keys in the Inventory tab render as
links), so Coverage (#31) has what it needs.

**Multi-tenancy is live (PR #48, deployed 2026-11-12).** Every table has a
`tenant_id`; the tenant is the verified Forge token's `app.installationId`
(`backend/tenancy.py`). The owner's install (`pwtrace`) is mapped to the
`local` tenant - where the env-bootstrapped Jira connection and the demo
data live - by the Fly secret `LOCAL_TENANT_INSTALLATION_ID` (its value is
shown in the app's Settings tab; it is an identifier, not a secret). Any
other installation is a fresh, empty tenant with no Jira connection.
Schema changes go through Alembic (`backend/migrations/`, run at startup;
the migrations are tested on a real Postgres in CI). CI uploads use
per-tenant keys generated in the Settings tab (hashed, shown once); the old
global `INGEST_API_KEY` still works and maps to the `local` tenant. The
classic Jira webhook only serves the `local` tenant.

**Product review (2026-11-12) re-ordered the plan.** Two new milestones:
- **Multi-Tenancy (#40-#43) - blocks Marketplace #37/#38.** #40
  (isolation), #41 (Jira via Forge's app system token) and #42 (per-tenant
  ingest keys + Settings tab) are DONE; #43 is half done. **#41 detail**
  (PRs #49/#51, verified live on pwtrace 2026-11-12): the frontend calls the
  backend with `invokeRemote` (NOT `requestRemote`, which carries no tokens)
  through a manifest `endpoint` with `auth.appSystemToken`; the backend uses
  that ~4h token + the verified FIT's `app.apiBaseUrl` as a Bearer
  credential, falling back to the tenant's stored Basic connection. **No
  token is ever stored** - each call/trigger/event delivers a fresh one.
  Drift detection for customers needs no webhook/polling script: an
  `avi:jira:updated:issue` trigger (`/api/forge/events/issue-updated`,
  verified live: edit -> Suspect in under a minute) plus an hourly
  `scheduledTrigger` (`/api/forge/scheduled/poll`, **NOT yet confirmed
  firing live** - check `fly logs` around the top of an hour). Forge gives
  event deliveries **5 seconds** and retries non-2xx 4x, so both routes ack
  immediately and work in a background task. Details: `backend/README.md`.
  **#43 (cold starts)**: `min_machines_running = 1` in `fly.toml` is
  deployed. The Postgres half is an unverified stopgap: the idle shutdown is
  the machine env var `FLY_SCALE_TO_ZERO` on `upg-ambered-dust-003`
  (unmanaged Fly Postgres, no longer maintained by Fly). Removing it needs
  `fly deploy`, which the $1 trial blocks (credit card), so it was raised
  from `1h` to `8760h` via `fly machine update -e`. Still to verify after
  >1h idle that the DB isn't Suspended. Real fix: add a card, remove the var,
  and move to Fly Managed Postgres before customers. Forge gives a call ~25s
  with no retry; first loads after idle took ~18s twice on 2026-11-11.
  **#50**: Analyze gaps took 20s+ on a tiny ticket - near that limit; needs
  start-and-poll before real use.
- **Adoption (#44-#47):** #44 DONE (below). Still open: a Jira issue panel
  showing per-ticket coverage/suspect/gaps (#45, mostly reuses #32); AI-
  suggested test-to-requirement links, human-accepted, never auto-linked
  (#46); and talking to 3-5 QA leads before Marketplace work (#47 - the
  interview guide and a 5-minute demo script are written, see
  `docs/customer-interview-guide.md` and `docs/demo-script.md`; the
  conversations themselves are the owner's to do).
- **#44 Playwright reporter (PR #52, merged 2026-11-12):** `reporter/` is a
  reporter you add to `playwright.config.ts` (`TRACEABILITY_INGEST_KEY` from
  the env, never the config). After a run it sends the results (built from
  Playwright's Suite API in the JSON-reporter shape) plus the raw facts of a
  `*.spec.ts` scan to `POST /api/ingest/playwright`, and the backend
  interprets both with the SAME Python parsers as the CLI
  (`parser.static_parser.records_from_raw`), so the rules live in one place.
  It never changes the run's exit code. `reporter/src/parse_specs.js` is a
  copy of `static_parser/parse_specs.js`; a test keeps them identical.
  Tests: 24 Node (incl. real Playwright vs a fake backend), 9 endpoint, 7
  cross-language checks against the committed real
  `reporter/test/sample-payload.json` (regenerate: `UPDATE_FIXTURE=1 npm
  test` in `reporter/`); CI job `reporter-tests`. **Open:** the package is
  `"private": true` - the npm name/scope is the owner's call and publishing is
  theirs; the backend needs a `fly deploy` for the endpoint (the Dockerfile
  now copies `parser/`); it has NOT been run against the live backend (needs
  a real ingest key from the Settings tab); the Settings tab still shows the
  Python CLI snippet and should switch to the reporter once it is published;
  `.feature` files and the Jira mapping file still go through the Python CLI.
- Positioning: Xray/Zephyr/AIO already import Playwright results into
  Jira. The pitch is "they make you maintain test cases in Jira; we read
  your actual tests and tell you when they no longer match the ticket."
  Strongest fit is regulated teams (medical, fintech, automotive) where
  traceability is mandatory.

**Next:** #47 (talk to 3-5 QA leads before more Marketplace work - the
owner's to do; the guide is ready), then #45/#46 (shape depends on what the
interviews say: they may favour the issue panel), Milestone 9 (#35-#39), #50
and the Postgres move from #43. Also still open from this session: verify the
hourly scheduled poll fires, and run the reporter against the live backend.

CORS is no longer needed for the Forge app now that
it uses `invokeRemote` (Forge proxies the call), so the earlier plan to
widen it to `https://<any>.atlassian.net` can be dropped - keep
`CORS_ALLOW_ORIGINS` only if the standalone frontend ever needs it.

**Working on forge-app - hard-won gotchas:**
- The Forge CLI needs Node 22/24: `export NVM_DIR="$HOME/.nvm" && source
  "$NVM_DIR/nvm.sh" && nvm use 22` (repo default Node 20 is unsupported).
  Deploy: `cd forge-app && npx @forge/cli deploy -e development
  --non-interactive`. Minor versions apply to the existing install
  automatically; new scopes/egress need `forge install --upgrade`. Always
  hard-reload (Cmd+Shift+R) the Jira tab after a deploy.
- Claude cannot do `forge login`, `fly ...` commands, or anything needing
  the user's credentials/TTY. The user runs those in their own terminal and
  pastes back non-secret output. NEVER ask for or accept real secrets/tokens
  in chat (INGEST_API_KEY, Jira/Anthropic/Fly/Atlassian tokens).
- Developer Space: `hazeltech` (id 510f3c41-5b47-4c2e-bed3-99986d4b4c4f);
  non-interactive `forge create` needs `-s <id> -y`.
- Manifest changes that add scopes are a MAJOR version: `forge deploy`
  fails with an approval note until you add `--approve MAJOR_VERSION_RULE`,
  and the install keeps running the old major until the user runs `forge
  install --upgrade -e development` (via `npx @forge/cli`, there is no global
  `forge`). New modules without new scopes deploy as a minor version.
  `npx @forge/cli lint` works from this shell (it is just not in CI).
- A frontend `invokeRemote` returns `{status, headers, body}`, not a fetch
  `Response`. Event/scheduled triggers call a backend `route.path` directly.
- UI Kit rules: only components exported by `@forge/react`; check real prop
  types in `forge-app/node_modules/@atlaskit/forge-react-types/src/components/
  __generated__/` rather than guessing; a fragment's children lay out SIDE BY
  SIDE (wrap in `Stack`); there is no `Table` (use `DynamicTable`); no
  div/strong/etc. The app is plain JS/JSX (no tsc). ESLint only has the
  react-hooks rule. No UI test harness exists - verify UI by deploying and
  asking the user for a screenshot (Claude in Chrome was not available).
- Keep presentation logic pure and unit-tested in `src/frontend/lib/*.js`.

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
`mvp` or `v2`.
