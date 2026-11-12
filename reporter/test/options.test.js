"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const { DEFAULT_URL, resolveOptions } = require("../src/options");

test("defaults", () => {
  const o = resolveOptions({}, {});
  assert.deepEqual([o.url, o.apiKey, o.scanSpecs, o.specsDir], [DEFAULT_URL, null, true, null]);
});

test("the key comes from the environment, TRACEABILITY_INGEST_KEY first, then INGEST_API_KEY", () => {
  assert.equal(resolveOptions({}, { INGEST_API_KEY: "old" }).apiKey, "old");
  assert.equal(resolveOptions({}, { INGEST_API_KEY: "old", TRACEABILITY_INGEST_KEY: "new" }).apiKey, "new");
});

test("explicit options beat the environment; scanSpecs can be turned off", () => {
  const o = resolveOptions({ url: "https://x", scanSpecs: false }, { TRACEABILITY_URL: "https://env" });
  assert.deepEqual([o.url, o.scanSpecs], ["https://x", false]);
});
