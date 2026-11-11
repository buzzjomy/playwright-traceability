// Pure presentation logic for the Requirement Coverage view, ported from
// frontend/src/CoverageView.tsx. Rendering (Lozenges) lives in CoverageView.jsx.

/** Worst-first ranking, so a requirement is only as healthy as its worst link. */
export const STATE_SEVERITY = { suspect: 0, stale: 1, orphaned: 2, covered: 3 };

/** Lozenge appearance for a link state or rolled-up health label. */
export function linkStateAppearance(state) {
  switch (state) {
    case 'covered':
      return 'success';
    case 'suspect':
      return 'moved';
    case 'stale':
    case 'orphaned':
    case 'uncovered':
      return 'removed';
    default:
      return 'default';
  }
}

/**
 * Roll one requirement's links up into a single health label. With no synced
 * link yet (sync runs lazily on the links fetch), fall back to the coverage
 * endpoint's own covered flag rather than showing nothing.
 */
export function rollUpHealth(requirement, links) {
  if (links.length > 0) {
    const worst = links.reduce((a, b) => (STATE_SEVERITY[a.state] <= STATE_SEVERITY[b.state] ? a : b));
    return worst.state;
  }
  return requirement.covered ? 'covered' : 'uncovered';
}

/** Group links by Jira key, preserving link order within each key. */
export function groupLinksByKey(links) {
  const byKey = new Map();
  for (const link of links) {
    const existing = byKey.get(link.jira_key);
    if (existing) existing.push(link);
    else byKey.set(link.jira_key, [link]);
  }
  return byKey;
}

/**
 * Jira keys that have links but aren't among the pulled requirements (an
 * orphaned link has no summary to look up) - they'd vanish from a table
 * keyed only off the requirements list.
 */
export function unmatchedKeys(linksByKey, requirements) {
  const known = new Set(requirements.map((r) => r.key));
  return [...linksByKey.keys()].filter((k) => !known.has(k)).sort();
}
