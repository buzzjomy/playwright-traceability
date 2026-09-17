import { useEffect, useState } from 'react';
import { fetchInventory, type InventoryEntry, type TrendPoint } from './api';
import { JiraKeyLink } from './JiraKeyLink';

function statusLabel(entry: InventoryEntry): string {
  if (!entry.has_run) return 'never run';
  return entry.status ?? 'unknown';
}

function statusClassName(entry: InventoryEntry): string {
  if (!entry.has_run) return 'status status-never-run';
  return `status status-${entry.status ?? 'unknown'}`;
}

// One dot per historical run, oldest first (left) to most recent (right) -
// mirrors the order build_inventory() already returns history in.
function TrendDots({ history }: { history: TrendPoint[] }) {
  if (history.length === 0) return <span>—</span>;
  return (
    <span className="trend-dots">
      {history.map((point) => (
        <span
          key={point.run_id}
          className={`trend-dot trend-dot-${point.status}`}
          title={`${point.status} — ${new Date(point.pushed_at).toLocaleString()}`}
        />
      ))}
    </span>
  );
}

export function InventoryView({ siteUrl }: { siteUrl: string | null }) {
  const [entries, setEntries] = useState<InventoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchInventory()
      .then((data) => setEntries(data.entries))
      .catch((err: Error) => setError(err.message));
  }, []);

  if (error) return <p className="error">Couldn't load the inventory: {error}</p>;
  if (entries === null) return <p>Loading…</p>;

  return (
    <>
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
              <th>Trend</th>
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
                  {entry.is_flaky && <span className="badge badge-flaky">flaky</span>}
                </td>
                <td>
                  <TrendDots history={entry.history} />
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
    </>
  );
}
