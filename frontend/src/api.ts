// Thin fetch wrapper around the backend's read-only GET endpoints used by
// this dashboard. See backend/main.py for the actual API surface.

export interface TrendPoint {
  run_id: number;
  pushed_at: string;
  status: string;
}

export interface InventoryEntry {
  file: string;
  title: string;
  full_title: string;
  project: string | null;
  status: string | null;
  tags: string[];
  jira_keys: string[];
  in_source: boolean;
  has_run: boolean;
  history: TrendPoint[];
  is_flaky: boolean;
}

export interface JiraConnectionStatus {
  connected: boolean;
  site_url: string | null;
  email: string | null;
  account_id: string | null;
  display_name: string | null;
}

export interface CoverageEntry {
  key: string;
  summary: string;
  linked_test_count: number;
  covered: boolean;
}

export interface CoverageResponse {
  project_key: string;
  requirements: CoverageEntry[];
  total: number;
  covered: number;
  uncovered: number;
}

export interface RequirementLink {
  id: number;
  jira_key: string;
  test_file: string;
  test_title: string;
  state: 'covered' | 'suspect' | 'stale' | 'orphaned';
  change_summary: string | null;
  linked_at: string;
  last_reviewed_at: string | null;
}

export interface RequirementLinksResponse {
  project_key: string;
  links: RequirementLink[];
}

export interface CriterionGapResult {
  criterion: string;
  covered: boolean;
  reasoning: string;
}

export interface GapAnalysisResponse {
  jira_key: string;
  criteria: CriterionGapResult[];
  uncovered_count: number;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    // FastAPI's HTTPException body is {"detail": "..."} - surface that
    // when present, since it's usually more useful than a bare status code
    // (e.g. "No Jira connection configured yet").
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `${path} returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { method: 'POST' });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `${path} returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchInventory(): Promise<{ entries: InventoryEntry[] }> {
  return getJson('/api/inventory');
}

export function fetchJiraConnection(): Promise<JiraConnectionStatus> {
  return getJson('/api/jira/connection');
}

export function fetchCoverage(projectKey: string): Promise<CoverageResponse> {
  return getJson(`/api/coverage?project_key=${encodeURIComponent(projectKey)}`);
}

export function fetchRequirementLinks(projectKey: string): Promise<RequirementLinksResponse> {
  return getJson(`/api/requirement-links?project_key=${encodeURIComponent(projectKey)}`);
}

export function markLinkReviewed(linkId: number): Promise<RequirementLink> {
  return postJson(`/api/requirement-links/${linkId}/reviewed`);
}

export function fetchGapAnalysis(projectKey: string, jiraKey: string): Promise<GapAnalysisResponse> {
  const params = new URLSearchParams({ project_key: projectKey, jira_key: jiraKey });
  return postJson(`/api/coverage/gap-analysis?${params.toString()}`);
}
