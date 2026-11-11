import React, { useEffect, useState } from 'react';
import {
  Button,
  DynamicTable,
  Inline,
  Link,
  Lozenge,
  SectionMessage,
  Spinner,
  Stack,
  Text,
  Textfield,
} from '@forge/react';
import { fetchCoverage, fetchRequirementLinks } from './lib/forgeApi';
import { groupLinksByKey, linkStateAppearance, rollUpHealth, unmatchedKeys } from './lib/health';
import { jiraBrowseUrl } from './lib/inventory';

// Ported from frontend/src/CoverageView.tsx (issue #31: table + row
// selection; the detail panel is issue #32). UI Kit's DynamicTable has no
// row-click, so the Key cell holds a Button; the selected row is shown by
// that button's appearance (primary vs subtle) - there's no row background.

const DEFAULT_PROJECT_KEY = 'KAN';

const head = {
  cells: [
    { key: 'key', content: 'Key' },
    { key: 'summary', content: 'Summary' },
    { key: 'tests', content: 'Linked Tests' },
    { key: 'health', content: 'Health' },
  ],
};

/** Key cell: a select button, plus a link out to the Jira ticket when connected. */
const KeyCell = ({ jiraKey, selected, onSelect, siteUrl }) => {
  const url = jiraBrowseUrl(siteUrl, jiraKey);
  return (
    <Inline space="space.100" alignBlock="center">
      <Button appearance={selected ? 'primary' : 'subtle'} spacing="compact" onClick={() => onSelect(jiraKey)}>
        {jiraKey}
      </Button>
      {url && (
        <Link href={url} openNewTab>
          ↗
        </Link>
      )}
    </Inline>
  );
};

const HealthCell = ({ health }) => <Lozenge appearance={linkStateAppearance(health)}>{health}</Lozenge>;

export const CoverageView = ({ siteUrl }) => {
  const [inputValue, setInputValue] = useState(DEFAULT_PROJECT_KEY);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [links, setLinks] = useState(null);
  const [linksError, setLinksError] = useState(null);
  // Used by the detail panel (issue #32); toggles off on re-click.
  const [selectedKey, setSelectedKey] = useState(null);

  const load = (key) => {
    setLoading(true);
    setError(null);
    setLinksError(null);
    setSelectedKey(null);
    fetchCoverage(key)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
    fetchRequirementLinks(key)
      .then((result) => setLinks(result.links))
      .catch((err) => setLinksError(err.message));
  };

  useEffect(() => {
    load(DEFAULT_PROJECT_KEY);
  }, []);

  const selectRow = (key) => setSelectedKey((current) => (current === key ? null : key));

  const linksByKey = groupLinksByKey(links ?? []);
  const requirements = data?.requirements ?? [];
  const orphanKeys = unmatchedKeys(linksByKey, requirements);

  const rows = [
    ...requirements.map((req) => ({
      key: req.key,
      cells: [
        {
          key: 'key',
          content: <KeyCell jiraKey={req.key} selected={selectedKey === req.key} onSelect={selectRow} siteUrl={siteUrl} />,
        },
        { key: 'summary', content: req.summary },
        { key: 'tests', content: String(req.linked_test_count) },
        { key: 'health', content: <HealthCell health={rollUpHealth(req, linksByKey.get(req.key) ?? [])} /> },
      ],
    })),
    ...orphanKeys.map((key) => ({
      key,
      cells: [
        { key: 'key', content: <KeyCell jiraKey={key} selected={selectedKey === key} onSelect={selectRow} siteUrl={siteUrl} /> },
        { key: 'summary', content: '(no longer resolves in Jira)' },
        { key: 'tests', content: String(linksByKey.get(key).length) },
        { key: 'health', content: <HealthCell health="orphaned" /> },
      ],
    })),
  ];

  return (
    <Stack space="space.200">
      <Inline space="space.100" alignBlock="center">
        <Textfield
          name="project-key"
          aria-label="Jira project key"
          defaultValue={DEFAULT_PROJECT_KEY}
          onChange={(e) => setInputValue(e.target.value)}
        />
        <Button appearance="primary" isDisabled={loading || !inputValue.trim()} onClick={() => load(inputValue.trim())}>
          {loading ? 'Loading…' : 'Load coverage'}
        </Button>
      </Inline>

      {error && (
        <SectionMessage appearance="error" title="Couldn't load coverage">
          <Text>{error}</Text>
        </SectionMessage>
      )}
      {linksError && (
        <SectionMessage appearance="error" title="Couldn't load link health">
          <Text>{linksError}</Text>
        </SectionMessage>
      )}

      {loading && !data && <Spinner size="medium" />}
      {data && (
        <Stack space="space.200">
          <Text>
            {data.total} requirement{data.total === 1 ? '' : 's'} in {data.project_key} — {data.covered} covered,{' '}
            {data.uncovered} uncovered. Select a key to see its details.
          </Text>
          {rows.length === 0 ? (
            <Text>No requirements found for this project.</Text>
          ) : (
            <DynamicTable head={head} rows={rows} rowsPerPage={25} />
          )}
        </Stack>
      )}
    </Stack>
  );
};
