// Waiting for a background gap analysis (issue #50), kept pure so the timing
// logic can be unit-tested without a clock or a network.

/** How often to ask, and how long to wait before giving up (a run is normally ~20-40s). */
export const POLL_INTERVAL_MS = 3000;
export const MAX_WAIT_MS = 150000;

const realSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Poll `fetchResult()` until the analysis is no longer pending, and return
 * that final status ({status: 'done' | 'failed' | 'none', ...}).
 *
 * - A `none` answer (the run vanished) and a timeout both come back as a
 *   `failed` status with a message, so callers handle exactly two outcomes.
 * - A poll that throws (a blip, a cold start) is retried until the deadline
 *   rather than abandoning a run that is still going on the server.
 * - `isCancelled()` stops the loop (the view went away) and returns null.
 */
export async function waitForGapResult(
  fetchResult,
  { intervalMs = POLL_INTERVAL_MS, maxWaitMs = MAX_WAIT_MS, sleep = realSleep, isCancelled = () => false } = {},
) {
  let waited = 0;
  let lastError = null;
  while (waited <= maxWaitMs) {
    if (isCancelled()) return null;
    try {
      const result = await fetchResult();
      lastError = null;
      if (result.status === 'done' || result.status === 'failed') return result;
      if (result.status === 'none') return { ...result, status: 'failed', error: 'The analysis could not be found - please run it again.' };
    } catch (err) {
      lastError = err;
    }
    await sleep(intervalMs);
    waited += intervalMs;
  }
  return {
    status: 'failed',
    error: lastError ? `Couldn't get the result: ${lastError.message}` : 'The analysis is taking longer than expected - please try again.',
  };
}
