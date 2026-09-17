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
