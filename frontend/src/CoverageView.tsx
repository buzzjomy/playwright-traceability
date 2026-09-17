import { useEffect, useState } from 'react';
import { fetchCoverage, type CoverageResponse } from './api';
import { JiraKeyLink } from './JiraKeyLink';

// Per-viewer convenience only (which project key you last looked at) -
// never shared, never read by the backend. Wrapped in try/catch since
// localStorage can throw or be unavailable (private browsing, etc).
function loadRememberedProjectKey(): string {
  try {
    return localStorage.getItem('coverageProjectKey') ?? 'KAN';
  } catch {
    return 'KAN';
  }
}

function rememberProjectKey(key: string): void {
  try {
    localStorage.setItem('coverageProjectKey', key);
  } catch {
    // ignore - just a convenience, not required for the view to work
  }
}

export function CoverageView({ siteUrl }: { siteUrl: string | null }) {
  const [projectKey] = useState(loadRememberedProjectKey);
  const [inputValue, setInputValue] = useState(projectKey);
  const [data, setData] = useState<CoverageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function load(key: string) {
    setLoading(true);
    setError(null);
    fetchCoverage(key)
      .then((result) => {
        setData(result);
        rememberProjectKey(key);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load(projectKey);
    // Only on mount - subsequent loads are triggered by the form submit below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <form
        className="coverage-form"
        onSubmit={(e) => {
          e.preventDefault();
          load(inputValue);
        }}
      >
        <label htmlFor="project-key">Jira project key</label>
        <input id="project-key" value={inputValue} onChange={(e) => setInputValue(e.target.value)} />
        <button type="submit" disabled={loading}>
          {loading ? 'Loading…' : 'Load coverage'}
        </button>
      </form>

      {error && <p className="error">Couldn't load coverage: {error}</p>}

      {data && (
        <>
          <p className="subtitle">
            {data.total} requirement{data.total === 1 ? '' : 's'} in {data.project_key} — {data.covered} covered,{' '}
            {data.uncovered} uncovered.
          </p>

          {data.requirements.length === 0 ? (
            <p>No requirements found for this project.</p>
          ) : (
            <table className="inventory-table">
              <thead>
                <tr>
                  <th>Key</th>
                  <th>Summary</th>
                  <th>Linked Tests</th>
                  <th>Coverage</th>
                </tr>
              </thead>
              <tbody>
                {data.requirements.map((req) => (
                  <tr key={req.key}>
                    <td>
                      <JiraKeyLink jiraKey={req.key} siteUrl={siteUrl} />
                    </td>
                    <td>{req.summary}</td>
                    <td>{req.linked_test_count}</td>
                    <td>
                      <span className={`status ${req.covered ? 'status-passed' : 'status-failed'}`}>
                        {req.covered ? 'covered' : 'uncovered'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </>
  );
}
