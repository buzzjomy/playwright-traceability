"use strict";

const fs = require("fs");
const path = require("path");
const { resolveOptions } = require("./options");
const { findRepoRoot } = require("./paths");
const { buildReport } = require("./serialize");
const { scanSpecs } = require("./scan");
const { upload } = require("./upload");

/**
 * Playwright reporter: after the run, upload the results (and a static scan of
 * your specs) to Playwright Traceability.
 *
 *   // playwright.config.ts
 *   reporter: [["list"], ["playwright-traceability-reporter"]],
 *
 * It only prints a short status line and NEVER changes the run's outcome: any
 * problem (no key, server down, a scan error) is a warning, not a failure.
 */
class TraceabilityReporter {
  constructor(options = {}) {
    this.options = resolveOptions(options);
  }

  onBegin(config, suite) {
    this.config = config;
    this.suite = suite;
  }

  printsToStdio() {
    return false;
  }

  async onEnd() {
    const log = (message) => console.log(`[traceability] ${message}`);
    try {
      const { apiKey, url, outputFile, timeoutMs } = this.options;
      if (!apiKey && !outputFile) {
        log("skipped: set TRACEABILITY_INGEST_KEY (generate one in the app's Settings tab) to upload results.");
        return;
      }

      const repoRoot = findRepoRoot(this.config.rootDir);
      const payload = { report: buildReport(this.suite, repoRoot), static_facts: this.scan(repoRoot, log) };

      if (outputFile) fs.writeFileSync(outputFile, JSON.stringify(payload, null, 2));
      if (!apiKey) return;

      const result = await upload({ url, apiKey, payload, timeoutMs });
      if (result.ok) {
        log(`uploaded ${this.suite.allTests().length} test results to ${url}`);
      } else if (result.status === 401) {
        log("upload rejected: the ingest key is missing or wrong (generate a new one in the app's Settings tab).");
      } else {
        log(`upload failed (${result.status ?? "no response"}${result.detail ? `: ${result.detail}` : ""}); the test run is unaffected.`);
      }
    } catch (err) {
      log(`skipped after an error: ${err.message}`);
    }
  }

  /** The static scan's raw facts, or null if disabled or it failed (results still upload). */
  scan(repoRoot, log) {
    if (!this.options.scanSpecs) return null;
    try {
      const dir = this.options.specsDir || this.config.projects[0]?.testDir || this.config.rootDir;
      return scanSpecs(path.resolve(dir), repoRoot);
    } catch (err) {
      log(`spec scan skipped: ${err.message}`);
      return null;
    }
  }
}

module.exports = TraceabilityReporter;
