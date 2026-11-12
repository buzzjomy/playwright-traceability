"use strict";

const { toRepoRelative } = require("./paths");

/**
 * Build a report in the shape of Playwright's own JSON reporter from the live
 * Suite tree, so the backend can feed it to the same Python parser as a real
 * `--reporter=json` file (parser/report_parser.py) instead of a second,
 * JavaScript copy of those rules.
 *
 * Differences from the real thing are deliberate and small: file paths are
 * already relative to the repo root (not Playwright's rootDir), because that
 * is what the static scan uses and what reconciliation matches on.
 *
 * `suite` is the root Suite from onBegin. Tests from every project are folded
 * into one spec per (file, describe path, title, location) with one `tests`
 * entry per project, exactly as the JSON reporter does.
 */
function buildReport(suite, repoRoot) {
  const files = new Map(); // file -> { suite, specs: Map<key, spec> }

  for (const test of suite.allTests()) {
    const file = toRepoRelative(test.location.file, repoRoot);
    const describes = describeTitles(test);
    const key = [describes.join("\u0001"), test.title, test.location.line, test.location.column].join("\u0002");

    let entry = files.get(file);
    if (!entry) {
      entry = { title: file, file, specs: new Map() };
      files.set(file, entry);
    }

    const groupKey = key;
    let spec = entry.specs.get(groupKey);
    if (!spec) {
      spec = {
        describes,
        id: test.id,
        title: test.title,
        file,
        line: test.location.line,
        column: test.location.column,
        tags: [...(test.tags || [])],
        tests: [],
      };
      entry.specs.set(groupKey, spec);
    }
    spec.tests.push(serializeTest(test));
  }

  return { suites: [...files.values()].map(nestDescribes) };
}

/** Titles of the describe blocks enclosing a test, outermost first. */
function describeTitles(test) {
  const titles = [];
  for (let parent = test.parent; parent; parent = parent.parent) {
    if (parent.type === "describe" && parent.title) titles.unshift(parent.title);
  }
  return titles;
}

function serializeTest(test) {
  return {
    projectName: projectNameOf(test),
    annotations: (test.annotations || []).map((a) => ({ type: a.type, description: a.description })),
    status: test.outcome(),
    results: test.results.map((r) => ({
      status: r.status,
      duration: Math.round(r.duration),
      errors: (r.errors || []).map((e) => ({ message: e.message })),
    })),
  };
}

function projectNameOf(test) {
  for (let parent = test.parent; parent; parent = parent.parent) {
    if (parent.type === "project") return parent.title;
  }
  return "default";
}

/** Turn a file's flat specs into nested describe suites, as the JSON reporter nests them. */
function nestDescribes(fileEntry) {
  const root = { title: fileEntry.title, file: fileEntry.file, specs: [], suites: [] };
  for (const spec of fileEntry.specs.values()) {
    let node = root;
    for (const title of spec.describes) {
      let next = node.suites.find((s) => s.title === title);
      if (!next) {
        next = { title, file: fileEntry.file, specs: [], suites: [] };
        node.suites.push(next);
      }
      node = next;
    }
    const { describes, ...jsonSpec } = spec; // eslint-disable-line no-unused-vars
    node.specs.push(jsonSpec);
  }
  return root;
}

module.exports = { buildReport };
