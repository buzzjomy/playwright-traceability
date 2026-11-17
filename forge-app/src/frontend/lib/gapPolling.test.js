import assert from 'node:assert/strict';
import { test } from 'node:test';
import { waitForGapResult } from './gapPolling.js';

const noSleep = () => Promise.resolve();
const sequence = (...results) => {
  let i = 0;
  return async () => {
    const next = results[Math.min(i++, results.length - 1)];
    if (next instanceof Error) throw next;
    return next;
  };
};

test('returns as soon as the analysis is done, after polling through pending', async () => {
  let calls = 0;
  const fetchResult = async () => (++calls < 3 ? { status: 'pending' } : { status: 'done', criteria: [] });
  const result = await waitForGapResult(fetchResult, { sleep: noSleep });
  assert.equal(result.status, 'done');
  assert.equal(calls, 3);
});

test('a failed analysis is returned as-is, with its message', async () => {
  const result = await waitForGapResult(sequence({ status: 'failed', error: 'No key' }), { sleep: noSleep });
  assert.deepEqual(result, { status: 'failed', error: 'No key' });
});

test('a vanished run (none) becomes a failure the user can act on', async () => {
  const result = await waitForGapResult(sequence({ status: 'none' }), { sleep: noSleep });
  assert.equal(result.status, 'failed');
  assert.match(result.error, /run it again/);
});

test('a poll that throws is retried, not treated as the end of the run', async () => {
  const result = await waitForGapResult(sequence(new Error('cold start'), { status: 'pending' }, { status: 'done', criteria: [] }), { sleep: noSleep });
  assert.equal(result.status, 'done');
});

test('gives up after the deadline with a message - never loops forever', async () => {
  let calls = 0;
  const result = await waitForGapResult(async () => (calls++, { status: 'pending' }), { intervalMs: 1000, maxWaitMs: 3000, sleep: noSleep });
  assert.equal(result.status, 'failed');
  assert.match(result.error, /taking longer/);
  assert.equal(calls, 4); // at 0s, 1s, 2s, 3s
});

test('if every poll fails, the last error is reported', async () => {
  const result = await waitForGapResult(sequence(new Error('offline')), { intervalMs: 1000, maxWaitMs: 2000, sleep: noSleep });
  assert.match(result.error, /offline/);
});

test('stops quietly when cancelled', async () => {
  let cancelled = false;
  const result = await waitForGapResult(async () => ((cancelled = true), { status: 'pending' }), { sleep: noSleep, isCancelled: () => cancelled });
  assert.equal(result, null);
});

test('waits the interval between polls', async () => {
  const sleeps = [];
  await waitForGapResult(sequence({ status: 'pending' }, { status: 'pending' }, { status: 'done', criteria: [] }), {
    intervalMs: 2500,
    sleep: async (ms) => sleeps.push(ms),
  });
  assert.deepEqual(sleeps, [2500, 2500]);
});
