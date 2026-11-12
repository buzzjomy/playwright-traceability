import { invokeRemote } from '@forge/bridge';

/**
 * Call the FastAPI backend through the manifest's `endpoint` module and
 * return its parsed JSON.
 *
 * invokeRemote (not requestRemote) on purpose: Forge proxies the call and
 * attaches the app system token the backend uses to read Jira as the app
 * (issue #41); requestRemote goes browser -> backend directly and carries no
 * tokens. Errors carry FastAPI's {"detail": "..."} message when present,
 * same as frontend/src/api.ts, since it's usually more useful than a bare
 * status code (e.g. "No Jira connection configured yet").
 */
async function callBackend(path, method) {
  let response;
  try {
    response = await invokeRemote({ path, method });
  } catch (err) {
    // The bridge may reject on a non-2xx; keep the backend's own message.
    throw new Error(err?.body?.detail ?? err?.message ?? `${path} failed`);
  }
  if (response.status >= 400) {
    throw new Error(response.body?.detail ?? `${path} returned ${response.status}`);
  }
  return response.body;
}

/** GET /api/inventory - the reconciled test inventory: {entries: InventoryEntry[]}. */
export function fetchInventory() {
  return callBackend('/api/inventory', 'GET');
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

/** GET /api/tenant - this installation's id and whether it already has a CI ingest key. */
export function fetchTenant() {
  return callBackend('/api/tenant', 'GET');
}

/** POST /api/tenant/ingest-key - generate (or replace) the CI ingest key; the key comes back once. */
export function createIngestKey() {
  return callBackend('/api/tenant/ingest-key', 'POST');
}
