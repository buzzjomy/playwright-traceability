# Backend Service (Milestone 2, plus Milestone 1 issue #5)

Covers Milestone 2, issue #6: *"Jira REST API auth (OAuth or API token) and
connection setup flow."* A minimal FastAPI service that authenticates
against a Jira Cloud site and persists that connection. Later Milestone 2
issues (pulling requirement/story data, linking tests, webhooks) build on
this same app and `jira_client.py`.

Also covers Milestone 1, issue #5 (*"CLI or GitHub Action snippet for users
to push run output to the service"*) — deferred until this backend existed.
See "Pushing test inventory data" below and `scripts/push_test_inventory.py`.

## Why API token + Basic Auth, not OAuth 2.0

OAuth 2.0 (3-legged) is the right choice for a real multi-tenant "Connect
your Jira" product experience later, but it needs an app registered on the
Atlassian Developer Console, a public redirect URI, and refresh-token
handling — real setup overhead before there's even a backend deployed
anywhere. Jira Cloud's email + API token (via HTTP Basic Auth) works today,
with a token a user generates themselves at id.atlassian.com — the
pragmatic MVP choice for a solo builder. See `CLAUDE.md` for the broader
"ship MVP fast" reasoning.

## Why SQLite by default, not Postgres

`backend/db.py` defaults `DATABASE_URL` to a local SQLite file so there's
zero setup to run this locally. Set `DATABASE_URL` to a Postgres connection
string for anything beyond local dev — SQLAlchemy's column types here are
portable across both, so nothing else needs to change. Postgres is still
the named production database per `CLAUDE.md`'s tech stack.

## Running locally

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Interactive API docs (Swagger UI) are then at `http://127.0.0.1:8000/docs`.

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/jira/connection` | Validate the given `{site_url, email, api_token}` against the real Jira API, then store it. Replaces any existing connection. Returns `401` if Jira rejects the credentials. |
| `GET` | `/api/jira/connection` | Return the current connection's status, re-validated live against Jira. Never returns the stored API token. |
| `DELETE` | `/api/jira/connection` | Remove the current connection, if any. |
| `GET` | `/api/jira/requirements?project_key=KAN` | Pull every Story/Task (configurable via `issue_types`) in a Jira project as `{key, summary, description_text, acceptance_criteria}`. Live-fetches from Jira every call, no caching yet. |
| `POST` | `/api/ingest/run` | Ingest test inventory data (see below). Requires `Authorization: Bearer <INGEST_API_KEY>`. |
| `POST` | `/api/webhooks/jira?token=...` | Receive a Jira webhook event (see below). Requires `?token=<JIRA_WEBHOOK_SECRET>`. |
| `GET` | `/api/webhooks/jira/events` | List recently received webhook events, newest first. Not authenticated (read-only, local-only use). |
| `POST` | `/api/jira/poll?project_key=KAN` | Poll Jira for issues changed since the last poll (see below). Requires `Authorization: Bearer <INGEST_API_KEY>`. |
| `GET` | `/api/inventory` | The reconciled test inventory (see below) — what `frontend/`'s dashboard reads. Not authenticated (read-only, local-only use). |
| `GET` | `/api/coverage?project_key=KAN` | Per-requirement test coverage for a Jira project (see below). Not authenticated (read-only, local-only use). |

## Pushing test inventory data

`scripts/push_test_inventory.py` runs whichever of the three Milestone 1
parsers you ask for and pushes the combined result to `POST
/api/ingest/run`. Typical CI usage, right after a Playwright run:

```bash
export INGEST_API_KEY=...  # set as a secret in CI, never in shell history
python -m scripts.push_test_inventory \
  --backend-url https://your-backend.example.com \
  --report report.json \
  --specs-dir tests/ \
  --features-dir features/
