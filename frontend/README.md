# Traceability Dashboard (Milestone 3)

The first frontend in this repo, now two views behind a simple tab switch:

1. **Test Inventory** (issue #12) — one table combining run-based and
   source-based test data (see `backend/test_inventory.py` for the
   reconciliation logic this reads), including a per-test pass/fail
   trend (issue #14) and a flaky-run badge (issue #15).
2. **Requirement Coverage** (issue #13) — for a given Jira project key,
   which requirements have zero linked tests (see
   `backend/requirement_coverage.py`).

Vite + React + TypeScript, chosen as the lightest setup that gets a real
page in front of real API data without extra machinery an MVP internal
dashboard doesn't need yet — no router (two views is still simple enough
for local component state to switch between, see `App.tsx`'s `Tab` type),
no state management library (`useState`/`useEffect` is enough), no
component library or CSS framework (plain CSS in `src/App.css`).

## Running locally

```bash
# Terminal 1 - the backend this dashboard reads from
uvicorn backend.main:app --reload

# Terminal 2 - this frontend
cd frontend
npm install
npm run dev
```

Then open the URL Vite prints (typically `http://localhost:5173`).

`vite.config.ts` proxies `/api/*` requests to `http://localhost:8000` in
dev, so the browser never makes a cross-origin request — no CORS
middleware needed on the FastAPI side, and no `VITE_API_URL`-style env
var to configure for local dev.

## What's here

- `src/api.ts` — typed fetch wrappers for the backend's read-only GET
  endpoints this page uses (`/api/inventory`, `/api/coverage`,
  `/api/jira/connection`). Surfaces FastAPI's `{"detail": "..."}` error
  body when a request fails (e.g. "No Jira connection configured yet")
  instead of just a bare status code.
- `src/App.tsx` — tab switching (`inventory` | `coverage`) plus the
  shared Jira connection lookup (used by both views to decide whether to
  render Jira keys as links or plain text).
- `src/InventoryView.tsx` — the reconciled test table. A "not in source"
  badge marks a run result with no matching static/feature scan entry
  (e.g. a dynamically-generated test title, or one since deleted from
  source); a `never run` status marks a source entry with no matching
  run. See `backend/test_inventory.py`'s docstring for the full
  reconciliation rules, including the (file, title) exact-match
  requirement. A **Trend** column (issue #14) renders each row's
  `history` as a row of colored dots, oldest run first (left) to most
  recent (right) — reusing the same pass/failed/flaky color scheme as the
  Status column, via `<title>` tooltips for the exact timestamp/status of
  each point. A test with no run history yet (source-only) just shows
  `—`. A `flaky` badge (issue #15) appears under the Status badge when the
  *latest* run passed only after Playwright itself retried a failure —
  distinct from the Trend column, which shows outcomes across separate
  pushes over time, not retries within one run.
- `src/CoverageView.tsx` — a project-key input (remembered per-viewer via
  `localStorage`, never sent anywhere) plus a table of that project's
  requirements, each showing how many distinct tests link to it and
  whether that count is zero ("uncovered").
- `src/JiraKeyLink.tsx` — shared by both views: links a Jira key to the
  real ticket (`{site_url}/browse/{key}`) when a connection is
  configured, otherwise renders it as plain text.

## Verification

Beyond `tsc -b` (typechecks clean) and `vite build` (builds clean), both
views were verified in a real browser (Playwright/Chromium, reusing the
browser already installed for `demo/google-search`) against a real
running backend seeded via `scripts/push_test_inventory.py`:

- **Inventory**, seeded with `samples/sample-report.json` +
  `samples/sample-specs`, then again with the real, fully-reconciled
  `demo/google-search` data (10 rows, correct pass/fail badges). For
  issue #14, `demo/google-search` was pushed four times in a row against
  a live backend and the Trend column was confirmed to grow by one real
  dot per push, in the correct left-to-right run order. For issue #15,
  `demo/google-search` was re-run for real against live Google, produced
  a genuine Playwright-retry flaky result, and the `flaky` badge was
  confirmed to render on exactly that row.
- **Coverage**, against the real `KAN` Jira project: 13 requirements (10
  real demo stories + 2 default onboarding tasks + the dedicated
  integration-test scratch issue), correctly showing 10 covered and 3
  uncovered — the 3 uncovered are exactly the ones with no
  `demo/google-search` test linking to them.

Both confirmed with zero browser console errors; screenshots reviewed
directly.
