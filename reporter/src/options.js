"use strict";

const DEFAULT_URL = "https://playwright-traceability.fly.dev";

/**
 * Resolve reporter options from the config entry and the environment.
 * The ingest key comes from the environment (never write it into
 * playwright.config.ts, which is committed): TRACEABILITY_INGEST_KEY, falling
 * back to INGEST_API_KEY - the name the Python CLI uses.
 */
function resolveOptions(options = {}, env = process.env) {
  return {
    url: options.url || env.TRACEABILITY_URL || DEFAULT_URL,
    apiKey: options.apiKey || env.TRACEABILITY_INGEST_KEY || env.INGEST_API_KEY || null,
    specsDir: options.specsDir || null, // null -> the config's testDir
    scanSpecs: options.scanSpecs !== false,
    outputFile: options.outputFile || null,
    timeoutMs: options.timeoutMs || 20000,
  };
}

module.exports = { resolveOptions, DEFAULT_URL };