```

Any of `--report`/`--specs-dir`/`--features-dir` may be omitted — only the
requested parsers run, and only their corresponding backend data is
touched. This matters because different CI jobs may push on different
triggers (a run report on every test run; a source-inventory scan only
when `.spec.ts`/`.feature` files change) — omitting a field means "this
push doesn't concern that data," not "there is none of it."

### JSON mapping-file linking (issue #9)

For teams that don't want `Trace(Jira:...)` comments in their test code at
all, `--mapping-file` links tests to Jira keys from a standalone JSON file
instead:

```bash
python -m scripts.push_test_inventory \
  --backend-url https://your-backend.example.com \
  --specs-dir tests/ \
  --mapping-file jira-mapping.json
```

```json
[
  { "file": "auth.spec.ts", "title": "should login", "jira_keys": ["PROJ-101"] }
]
```

Matches by exact `(file, title)` — as of the path normalization described
below, `file` should be written repo-root-relative (e.g.
`demo/google-search/tests/homepage.spec.ts`), matching what every
pushed record's `file` now looks like regardless of how each parser was
invoked. Mapping keys are **merged into**, not swapped in for, whatever `jira_keys`
a test already has from tags/annotations/`Trace(...)` comments — a test
can be linked more than one way at once. A mapping entry that never
matches any parsed test prints a warning (likely a typo, or a renamed/
removed test) but doesn't fail the push.

Verified end-to-end (not just mocks): pushed the real `demo/google-search`
project through this exact CLI with a mapping file that added an extra key
to a test that already had a `Trace(...)`-equivalent comment, then read
the resulting DB row directly — both keys were present, every other test
was untouched, and a deliberately-stale mapping entry printed its warning
without failing the push.

**Example GitHub Action step** (in a Playwright project's own workflow,
after the test run):

```yaml
- name: Run Playwright tests
  run: npx playwright test --reporter=json > report.json
  continue-on-error: true  # still want to push results even if tests failed

- name: Push test inventory to Traceability service
  env:
    INGEST_API_KEY: ${{ secrets.TRACEABILITY_API_KEY }}
  run: |
    pip install requests
    python -m scripts.push_test_inventory \
      --backend-url ${{ vars.TRACEABILITY_BACKEND_URL }} \
      --report report.json \
      --specs-dir tests/
