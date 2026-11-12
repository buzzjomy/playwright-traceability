"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const { upload } = require("../src/upload");

const response = (status, body) => ({ ok: status < 300, status, json: async () => body });

test("posts JSON to the ingest endpoint with the bearer key", async () => {
  let seen;
  const fetchImpl = async (url, init) => ((seen = { url, init }), response(200, {}));
  const result = await upload({ url: "https://host/", apiKey: "k", payload: { a: 1 }, fetchImpl });
  assert.equal(result.ok, true);
  assert.equal(seen.url, "https://host/api/ingest/playwright");
  assert.equal(seen.init.headers.authorization, "Bearer k");
  assert.deepEqual(JSON.parse(seen.init.body), { a: 1 });
});

test("reports a rejection with the server's detail, never throwing", async () => {
  const result = await upload({ url: "https://h", apiKey: "k", payload: {}, fetchImpl: async () => response(401, { detail: "bad key" }) });
  assert.deepEqual(result, { ok: false, status: 401, detail: "bad key" });
});

test("a network failure is a result, not an exception", async () => {
  const result = await upload({ url: "https://h", apiKey: "k", payload: {}, fetchImpl: async () => { throw new Error("ECONNREFUSED"); } });
  assert.deepEqual([result.ok, result.status, result.detail], [false, null, "ECONNREFUSED"]);
});

test("a hung server times out instead of hanging the run", async () => {
  const fetchImpl = (url, { signal }) => new Promise((_, reject) => signal.addEventListener("abort", () => reject(Object.assign(new Error("x"), { name: "AbortError" }))));
  const result = await upload({ url: "https://h", apiKey: "k", payload: {}, timeoutMs: 30, fetchImpl });
  assert.equal(result.ok, false);
  assert.match(result.detail, /timed out/);
});
