import { requestRemote } from '@forge/bridge';

// Must match the `remotes[].key` in manifest.yml.
const REMOTE_KEY = 'traceability-backend';

/**
 * Call the FastAPI backend through the Forge Remote and return its parsed
 * JSON. Forge attaches the Forge Invocation Token the backend verifies
 * (backend/forge_auth.py). Errors carry FastAPI's {"detail": "..."} message
 * when present, same as frontend/src/api.ts, since it's usually more useful
 * than a bare status code (e.g. "No Jira connection configured yet").
 */
async function callBackend(path, method) {
  const response = await requestRemote(REMOTE_KEY, { path, method });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `${path} returned ${response.status}`);
  }
  return response.json();
}

/** GET /api/inventory - the reconciled test inventory: {entries: InventoryEntry[]}. */
export function fetchInventory() {
  return callBackend('/api/inventory', 'GET');
}

/** GET /api/jira/connection - connection status; used only to link Jira keys. */
export function fetchJiraConnection() {
  return callBackend('/api/jira/connection', 'GET');
}

/** GET /api/coverage - every requirement in a Jira project with its linked-test count. */
export function fetchCoverage(projectKey) {
  return callBackend(`/api/coverage?project_key=${encodeURIComponent(projectKey)}`, 'GET');
}

/** GET /api/requirement-links - per-link health (covered/suspect/stale/orphaned) for a project. */
export function fetchRequirementLinks(projectKey) {
  return callBackend(`/api/requirement-links?project_key=${encodeURIComponent(projectKey)}`, 'GET');
}

/** POST /api/requirement-links/{id}/reviewed - the only way a Suspect link is cleared. */
export function markLinkReviewed(linkId) {
  return callBackend(`/api/requirement-links/${linkId}/reviewed`, 'POST');
}

/** POST /api/coverage/gap-analysis - per-criterion LLM verdicts for one requirement (a real LLM call). */
export function fetchGapAnalysis(projectKey, jiraKey) {
  const params = new URLSearchParams({ project_key: projectKey, jira_key: jiraKey });
  return callBackend(`/api/coverage/gap-analysis?${params.toString()}`, 'POST');
}
