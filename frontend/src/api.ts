// Thin fetch wrapper around the backend's read-only GET endpoints used by
// this dashboard. See backend/main.py for the actual API surface.

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
}

export interface JiraConnectionStatus {
  connected: boolean;
  site_url: string | null;
  email: string | null;
  account_id: string | null;
  display_name: string | null;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchInventory(): Promise<{ entries: InventoryEntry[] }> {
  return getJson('/api/inventory');
}

export function fetchJiraConnection(): Promise<JiraConnectionStatus> {
  return getJson('/api/jira/connection');
}
