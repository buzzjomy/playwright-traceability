import React, { useEffect, useState } from 'react';
import { DynamicTable, Inline, Link, Lozenge, SectionMessage, Spinner, Stack, Text, Tooltip } from '@forge/react';
import { fetchInventory } from './lib/forgeApi';
import {
  jiraBrowseUrl,
  statusAppearance,
  statusLabel,
  summarizeHistory,
  trendSymbol,
  trendWindow,
} from './lib/inventory';

// Ported from frontend/src/InventoryView.tsx. UI Kit has no free-form CSS, so
// the status/flaky/"not in source" badges are Lozenges in Atlassian's own
// palette, and the per-run trend dots become a short row of Lozenges under
// ONE Tooltip with a text summary (Tooltip wraps a single element).

const head = {
  cells: [
    { key: 'title', content: 'Title' },
    { key: 'file', content: 'File' },
    { key: 'project', content: 'Project' },
    { key: 'status', content: 'Status' },
    { key: 'trend', content: 'Trend' },
    { key: 'tags', content: 'Tags' },
    { key: 'jira', content: 'Jira Keys' },
  ],
};

/** Status badge plus the "not in source" and "flaky" warnings, in one cell. */
const StatusCell = ({ entry }) => {
  const label = statusLabel(entry);
  return (
    <Inline space="space.050" shouldWrap>
      <Lozenge appearance={statusAppearance(label)}>{label}</Lozenge>
      {!entry.in_source && <Lozenge appearance="warning">not in source</Lozenge>}
      {entry.is_flaky && <Lozenge appearance="moved">flaky</Lozenge>}
    </Inline>
  );
};

/** The last few runs as tiny badges; hovering shows a one-line summary. */
const TrendCell = ({ history }) => {
  if (history.length === 0) return <Text>—</Text>;
  return (
    <Tooltip content={summarizeHistory(history)}>
      <Inline space="space.025">
        {trendWindow(history).map((point, i) => (
          <Lozenge key={`${point.run_id}-${i}`} appearance={statusAppearance(point.status)}>
            {trendSymbol(point.status)}
          </Lozenge>
        ))}
      </Inline>
    </Tooltip>
  );
};

/** Each Jira key as a link to the real ticket, or plain text without a connection. */
const JiraKeysCell = ({ keys, siteUrl }) => {
  if (keys.length === 0) return <Text>—</Text>;
  return (
    <Inline space="space.100" shouldWrap>
      {keys.map((key) => {
        const url = jiraBrowseUrl(siteUrl, key);
        return url ? (
          <Link key={key} href={url} openNewTab>
            {key}
          </Link>
        ) : (
          <Text key={key}>{key}</Text>
        );
      })}
    </Inline>
  );
};

const toRow = (entry, index, siteUrl) => ({
  key: `${entry.file}:${entry.title}:${entry.project ?? ''}:${index}`,
  cells: [
    { key: 'title', content: entry.title },
    { key: 'file', content: entry.file },
    { key: 'project', content: entry.project ?? '—' },
    { key: 'status', content: <StatusCell entry={entry} /> },
    { key: 'trend', content: <TrendCell history={entry.history} /> },
    { key: 'tags', content: entry.tags.join(', ') || '—' },
    { key: 'jira', content: <JiraKeysCell keys={entry.jira_keys} siteUrl={siteUrl} /> },
  ],
});

export const InventoryView = ({ siteUrl }) => {
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchInventory()
      .then((data) => setEntries(data.entries))
      .catch((err) => setError(err.message));
  }, []);

  if (error) {
    return (
      <SectionMessage appearance="error" title="Couldn't load the inventory">
        <Text>{error}</Text>
      </SectionMessage>
    );
  }
  if (entries === null) return <Spinner size="medium" />;
  if (entries.length === 0) {
    return <Text>No tests found yet. Push some data via scripts/push_test_inventory.py.</Text>;
  }

  // A Stack, not a fragment: UI Kit lays a fragment's children out side by
  // side, which put the summary line to the left of the table.
  return (
    <Stack space="space.200">
      <Text>
        {entries.length} test{entries.length === 1 ? '' : 's'} — reconciled from run reports and static source scans.
      </Text>
      <DynamicTable head={head} rows={entries.map((entry, i) => toRow(entry, i, siteUrl))} rowsPerPage={25} />
    </Stack>
  );
};