```

### Why an API key here, unlike the Jira endpoints

`/api/ingest/run` is meant to be called from outside — a GitHub Action
runner, not just local dev — so unlike the local-only Jira setup
endpoints, it requires a shared secret (`INGEST_API_KEY` env var, checked
as a Bearer token). The endpoint fails closed (returns `500`) if the
server itself isn't configured with a key, rather than silently accepting
every request.

### Run history vs. source snapshots

`run_report` data is **appended**: every push creates a new `TestRun` row,
and old runs are kept — needed for pass/fail trends over time (Milestone
3, issue #14), which would be expensive to retrofit later if the history
was never kept in the first place. `static_specs` and `features` are
**replaced** on each push (per source type independently): there's no
equivalent need to keep historical versions of "what the source currently
looks like," just the latest snapshot.

### File paths are normalized to repo-root-relative before pushing

Discovered as a real bug while manually demoing the dashboard, not in a
test: `report_parser`'s `file` is relative to Playwright's own `rootDir`
(e.g. `homepage.spec.ts`), while `static_parser`/`feature_parser`'s `file`
is relative to whatever `--specs-dir`/`--features-dir` string was passed
(e.g. `demo/google-search/tests/homepage.spec.ts` if invoked from the repo
root). Same physical file, two different strings — which silently broke
`backend/test_inventory.py`'s `(file, title)` reconciliation: every test
showed up as two unmatched rows instead of one.

The fix, in `scripts/push_test_inventory.py` (`find_repo_root`,
`normalize_file_path`): every record's `file` is resolved to an absolute
path and made relative to the repo root (found by walking up from cwd for
a `.git` directory) before it's ever sent to the backend. For
`report_parser` records specifically, the report's own `config.rootDir`
field is used to correctly resolve its rootDir-relative paths first. This
means callers no longer need to invoke every parser from a consistent
working directory for reconciliation to work — normalization happens once,
centrally, regardless of how each one was actually run. A path that can't
be related to the repo root (e.g. a synthetic fixture with a fake
`rootDir` like `/repo/tests`) falls back to its original string rather
than fabricating something wrong.

Verified against the exact real scenario that surfaced the bug: pushed
`demo/google-search`'s committed `report.json` + a `--specs-dir` pointed
at it from the repo root (the same invocation that originally produced 20
unreconciled rows in the live dashboard) and confirmed all 10 tests now
reconcile correctly — see
`tests/test_push_test_inventory.py::test_build_payload_normalizes_paths_so_report_and_specs_reconcile`.

## Pulling requirement/story data (issue #7)

`GET /api/jira/requirements?project_key=KAN` pulls every Story/Task in a
project and parses out (key, summary, description, acceptance criteria).

**Real, non-obvious finding:** there's no dedicated "Acceptance Criteria"
field on a standard Jira Cloud site — confirmed against a real project,
`demo/google-search`'s own KAN-4..KAN-13 stories. Teams write ACs as a
heading (e.g. "Acceptance Criteria") followed by a bullet list inside the
description, same as this repo did when creating that demo data. That's
the convention `jira_requirements.py` parses; an issue with a plain
description and no such heading just gets `acceptance_criteria: []`.

**Also confirmed against a real site:** the classic `GET /rest/api/3/search`
endpoint has been **removed** by Atlassian — it now returns an error
telling callers to migrate to `/rest/api/3/search/jql`, which uses
cursor-based pagination (`nextPageToken`/`isLast`) instead of the old
`startAt`/`total` offset pagination. `JiraClient.search_issues` handles
this paging automatically.

Verified end-to-end against the real pwtrace.atlassian.net site (not just
mocks): pulled all 10 `demo/google-search` stories with their exact
Acceptance Criteria intact, plus Jira's own default onboarding tasks
(correctly showing `acceptance_criteria: []`, since they don't use the
heading convention).

## Receiving Jira webhook events (issue #10)

`POST /api/webhooks/jira?token=...` receives Jira webhook deliveries
(e.g. `jira:issue_updated`) and records them in `jira_webhook_events` for
issue #17 (drift detection) to consume later. It doesn't itself decide
anything changed or flip any Suspect state — it's purely a durable log of
"this happened."

**Real, significant finding:** Jira Cloud's webhook self-registration REST
API (`POST /rest/api/3/webhook`) **rejects Basic Auth outright** — tested
against the real pwtrace.atlassian.net site, it returns `403 "Only Connect
and OAuth 2.0 apps can use this operation."` This directly conflicts with
the API-token auth chosen for issue #6 (specifically to avoid needing a
registered app + public redirect URI). There's no way around this without
either building OAuth 2.0 now or using a different registration path.

**The path taken:** Jira Cloud still supports the older "classic" webhooks
feature, configured manually by a Jira admin — no OAuth needed:

1. In Jira: **Settings → System → WebHooks → Create a WebHook**
2. URL: `https://your-backend.example.com/api/webhooks/jira?token=<JIRA_WEBHOOK_SECRET>`
   (optionally with a JQL filter, e.g. `project = KAN`)
3. Events: check **Issue → updated**

The secret is a **query param, not a header** — the classic webhook admin
UI only lets you configure a plain URL, with no way to add custom headers,
so the shared secret is embedded directly in the URL instead. The endpoint
fails closed (`500`) if `JIRA_WEBHOOK_SECRET` isn't configured on the
server at all.

**Verified with a real webhook delivery**, not just a synthetic payload:
tunneled a local backend to the internet with `ngrok`, registered it as a
classic webhook against the real pwtrace.atlassian.net site, edited
KAN-4's description for real, and confirmed the exact payload arrived and
was recorded correctly — including the real `changelog.items[].fromString`
/`toString` diff. The payload shape (`webhookEvent`, `issue.key`,
`changelog.items`) matched Atlassian's documented format exactly, so no
code changes were needed after seeing the real delivery.

