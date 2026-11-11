import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  MAX_TREND_POINTS,
  jiraBrowseUrl,
  statusAppearance,
  statusLabel,
  summarizeHistory,
  trendSymbol,
  trendWindow,
} from './inventory.js';

const point = (status) => ({ run_id: 1, pushed_at: '2026-01-01T00:00:00', status });

test('statusLabel is "never run" until the test has a run', () => {
  assert.equal(statusLabel({ has_run: false, status: null }), 'never run');
  assert.equal(statusLabel({ has_run: true, status: 'passed' }), 'passed');
  assert.equal(statusLabel({ has_run: true, status: null }), 'unknown');
});

test('statusAppearance maps statuses onto the Atlassian palette', () => {
  assert.equal(statusAppearance('passed'), 'success');
  for (const failing of ['failed', 'unexpected', 'timedOut', 'interrupted']) {
    assert.equal(statusAppearance(failing), 'removed');
  }
  assert.equal(statusAppearance('flaky'), 'moved');
  assert.equal(statusAppearance('skipped'), 'default');
  assert.equal(statusAppearance('never run'), 'default');
});

test('trendSymbol falls back to ? for unknown statuses', () => {
  assert.equal(trendSymbol('passed'), '✓');
  assert.equal(trendSymbol('failed'), '✕');
  assert.equal(trendSymbol('something-new'), '?');
});

test('trendWindow keeps only the most recent runs, oldest first', () => {
  const history = Array.from({ length: MAX_TREND_POINTS + 3 }, (_, i) => ({ ...point('passed'), run_id: i }));
  const window = trendWindow(history);
  assert.equal(window.length, MAX_TREND_POINTS);
  assert.equal(window[window.length - 1].run_id, MAX_TREND_POINTS + 2);
});

test('summarizeHistory counts statuses and names the latest', () => {
  const history = [point('failed'), point('passed'), point('passed'), point('passed'), point('passed')];
  assert.equal(summarizeHistory(history), '4 passed, 1 failed - latest: passed');
});

test('summarizeHistory only counts the trend window, not older runs', () => {
  const history = [point('failed'), point('failed'), ...Array.from({ length: MAX_TREND_POINTS }, () => point('passed'))];
  assert.equal(summarizeHistory(history), `${MAX_TREND_POINTS} passed - latest: passed`);
});

test('summarizeHistory handles an empty history', () => {
  assert.equal(summarizeHistory([]), 'No runs yet');
});

test('jiraBrowseUrl strips a trailing slash and returns null without a site', () => {
  assert.equal(jiraBrowseUrl('https://x.atlassian.net/', 'KAN-4'), 'https://x.atlassian.net/browse/KAN-4');
  assert.equal(jiraBrowseUrl(null, 'KAN-4'), null);
});
