// Pure presentation logic for the Test Inventory view, ported from
// frontend/src/InventoryView.tsx (statusLabel/statusClassName/TrendDots).
// Kept free of UI Kit imports so it can be unit-tested with plain node.

// How many of a test's most recent runs the trend column shows.
export const MAX_TREND_POINTS = 5;

/** The status text for an inventory entry: "never run" until it has a run. */
export function statusLabel(entry) {
  if (!entry.has_run) return 'never run';
  return entry.status ?? 'unknown';
}

/**
 * Map a Playwright status string onto a UI Kit Lozenge `appearance`.
 * UI Kit only allows Atlassian's own palette (no custom hex), so the old
 * dashboard's green/red/amber/gray become success/removed/moved/default.
 */
export function statusAppearance(status) {
  switch (status) {
    case 'passed':
      return 'success';
    case 'failed':
    case 'unexpected':
    case 'timedOut':
    case 'interrupted':
      return 'removed';
    case 'flaky':
      return 'moved';
    default:
      return 'default';
  }
}

const TREND_SYMBOLS = { passed: '✓', failed: '✕', unexpected: '✕', timedOut: '✕', interrupted: '✕', flaky: '~', skipped: '–' };

/** A one-character stand-in for a run's status, shown inside a Lozenge. */
export function trendSymbol(status) {
  return TREND_SYMBOLS[status] ?? '?';
}

/** The most recent MAX_TREND_POINTS runs, oldest first (as the backend sends them). */
export function trendWindow(history) {
  return history.slice(-MAX_TREND_POINTS);
}

/**
 * Plain-text summary of the trend window, used as the tooltip: UI Kit's
 * Tooltip wraps one element, so the old per-dot hover text becomes one
 * summary for the whole group, e.g. "3 passed, 1 failed - latest: passed".
 */
export function summarizeHistory(history) {
  const window = trendWindow(history);
  if (window.length === 0) return 'No runs yet';

  const counts = new Map();
  for (const point of window) {
    counts.set(point.status, (counts.get(point.status) ?? 0) + 1);
  }
  const parts = [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([status, count]) => `${count} ${status}`);

  return `${parts.join(', ')} - latest: ${window[window.length - 1].status}`;
}

/** Link to the real Jira ticket, or null when no Jira connection is known. */
export function jiraBrowseUrl(siteUrl, jiraKey) {
  if (!siteUrl) return null;
  return `${siteUrl.replace(/\/$/, '')}/browse/${jiraKey}`;
}
