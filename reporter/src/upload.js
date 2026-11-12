"use strict";

const INGEST_PATH = "/api/ingest/playwright";

/**
 * POST the payload to the backend. Resolves to {ok, status, detail}; never
 * throws - a reporting problem must not fail the customer's test run.
 * `fetchImpl` is injectable for tests.
 */
async function upload({ url, apiKey, payload, timeoutMs = 20000, fetchImpl = fetch }) {
  const endpoint = url.replace(/\/+$/, "") + INGEST_PATH;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${apiKey}` },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (response.ok) return { ok: true, status: response.status, detail: null };
    let detail = null;
    try {
      detail = (await response.json()).detail ?? null;
    } catch {
      /* body wasn't JSON */
    }
    return { ok: false, status: response.status, detail };
  } catch (err) {
    return { ok: false, status: null, detail: err.name === "AbortError" ? `timed out after ${timeoutMs}ms` : err.message };
  } finally {
    clearTimeout(timer);
  }
}

module.exports = { upload, INGEST_PATH };
