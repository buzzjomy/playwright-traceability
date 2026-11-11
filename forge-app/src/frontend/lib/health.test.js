import assert from 'node:assert/strict';
import { test } from 'node:test';
import { groupLinksByKey, linkStateAppearance, rollUpHealth, unmatchedKeys } from './health.js';

const link = (jira_key, state) => ({ jira_key, state });

test('linkStateAppearance maps states onto the Atlassian palette', () => {
  assert.equal(linkStateAppearance('covered'), 'success');
  assert.equal(linkStateAppearance('suspect'), 'moved');
  for (const s of ['stale', 'orphaned', 'uncovered']) assert.equal(linkStateAppearance(s), 'removed');
  assert.equal(linkStateAppearance('???'), 'default');
});

test('rollUpHealth picks the worst link', () => {
  const req = { covered: true };
  assert.equal(rollUpHealth(req, [link('A', 'covered'), link('A', 'suspect'), link('A', 'stale')]), 'suspect');
  assert.equal(rollUpHealth(req, [link('A', 'covered'), link('A', 'orphaned')]), 'orphaned');
  assert.equal(rollUpHealth(req, [link('A', 'covered')]), 'covered');
});

test('rollUpHealth falls back to the coverage flag with no links', () => {
  assert.equal(rollUpHealth({ covered: true }, []), 'covered');
  assert.equal(rollUpHealth({ covered: false }, []), 'uncovered');
});

test('groupLinksByKey and unmatchedKeys find links with no matching requirement', () => {
  const grouped = groupLinksByKey([link('B', 'covered'), link('A', 'stale'), link('B', 'suspect')]);
  assert.equal(grouped.get('B').length, 2);
  assert.deepEqual(unmatchedKeys(grouped, [{ key: 'B' }]), ['A']);
});