## Polling fallback (issue #11)

For Jira instances/networks that can't deliver webhooks at all (no admin
access to configure one, a firewall blocking inbound requests to a
self-hosted backend, etc), `POST /api/jira/poll?project_key=KAN` polls
Jira's search API instead, on whatever interval an external scheduler
(cron, a scheduled GitHub Action) triggers it — there's no in-process
background scheduler here, same posture as `scripts/push_test_inventory.py`.
It tracks the last successful poll per project (`JiraPollState`) and
records one `JiraWebhookEvent` per changed issue found
(`webhook_event: "jira:issue_polled"`, `changelog: null` — a JQL search
returns each issue's current state, not a field-level diff, so polled
events are lower-fidelity than real webhook deliveries by design).

**Major real finding — this one required fixing after first getting it
wrong.** The original implementation built an absolute JQL date literal
(`updated >= "2026-09-17 07:28"`) from the last poll's timestamp. Verified
against the real pwtrace.atlassian.net site: **every absolute time-of-day
JQL literal silently matched zero issues**, whether or not it included
seconds, at any hour tried (`06:00`, `10:00`, `12:58`, all failed) — only
an exact-midnight date-only literal (`"2026-09-17 00:00"`) or a *relative*
literal (`"-1h"`, `"-5m"`) worked. There was no error; it just silently
found nothing, which would have made every real poll after the first a
silent no-op forever.

**The fix:** `jira_polling.format_jql_relative_window` computes the
elapsed time between the last poll and now, and expresses it as Jira's
own relative-time syntax (`"-45m"`) instead of an absolute timestamp —
sidestepping the bug entirely, and any timezone-conversion ambiguity
along with it, since a relative literal needs no timezone context.
Rounds up to the nearest whole minute (floored at 1 minute) so a partial
minute is never silently dropped.

**Verified for real, after the fix**, not just against mocks: ran a real
poll cycle against the live Jira site — baseline poll, a real edit to a
KAN issue via the actual Jira API, then a second poll a few seconds later
— and confirmed the edited issue was correctly detected and recorded.
Caught and fixed the absolute-literal bug the same way, by testing against
the real site first and finding the first version silently missed a real
edit before shipping it.

## Test inventory view (issue #12)

`GET /api/inventory` (`backend/test_inventory.py`) is the first Milestone
3 (dashboard) piece, and the first place `TestRunRecord` (from a pushed
run) and `SourceTestRecord` (from a static `.spec.ts`/`.feature` scan)
actually get reconciled into one view — they've been independent,
unreconciled streams since Milestone 1, deferred each time with "a simple
`(file, title)` match is probably sufficient when picked up." This is
where that got picked up, and it works exactly as it sounds: a
`SourceTestRecord` and a `TestRunRecord` are the same test if their `file`
and `title` match exactly. `tags`/`jira_keys` from both sides are unioned.
Multi-project runs are **not** collapsed (same principle as `TestRecord`
itself) — a test that ran under both chromium and firefox produces one
row per project.

A test found only in source (`in_source: true, has_run: false` —
skipped, filtered out, or just not part of the pushed run) or only in a
run (`in_source: false, has_run: true` — e.g. a dynamically-generated
title a static scan can never resolve, or a test since deleted from
source) still gets its own row rather than being dropped, so the gap
itself is visible in the dashboard, not hidden.

