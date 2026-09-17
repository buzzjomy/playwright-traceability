# Traceability Dashboard (Milestone 3)

The first frontend in this repo. Covers issue #12: a read-only test
inventory view — one table combining run-based and source-based test data
(see `backend/test_inventory.py` for the reconciliation logic this reads).

Vite + React + TypeScript, chosen as the lightest setup that gets a real
page in front of real API data without extra machinery an MVP internal
dashboard doesn't need yet — no router (one page so far), no state
management library (`useState`/`useEffect` is enough), no component
library or CSS framework (plain CSS in `src/App.css`).

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
  endpoints this page uses (`/api/inventory`, `/api/jira/connection`).
- `src/App.tsx` — the inventory table: loads data on mount, renders a row
  per reconciled test, links each Jira key to the real ticket
  (`{site_url}/browse/{key}`) when a Jira connection is configured,
  otherwise renders the key as plain text.
- A "not in source" badge marks a run result with no matching static/
  feature scan entry (e.g. a dynamically-generated test title, or one
  since deleted from source); a `never run` status marks a source entry
  with no matching run. See `backend/test_inventory.py`'s docstring for
  the full reconciliation rules, including the (file, title) exact-match
  requirement.

## Verification

Beyond `tsc -b` (typechecks clean) and `vite build` (builds clean), this
was verified in a real browser (Playwright/Chromium, reusing the browser
already installed for `demo/google-search`) against a real running
backend seeded with the real `samples/sample-report.json` +
`samples/sample-specs` fixtures via `scripts/push_test_inventory.py` -
confirmed the table renders the correct row count, status badges, "not in
source" warnings, and Jira key text, with zero console errors.
