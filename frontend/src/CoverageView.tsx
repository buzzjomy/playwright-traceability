import { useEffect, useState } from 'react';
import {
  fetchCoverage,
  fetchGapAnalysis,
  fetchRequirementLinks,
  markLinkReviewed,
  type CoverageEntry,
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

// Worst-first, for rolling up one requirement's many links into a single
// health badge - a requirement is only as healthy as its worst link.
const STATE_SEVERITY: Record<RequirementLink['state'], number> = {
  suspect: 0,
  stale: 1,
  orphaned: 2,
  covered: 3,
};

type Health = { label: RequirementLink['state'] | 'uncovered'; className: string };

function rollUpHealth(req: CoverageEntry, reqLinks: RequirementLink[]): Health {
  if (reqLinks.length > 0) {
    const worst = reqLinks.reduce((a, b) => (STATE_SEVERITY[a.state] <= STATE_SEVERITY[b.state] ? a : b));
    return { label: worst.state, className: LINK_STATE_CLASS[worst.state] };
  }
  // No synced link yet even though linked_test_count may be >0 (sync runs
  // lazily on the Link Health fetch) - fall back to coverage's own signal
  // rather than showing nothing.
  return req.covered ? { label: 'covered', className: 'status-passed' } : { label: 'uncovered', className: 'status-failed' };
}

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

// The detail panel for whichever requirement row is currently selected -
// no longer nested inside that row (there's no per-row "Show links" button
// anymore), just rendered once below the requirements table.
function LinkDetailTable({
  reqLinks,
  reviewingId,
  onReview,
}: {
  reqLinks: RequirementLink[];
  reviewingId: number | null;
  onReview: (linkId: number) => void;
}) {
  return (
    <table className="inventory-table">
      <thead>
        <tr>
          <th>Test</th>
          <th>State</th>
          <th>Last Reviewed</th>
          <th>What Changed</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {reqLinks.map((link) => (
          <tr key={link.id}>
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
                <button onClick={() => onReview(link.id)} disabled={reviewingId === link.id}>
                  {reviewingId === link.id ? 'Reviewing…' : 'Mark reviewed'}
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
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

  // Which single requirement row is selected, and whether its link-detail
  // table is open - a master/detail panel below the table instead of a
  // "Show links" button on every row.
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [linksVisible, setLinksVisible] = useState(false);

  const [gapResults, setGapResults] = useState<Record<string, GapAnalysisResponse>>({});
  const [gapErrors, setGapErrors] = useState<Record<string, string>>({});
  const [analyzingKey, setAnalyzingKey] = useState<string | null>(null);

  function load(key: string) {
    setLoading(true);
    setError(null);
    setGapResults({});
    setGapErrors({});
    setSelectedKey(null);
    setLinksVisible(false);
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

  function selectRow(key: string) {
    setSelectedKey((current) => (current === key ? null : key));
    setLinksVisible(false);
  }

  useEffect(() => {
    load(projectKey);
    // Only on mount - subsequent loads are triggered by the form submit below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const linksByKey = new Map<string, RequirementLink[]>();
  for (const link of links ?? []) {
    const existing = linksByKey.get(link.jira_key);
    if (existing) {
      existing.push(link);
    } else {
      linksByKey.set(link.jira_key, [link]);
    }
  }

  // Links whose Jira key isn't among the pulled requirements at all - an
  // orphaned link with nothing to look up a summary for - would otherwise
  // vanish entirely when the table is keyed off `data.requirements`.
  const requirementKeys = new Set((data?.requirements ?? []).map((r) => r.key));
  const unmatchedKeys = [...linksByKey.keys()].filter((k) => !requirementKeys.has(k)).sort();

  const selectedLinks = selectedKey ? linksByKey.get(selectedKey) ?? [] : [];
  const selectedGapResult = selectedKey ? gapResults[selectedKey] : undefined;
  const selectedGapError = selectedKey ? gapErrors[selectedKey] : undefined;
  // Gap analysis needs the requirement's acceptance criteria from Jira - an
  // unmatched (orphaned) key has none, so it's not offered for those rows.
  const selectedIsUnmatched = selectedKey !== null && !requirementKeys.has(selectedKey);

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
      {linksError && <p className="error">Couldn't load link health: {linksError}</p>}

      {data && (
        <>
          <p className="subtitle">
            {data.total} requirement{data.total === 1 ? '' : 's'} in {data.project_key} — {data.covered} covered,{' '}
            {data.uncovered} uncovered. Click a row to see its gap analysis and test links.
          </p>

          {data.requirements.length === 0 && unmatchedKeys.length === 0 ? (
            <p>No requirements found for this project.</p>
          ) : (
            <>
              <table className="inventory-table">
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Summary</th>
                    <th>Linked Tests</th>
                    <th>Health</th>
                  </tr>
                </thead>
                <tbody>
                  {data.requirements.map((req) => {
                    const reqLinks = linksByKey.get(req.key) ?? [];
                    const health = rollUpHealth(req, reqLinks);
                    return (
                      <tr
                        key={req.key}
                        className={`clickable-row${selectedKey === req.key ? ' selected-row' : ''}`}
                        onClick={() => selectRow(req.key)}
                      >
                        <td>
                          <JiraKeyLink jiraKey={req.key} siteUrl={siteUrl} />
                        </td>
                        <td>{req.summary}</td>
                        <td>{req.linked_test_count}</td>
                        <td>
                          <span className={`status ${health.className}`}>{health.label}</span>
                        </td>
                      </tr>
                    );
                  })}

                  {unmatchedKeys.map((key) => {
                    const reqLinks = linksByKey.get(key) ?? [];
                    return (
                      <tr
                        key={key}
                        className={`clickable-row${selectedKey === key ? ' selected-row' : ''}`}
                        onClick={() => selectRow(key)}
                      >
                        <td>
                          <JiraKeyLink jiraKey={key} siteUrl={siteUrl} />
                        </td>
                        <td className="subtitle">(no longer resolves in Jira)</td>
                        <td>{reqLinks.length}</td>
                        <td>
                          <span className={`status ${LINK_STATE_CLASS.orphaned}`}>orphaned</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {selectedKey && (
                <div className="detail-panel">
                  <div className="detail-toolbar">
                    <span className="jira-key">{selectedKey}</span>
                    {!selectedIsUnmatched && (
                      <button onClick={() => analyzeGaps(selectedKey)} disabled={analyzingKey === selectedKey}>
                        {analyzingKey === selectedKey
                          ? 'Analyzing…'
                          : selectedGapResult
                            ? 'Re-analyze gaps'
                            : 'Analyze gaps'}
                      </button>
                    )}
                    {selectedLinks.length > 0 && (
                      <button onClick={() => setLinksVisible((v) => !v)}>
                        {linksVisible
                          ? 'Hide links'
                          : `Show ${selectedLinks.length} link${selectedLinks.length === 1 ? '' : 's'}`}
                      </button>
                    )}
                    <button onClick={() => setSelectedKey(null)}>Close</button>
                  </div>

                  {selectedGapError && <p className="error">Gap analysis failed: {selectedGapError}</p>}
                  {selectedGapResult && (
                    <ul className="gap-analysis-list">
                      {selectedGapResult.criteria.map((c, i) => (
                        <li key={i}>
                          <span className={`status ${c.covered ? 'status-passed' : 'status-failed'}`}>
                            {c.covered ? 'covered' : 'gap'}
                          </span>{' '}
                          <strong>{c.criterion}</strong> — {c.reasoning}
                        </li>
                      ))}
                    </ul>
                  )}
                  {linksVisible && selectedLinks.length > 0 && (
                    <LinkDetailTable reqLinks={selectedLinks} reviewingId={reviewingId} onReview={reviewLink} />
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}
    </>
  );
}
