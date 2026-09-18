import { Fragment, useEffect, useState } from 'react';
import {
  fetchCoverage,
  fetchGapAnalysis,
  fetchRequirementLinks,
  markLinkReviewed,
  type CoverageResponse,
  type GapAnalysisResponse,
  type RequirementLink,
} from './api';
import { JiraKeyLink } from './JiraKeyLink';

// Reuses the pass/fail/flaky badge styling from the inventory table -
// "covered" reads as healthy, "suspect" as needs-attention (same as
// flaky), "stale"/"orphaned" as broken links (same as failed/never-run).
const LINK_STATE_CLASS: Record<RequirementLink['state'], string> = {
  covered: 'status-passed',
  suspect: 'status-flaky',
  stale: 'status-never-run',
  orphaned: 'status-failed',
};

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

  const [links, setLinks] = useState<RequirementLink[] | null>(null);
  const [linksError, setLinksError] = useState<string | null>(null);
  const [reviewingId, setReviewingId] = useState<number | null>(null);

  const [gapResults, setGapResults] = useState<Record<string, GapAnalysisResponse>>({});
  const [gapErrors, setGapErrors] = useState<Record<string, string>>({});
  const [analyzingKey, setAnalyzingKey] = useState<string | null>(null);

  function load(key: string) {
    setLoading(true);
    setError(null);
    setGapResults({});
    setGapErrors({});
    fetchCoverage(key)
      .then((result) => {
        setData(result);
        rememberProjectKey(key);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));

    setLinksError(null);
    fetchRequirementLinks(key)
      .then((result) => setLinks(result.links))
      .catch((err: Error) => setLinksError(err.message));
  }

  function reviewLink(linkId: number) {
    setReviewingId(linkId);
    markLinkReviewed(linkId)
      .then((updated) => {
        setLinks((current) => (current ? current.map((l) => (l.id === linkId ? updated : l)) : current));
      })
      .catch((err: Error) => setLinksError(err.message))
      .finally(() => setReviewingId(null));
  }

  function analyzeGaps(jiraKey: string) {
    setAnalyzingKey(jiraKey);
    setGapErrors((current) => ({ ...current, [jiraKey]: '' }));
    fetchGapAnalysis(projectKey, jiraKey)
      .then((result) => setGapResults((current) => ({ ...current, [jiraKey]: result })))
      .catch((err: Error) => setGapErrors((current) => ({ ...current, [jiraKey]: err.message })))
      .finally(() => setAnalyzingKey(null));
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
                  <th>Gap Analysis</th>
                </tr>
              </thead>
              <tbody>
                {data.requirements.map((req) => {
                  const gapResult = gapResults[req.key];
                  const gapError = gapErrors[req.key];
                  return (
                    <Fragment key={req.key}>
                      <tr>
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
                        <td>
                          <button onClick={() => analyzeGaps(req.key)} disabled={analyzingKey === req.key}>
                            {analyzingKey === req.key
                              ? 'Analyzing…'
                              : gapResult
                                ? 'Re-analyze'
                                : 'Analyze Gaps'}
                          </button>
                        </td>
                      </tr>
                      {gapError && (
                        <tr>
                          <td colSpan={5} className="error">
                            Gap analysis failed: {gapError}
                          </td>
                        </tr>
                      )}
                      {gapResult && (
                        <tr>
                          <td colSpan={5}>
                            <ul className="gap-analysis-list">
                              {gapResult.criteria.map((c, i) => (
                                <li key={i}>
                                  <span className={`status ${c.covered ? 'status-passed' : 'status-failed'}`}>
                                    {c.covered ? 'covered' : 'gap'}
                                  </span>{' '}
                                  <strong>{c.criterion}</strong> — {c.reasoning}
                                </li>
                              ))}
                            </ul>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          )}

          <h3>Link Health</h3>
          <p className="subtitle">
            Whether each linked test's requirement has changed since it was linked - the differentiator over "does a
            link exist at all" (see the coverage table above).
          </p>

          {linksError && <p className="error">Couldn't load link health: {linksError}</p>}

          {links && (
            <>
              {links.length === 0 ? (
                <p>No requirement links yet.</p>
              ) : (
                <table className="inventory-table">
                  <thead>
                    <tr>
                      <th>Key</th>
                      <th>Test</th>
                      <th>State</th>
                      <th>Last Reviewed</th>
                      <th>What Changed</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {links.map((link) => (
                      <tr key={link.id}>
                        <td>
                          <JiraKeyLink jiraKey={link.jira_key} siteUrl={siteUrl} />
                        </td>
                        <td className="file-cell">
                          {link.test_file} — {link.test_title}
                        </td>
                        <td>
                          <span className={`status ${LINK_STATE_CLASS[link.state]}`}>{link.state}</span>
                        </td>
                        <td>{link.last_reviewed_at ? new Date(link.last_reviewed_at).toLocaleString() : '—'}</td>
                        <td>{link.change_summary ?? '—'}</td>
                        <td>
                          {link.state === 'suspect' && (
                            <button onClick={() => reviewLink(link.id)} disabled={reviewingId === link.id}>
                              {reviewingId === link.id ? 'Reviewing…' : 'Mark reviewed'}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </>
      )}
    </>
  );
}
