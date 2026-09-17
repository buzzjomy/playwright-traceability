import { useEffect, useState } from 'react';
import './App.css';
import { fetchInventory, fetchJiraConnection, type InventoryEntry } from './api';

function statusLabel(entry: InventoryEntry): string {
  if (!entry.has_run) return 'never run';
  return entry.status ?? 'unknown';
}

function statusClassName(entry: InventoryEntry): string {
  if (!entry.has_run) return 'status status-never-run';
  return `status status-${entry.status ?? 'unknown'}`;
}

function JiraKeyLink({ jiraKey, siteUrl }: { jiraKey: string; siteUrl: string | null }) {
  if (!siteUrl) return <span className="jira-key">{jiraKey}</span>;
  return (
    <a className="jira-key" href={`${siteUrl.replace(/\/$/, '')}/browse/${jiraKey}`} target="_blank" rel="noreferrer">
      {jiraKey}
    </a>
  );
}

function App() {
  const [entries, setEntries] = useState<InventoryEntry[] | null>(null);
  const [siteUrl, setSiteUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchInventory()
      .then((data) => setEntries(data.entries))
      .catch((err: Error) => setError(err.message));

    // Best-effort: if there's no Jira connection configured yet, jira
    // keys just render as plain text instead of links - not a hard error.
    fetchJiraConnection()
      .then((status) => setSiteUrl(status.connected ? status.site_url : null))
      .catch(() => setSiteUrl(null));
  }, []);

  if (error) {
    return (
      <main className="page">
        <h1>Test Inventory</h1>
        <p className="error">Couldn't load the inventory: {error}</p>
      </main>
    );
  }

  if (entries === null) {
    return (
      <main className="page">
        <h1>Test Inventory</h1>
        <p>Loading…</p>
      </main>
    );
  }

  return (
    <main className="page">
      <h1>Test Inventory</h1>
      <p className="subtitle">
        {entries.length} test{entries.length === 1 ? '' : 's'} — reconciled from run reports and static source scans.
      </p>

      {entries.length === 0 ? (
        <p>No tests found yet. Push some data via scripts/push_test_inventory.py.</p>
      ) : (
        <table className="inventory-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>File</th>
              <th>Project</th>
              <th>Status</th>
              <th>Tags</th>
              <th>Jira Keys</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, i) => (
              <tr key={`${entry.file}:${entry.title}:${entry.project ?? ''}:${i}`}>
                <td>{entry.title}</td>
                <td className="file-cell">{entry.file}</td>
                <td>{entry.project ?? '—'}</td>
                <td>
                  <span className={statusClassName(entry)}>{statusLabel(entry)}</span>
                  {!entry.in_source && <span className="badge badge-warn">not in source</span>}
                </td>
                <td>{entry.tags.join(', ') || '—'}</td>
                <td>
                  {entry.jira_keys.length === 0
                    ? '—'
                    : entry.jira_keys.map((key) => (
                        <span key={key} className="jira-key-wrapper">
                          <JiraKeyLink jiraKey={key} siteUrl={siteUrl} />
                        </span>
                      ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

export default App;