**The (file, title) match was a real sharp edge, not a hypothetical one -
it broke a live demo, and got fixed as a result.** `frontend/`'s
dashboard, run against the real `samples/sample-report.json` +
`samples/sample-specs` fixtures (and again against `demo/google-search`),
visibly showed every test as two unmatched rows instead of one: the
run-report's `file` is rootDir-relative (`auth.spec.ts`), while
`static_parser` was invoked with a different root and so reported the
longer `demo/google-search/tests/auth.spec.ts` — different strings for
the same file. This is exactly what led to the path-normalization fix in
`scripts/push_test_inventory.py` (see "File paths are normalized..."
above) — `build_inventory` itself still does a plain exact-string
`(file, title)` match with no fuzziness, but callers no longer need to
invoke every parser from a consistent working directory to get correct
paths into it. `tests/test_test_inventory.py::test_reconciliation_requires_matching_file_paths`
still documents what happens if paths reach the backend unnormalized
(e.g. via a direct API call rather than the CLI) — the reconciliation
logic itself doesn't know or care where a `file` string came from.

`frontend/` is the first UI in the repo (Vite + React + TypeScript) - see
its own README for what it renders and how it was verified in a real
browser, not just typechecked.

## Requirement coverage view (issue #13)

`GET /api/coverage?project_key=KAN` (`backend/requirement_coverage.py`)
combines a live pull of a Jira project's requirements (issue #7) with the
reconciled inventory (issue #12): for each requirement, how many
*distinct* tests reference its key. A requirement with
`linked_test_count: 0` is `covered: false` — the core signal this view
exists to surface, per `CLAUDE.md`'s differentiator: knowing a linked
test exists at all is the prerequisite for the later semantic-gap
work (Milestone 5), which checks whether a linked test's *content* still
matches the requirement, not just whether one exists.

Counting is **per distinct `(file, title)` test, not per inventory row**
— a multi-project test (one row per project, per issue #12's design)
counts once toward a requirement's coverage, not once per project it ran
under; two different tests linking the same requirement both count.

Verified against the real Jira `KAN` project + the real, correctly-
reconciled `demo/google-search` inventory: 13 requirements total (the 10
real demo stories, Jira's 2 default onboarding tasks, and the dedicated
integration-test scratch issue KAN-14), correctly showing 10 covered and
3 uncovered — the 3 uncovered are exactly the ones with no test linking
to them.

## Design notes for whoever picks up the next issue

- This is single-tenant for now — `JiraConnection` is a one-row table,
  and creating a new connection replaces the old one outright. Multi-tenant
  support (one connection per user/org) is real work for whenever this
  becomes a multi-user product, not before.
- `api_token` is stored as given, in plaintext, in the local DB. Acceptable
  for a solo builder's own local MVP; this is a known gap to close (e.g.
  encryption at rest) before any multi-user or production deployment.
- `GET`/`DELETE` don't require re-sending credentials — they operate on
  whatever's already stored.
- `/api/jira/requirements` live-fetches from Jira on every call — no
  caching or persistence yet (deliberately out of scope for #7; that's
  really issues #16/#17/#18's territory - hashing fields, drift detection,
  the Covered/Suspect/Stale/Orphaned link-state model).
- Default issue types pulled are `Story` and `Task` (not `Epic` or
  `Subtask`) - overridable via `?issue_types=Epic,Bug`.
- Tests mock `requests.get`/`requests.post` directly (`unittest.mock.patch`)
  rather than pulling in a dedicated HTTP-mocking library — matches this
  repo's preference for stdlib over new dependencies where it's simple
  enough.
- `SourceTestRecord` is one table for both static (`.spec.ts`) and feature
  (`.feature`) records, distinguished by `source_type` — they share an
  identical shape (`parser.models.StaticTestRecord`/`FeatureTestRecord`),
  so one table avoids duplicating an otherwise-identical schema.
- `tags`/`jira_keys` are stored as a JSON column (portable across SQLite
  and Postgres via SQLAlchemy's `JSON` type) rather than a normalized
  many-to-many table — simplest thing that works for now; revisit if
  querying "all tests tagged X" across the DB (not just via the API)
  becomes a real need.
- Reconciling `TestRunRecord` (from a run) with `SourceTestRecord` (from
  source) — e.g. "exists in source but never run" — is still deferred, per
  `README.md`'s design notes; ingest doesn't attempt this, it just stores
  both streams independently, same as the parsers themselves.
