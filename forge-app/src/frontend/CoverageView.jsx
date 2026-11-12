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
  useProductContext,
} from '@forge/react';
import { fetchCoverage, fetchGapAnalysis, fetchRequirementLinks, markLinkReviewed } from './lib/forgeApi';
import { groupLinksByKey, linkStateAppearance, rollUpHealth, unmatchedKeys } from './lib/health';
import { jiraBrowseUrl } from './lib/inventory';
import { projectKeyFromContext, resolveProjectKey } from './lib/projectContext';

// Ported from frontend/src/CoverageView.tsx (issues #31/#32: table + row
// selection, and the detail panel below it). UI Kit's DynamicTable has no
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

const linkHead = {
  cells: [
    { key: 'test', content: 'Test' },
    { key: 'state', content: 'State' },
    { key: 'reviewed', content: 'Last Reviewed' },
    { key: 'changed', content: 'What Changed' },
    { key: 'action', content: '' },
  ],
};

/** Per-test link rows for the selected requirement; Suspect rows get "Mark reviewed". */
const LinkDetailTable = ({ links, reviewingId, onReview }) => (
  <DynamicTable
    head={linkHead}
    rows={links.map((link) => ({
      key: String(link.id),
      cells: [
        { key: 'test', content: `${link.test_file} — ${link.test_title}` },
        { key: 'state', content: <Lozenge appearance={linkStateAppearance(link.state)}>{link.state}</Lozenge> },
        { key: 'reviewed', content: link.last_reviewed_at ? new Date(link.last_reviewed_at).toLocaleString() : '—' },
        { key: 'changed', content: link.change_summary ?? '—' },
        {
          key: 'action',
          content:
            link.state === 'suspect' ? (
              <Button isDisabled={reviewingId === link.id} onClick={() => onReview(link.id)}>
                {reviewingId === link.id ? 'Reviewing…' : 'Mark reviewed'}
              </Button>
            ) : (
              ''
            ),
        },
      ],
    }))}
  />
);

/** One Lozenge + criterion + reasoning per acceptance criterion. */
const GapList = ({ criteria }) => (
  <Stack space="space.100">
    {criteria.map((c, i) => (
      <Inline key={i} space="space.100" shouldWrap>
        <Lozenge appearance={c.covered ? 'success' : 'removed'}>{c.covered ? 'covered' : 'gap'}</Lozenge>
        <Text>
          {c.criterion} — {c.reasoning}
        </Text>
      </Inline>
    ))}
  </Stack>
);

export const CoverageView = ({ siteUrl }) => {
  // Inside Jira the project comes from the page we're embedded in; the
  // Textfield stays as a manual override (and the fallback when there's no
  // project context). The context arrives asynchronously, so the first load
  // waits for it instead of flashing the fallback project.
  const context = useProductContext();
  const detectedKey = projectKeyFromContext(context);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [links, setLinks] = useState(null);
  const [linksError, setLinksError] = useState(null);
  // Which requirement's detail panel is open; toggles off on re-click.
  const [selectedKey, setSelectedKey] = useState(null);
  const [linksVisible, setLinksVisible] = useState(false);
  const [reviewingId, setReviewingId] = useState(null);
  const [gapResults, setGapResults] = useState({});
  const [gapErrors, setGapErrors] = useState({});
  const [analyzingKey, setAnalyzingKey] = useState(null);
  // The project the loaded data belongs to (the input may have been edited since).
  const [loadedKey, setLoadedKey] = useState(DEFAULT_PROJECT_KEY);
  const [autoLoaded, setAutoLoaded] = useState(false);

  const load = (key) => {
    setLoading(true);
    setError(null);
    setLinksError(null);
    setSelectedKey(null);
    setLinksVisible(false);
    setGapResults({});
    setGapErrors({});
    setLoadedKey(key);
    fetchCoverage(key)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
    fetchRequirementLinks(key)
      .then((result) => setLinks(result.links))
      .catch((err) => setLinksError(err.message));
  };

  useEffect(() => {
    if (context === undefined || autoLoaded) return;
    setAutoLoaded(true);
    load(resolveProjectKey({ override: '', detected: detectedKey, fallback: DEFAULT_PROJECT_KEY }));
  }, [context]);

  const selectRow = (key) => {
    setSelectedKey((current) => (current === key ? null : key));
    setLinksVisible(false);
  };

  const reviewLink = (linkId) => {
    setReviewingId(linkId);
    markLinkReviewed(linkId)
      .then((updated) => setLinks((current) => (current ? current.map((l) => (l.id === linkId ? updated : l)) : current)))
      .catch((err) => setLinksError(err.message))
      .finally(() => setReviewingId(null));
  };

  const analyzeGaps = (jiraKey) => {
    setAnalyzingKey(jiraKey);
    setGapErrors((current) => ({ ...current, [jiraKey]: '' }));
    fetchGapAnalysis(loadedKey, jiraKey)
      .then((result) => setGapResults((current) => ({ ...current, [jiraKey]: result })))
      .catch((err) => setGapErrors((current) => ({ ...current, [jiraKey]: err.message })))
      .finally(() => setAnalyzingKey(null));
  };

  const linksByKey = groupLinksByKey(links ?? []);
  const requirements = data?.requirements ?? [];
  const orphanKeys = unmatchedKeys(linksByKey, requirements);

  const selectedLinks = selectedKey ? linksByKey.get(selectedKey) ?? [] : [];
  const selectedGapResult = selectedKey ? gapResults[selectedKey] : undefined;
  const selectedGapError = selectedKey ? gapErrors[selectedKey] : undefined;
  // An orphaned key has no acceptance criteria to pull, so gap analysis isn't offered.
  const selectedIsUnmatched = selectedKey !== null && orphanKeys.includes(selectedKey);

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
          placeholder={detectedKey ?? DEFAULT_PROJECT_KEY}
          onChange={(e) => setInputValue(e.target.value)}
        />
        <Button appearance="primary" isDisabled={loading} onClick={() => load(resolveProjectKey({ override: inputValue, detected: detectedKey, fallback: DEFAULT_PROJECT_KEY }))}>
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
          {selectedKey && (
            <Stack space="space.150">
              <Inline space="space.100" alignBlock="center" shouldWrap>
                <Text>{selectedKey}</Text>
                {!selectedIsUnmatched && (
                  <Button isDisabled={analyzingKey === selectedKey} onClick={() => analyzeGaps(selectedKey)}>
                    {analyzingKey === selectedKey ? 'Analyzing…' : selectedGapResult ? 'Re-analyze gaps' : 'Analyze gaps'}
                  </Button>
                )}
                {selectedLinks.length > 0 && (
                  <Button onClick={() => setLinksVisible((v) => !v)}>
                    {linksVisible
                      ? 'Hide links'
                      : `Show ${selectedLinks.length} link${selectedLinks.length === 1 ? '' : 's'}`}
                  </Button>
                )}
                <Button appearance="subtle" onClick={() => setSelectedKey(null)}>
                  Close
                </Button>
              </Inline>
              {selectedGapError && (
                <SectionMessage appearance="error" title="Gap analysis failed">
                  <Text>{selectedGapError}</Text>
                </SectionMessage>
              )}
              {selectedGapResult && <GapList criteria={selectedGapResult.criteria} />}
              {linksVisible && selectedLinks.length > 0 && (
                <LinkDetailTable links={selectedLinks} reviewingId={reviewingId} onReview={reviewLink} />
              )}
            </Stack>
          )}
        </Stack>
      )}
    </Stack>
  );
};
