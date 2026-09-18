# Contributing

Thanks for taking a look at this project. It's still a young, solo-built
tool, so the fastest way to help is usually to open an issue describing
what you hit before sending a large PR — but small, focused fixes are
always welcome directly.

## Project layout

- `parser/` + `static_parser/` — the three Playwright test-inventory
  parsers (JSON run report, static `.spec.ts` AST scan, `.feature` BDD
  scan). See the root `README.md`.
- `backend/` — the FastAPI service (Jira auth, requirement pulling,
  traceability logic, suspect-link detection, gap analysis). See
  `backend/README.md`.
- `frontend/` — the React/Vite dashboard.
- `demo/google-search/` — a real demo Playwright project used as
  end-to-end test data.
- `tests/` — the Python test suite; `tests/integration/` holds the
  real-Jira integration tests (skipped without live credentials).

## Local setup

```bash
pip install -r requirements.txt
cd static_parser && npm install && cd ..
cd frontend && npm install && cd ..
```

## Running tests

```bash
pytest                        # backend + parser test suite
cd frontend && npm run build  # typecheck + build the dashboard
```

CI (`.github/workflows/ci.yml`) runs both of these on every push and PR.
There's also a separate `real-jira-integration.yml` workflow that runs
daily against a real Jira Cloud site — that one needs live credentials
and isn't something a PR from a fork can trigger or access.

## Making changes

- Match the existing code style — no framework beyond what's already
  used (no new state-management library, no ORM changes without reason).
- Add or update tests for behavior you change; the test suite is the
  main thing CI checks.
- Every function/method should have a short docstring or comment
  describing what it does, even a simple one-liner.
- Keep PRs focused. If a change touches several unrelated things, it's
  easier to review as separate PRs.

## Reporting issues

Open a GitHub issue. Include what you expected, what happened instead,
and enough detail (Playwright version, whether you're using the JSON
reporter / static parser / BDD parser, etc.) to reproduce it.
