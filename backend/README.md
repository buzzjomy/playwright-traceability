# Backend Service (Milestone 2)

Covers the first issue of Milestone 2: *"Jira REST API auth (OAuth or API
token) and connection setup flow."* A minimal FastAPI service that
authenticates against a Jira Cloud site and persists that connection.
Later Milestone 2 issues (pulling requirement/story data, linking tests,
webhooks) build on this same app and `jira_client.py`.

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

## Design notes for whoever picks up the next issue

- This is single-tenant for now — `JiraConnection` is a one-row table,
  and creating a new connection replaces the old one outright. Multi-tenant
  support (one connection per user/org) is real work for whenever this
  becomes a multi-user product, not before.
- `api_token` is stored as given, in plaintext, in the local DB. Acceptable
  for a solo builder's own local MVP; this is a known gap to close (e.g.
  encryption at rest) before any multi-user or production deployment.
- `GET`/`DELETE` don't require re-sending credentials — they operate on
  whatever's already stored. `jira_client.JiraClient` is the reusable piece
  for issue #7 (pulling requirement/story data): construct it from a stored
  `JiraConnection` row and add methods alongside `get_current_user`.
- Tests mock `requests.get` directly (`unittest.mock.patch`) rather than
  pulling in a dedicated HTTP-mocking library — matches this repo's
  preference for stdlib over new dependencies where it's simple enough.
