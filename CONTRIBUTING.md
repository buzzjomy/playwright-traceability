# Contributing

Thanks for taking a look at this project. It's still a young, solo-built
tool, so the fastest way to help is usually to open an issue describing
what you hit before sending a large PR - but small, focused fixes are
always welcome directly.

For what the project is and where everything lives, start with the root
[`README.md`](README.md); for current status and design decisions,
[`CLAUDE.md`](CLAUDE.md).

## Project layout

- `parser/` + `static_parser/` - the three Playwright test-inventory
  parsers (JSON run report, static `.spec.ts` AST scan, `.feature` BDD
  scan). See the root `README.md`.
- `backend/` - the FastAPI service (ingest, Jira access, coverage,
  suspect-link detection, gap analysis, multi-tenancy). Database changes go
  through Alembic migrations in `backend/migrations/`. See
  `backend/README.md`.
- `forge-app/` - the Jira app (Atlassian Forge, UI Kit). Plain JS/JSX.
- `reporter/` - the Playwright reporter package (Node).
- `frontend/` - the standalone React/Vite dashboard.
- `scripts/` - the Python CLI for uploading test data.
- `demo/google-search/` - a real demo Playwright project used as
  end-to-end test data.
- `tests/` - the Python test suite; `tests/integration/` holds the
  real-Jira integration tests (skipped without live credentials).
- `docs/` - the customer interview guide and demo script.

## Local setup

```bash
pip install -r requirements.txt
(cd static_parser && npm install)
(cd frontend && npm install)
(cd forge-app && npm ci)
(cd reporter && npm install)
```

**Use Node 22** for everything Node-based. The Forge CLI requires 22 or 24,
and the static-parser tests shell out to `node`:

```bash
export NVM_DIR="$HOME/.nvm" && source "$NVM_DIR/nvm.sh" && nvm use 22
```

If `node` on your PATH is a different or broken binary (for example an Intel
build that won't run on Apple Silicon), the static-parser tests fail with
"Bad CPU type" - switch Node first.

## Running tests

```bash
pytest                                  # backend + parser + migration tests
(cd reporter && npm test)               # the reporter, incl. a real Playwright run
(cd forge-app && npm run lint && npm test)
(cd frontend && npm run build)          # typecheck + build the dashboard
```

CI (`.github/workflows/ci.yml`) runs all of these on every push and PR, with
a real Postgres service so the database migrations are tested against the
production database engine too. (`forge lint` needs an Atlassian login, so it
is not in CI; run `npx @forge/cli lint` in `forge-app/` yourself if you change
the manifest.) There's also a separate `real-jira-integration.yml` workflow
that runs daily against a real Jira Cloud site - it needs live credentials and
isn't something a PR from a fork can trigger or access.

## Making changes

- Match the existing code style - no framework beyond what's already
  used (no new state-management library, no ORM changes without reason).
- Add or update tests for behavior you change; the test suite is the
  main thing CI checks. Where a behaviour matters for security or customer
  isolation, add a test that fails if it breaks.
- Changing the database? Add an Alembic migration (see
  `backend/README.md`); don't rely on `create_all`.
- Every function/method should have a short docstring or comment
  describing what it does, even a simple one-liner - in any language.
- Never commit secrets (ingest keys, Jira/Anthropic/Fly/Atlassian tokens).
- If you change what the product does or how it is run, update the relevant
  document in the same PR (see the table in the root `README.md`).
- Keep PRs focused. If a change touches several unrelated things, it's
  easier to review as separate PRs.

## Reporting issues

Open a GitHub issue. Include what you expected, what happened instead,
and enough detail (Playwright version, whether you're using the reporter,
the JSON reporter / static parser / BDD parser, etc.) to reproduce it.
