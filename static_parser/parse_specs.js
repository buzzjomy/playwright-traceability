#!/usr/bin/env node
// Static AST reader for Playwright .spec.ts files.
//
// Finds every `test(...)` definition (including test.skip/.only/.fixme/.fail
// and tests nested in test.describe blocks), whether or not it ever ran, so
// callers can catch tests and Jira annotations that a JSON run report would
// never show (skipped, grep-filtered out, or just never executed).
//
// Emits raw facts as JSON (title, location, tag option, leading comment
// text, assertion call source text) for parser/static_parser.py to
// interpret. Jira-key extraction and other business logic intentionally
// stay in Python, not duplicated here.
//
// Usage: node parse_specs.js <actualPath1> <displayPath1> [<actualPath2> <displayPath2> ...]
// actualPath is read from disk; displayPath is what's emitted as "file" (so
// callers can pass an absolute path to read while keeping a repo-relative
// path in the output).

"use strict";

const ts = require("typescript");
const fs = require("fs");

const TEST_LEVEL_MODIFIERS = new Set(["skip", "only", "fixme", "fail"]);

/**
 * Unwind a call target expression into its dotted member path.
 * e.g. `test` -> ["test"], `test.describe.only` -> ["test", "describe", "only"].
 * Returns null for anything that isn't a plain identifier/property-access chain
 * (e.g. a computed member access), so callers can safely ignore it.
 */
function getMemberPath(expr) {
  if (ts.isIdentifier(expr)) return [expr.text];
  if (ts.isPropertyAccessExpression(expr)) {
    const base = getMemberPath(expr.expression);
    if (!base) return null;
    return base.concat([expr.name.text]);
  }
  return null;
}

/**
 * Resolve a node to a plain string if it's a string literal or a template
 * literal with no ${...} substitutions; returns null otherwise. A dynamic
 * title (built in a loop, interpolated) can't be known statically — those
 * tests are only knowable from a real run report, by design; see CLAUDE.md.
 */
function resolveStaticString(node) {
  if (!node) return null;
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    return node.text;
  }
  return null;
}

/** Find the callback (arrow function or function expression) among a call's arguments. */
function findFunctionArgument(args) {
  return args.find((a) => ts.isArrowFunction(a) || ts.isFunctionExpression(a));
}

/**
 * Return the leftmost identifier of a fluent call/property-access chain,
 * e.g. `expect(x).not.toBe(y)` -> "expect", `page.locator(x).click()` -> "page".
 * Returns null for anything else (a computed member access, etc).
 */
function getChainRootIdentifier(node) {
  while (node) {
    if (ts.isIdentifier(node)) return node.text;
    if (ts.isCallExpression(node) || ts.isPropertyAccessExpression(node)) {
      node = node.expression;
      continue;
    }
    return null;
  }
  return null;
}

/**
 * Recursively collect the source text of every `expect(...)`-rooted call in
 * a test body, e.g. `expect(page.getByRole('button')).toBeVisible()` - this
 * is the raw signal semantic gap detection (issue #21) compares against a
 * requirement's acceptance criteria. Stops descending once a chain matches,
 * so an assertion's own arguments (a locator, an expected value) aren't
 * misread as further assertions.
 */
function collectAssertions(node, sourceFile, out) {
  if (
    ts.isCallExpression(node) &&
    getChainRootIdentifier(node.expression) === "expect"
  ) {
    out.push(node.getText(sourceFile));
    return;
  }
  ts.forEachChild(node, (child) => collectAssertions(child, sourceFile, out));
}

/** Find the `{ tag: ..., annotation: ... }` details object among a call's arguments, if any. */
function findOptionsObjectArgument(args) {
  return args.find((a) => ts.isObjectLiteralExpression(a));
}

/**
 * Read the `tag` property off a test's details object (the 2nd argument to
 * `test(title, { tag: ... }, fn)`), normalized to an array of strings
 * whether it was written as a single string or an array literal.
 */
function extractTagOption(optionsArg) {
  if (!optionsArg) return [];
  const tagProp = optionsArg.properties.find(
    (p) =>
      ts.isPropertyAssignment(p) &&
      ts.isIdentifier(p.name) &&
      p.name.text === "tag",
  );
  if (!tagProp) return [];
  const init = tagProp.initializer;
  if (ts.isStringLiteralLike(init)) return [init.text];
  if (ts.isArrayLiteralExpression(init)) {
    return init.elements.filter(ts.isStringLiteralLike).map((e) => e.text);
  }
  return [];
}

/**
 * Get the raw text of any comment lines immediately preceding a node (e.g.
 * a "// Trace(Jira:PROJ-13)" line above a test), concatenated. Returns ""
 * if there are none.
 */
function getLeadingCommentsText(node, sourceFile) {
  const fullText = sourceFile.getFullText();
  const ranges =
    ts.getLeadingCommentRanges(fullText, node.getFullStart()) || [];
  return ranges.map((r) => fullText.slice(r.pos, r.end)).join("\n");
}

/**
 * Parse one .spec.ts file and return one raw record per statically-titled
 * `test(...)` definition found in it (see `visit` for the traversal rules).
 * `filePath` is read from disk; `displayPath` is what's emitted as "file".
 */
function parseFile(filePath, displayPath) {
  const text = fs.readFileSync(filePath, "utf8");
  const sourceFile = ts.createSourceFile(
    filePath,
    text,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  const records = [];

  /**
   * Record a `test(...)`-family call as one raw fact, unless its title
   * can't be statically resolved (in which case it's silently skipped).
   */
  function handleTest(node, ancestors) {
    const title = resolveStaticString(node.arguments[0]);
    if (title === null) return;

    const optionsArg = findOptionsObjectArgument(node.arguments);
    const fnArg = findFunctionArgument(node.arguments);
    const pos = sourceFile.getLineAndCharacterOfPosition(node.getStart());

    const assertions = [];
    if (fnArg && fnArg.body) {
      collectAssertions(fnArg.body, sourceFile, assertions);
    }

    records.push({
      title,
      ancestors: ancestors.slice(),
      file: displayPath,
      line: pos.line + 1,
      column: pos.character + 1,
      tag_option: extractTagOption(optionsArg),
      leading_comment_text: getLeadingCommentsText(node, sourceFile),
      assertions,
    });
  }

  /**
   * Handle a `test.describe(...)`-family call: recurse into its callback
   * body with the describe's title (if statically resolvable) pushed onto
   * the ancestor chain, so nested tests get the right full_title.
   */
  function handleDescribe(node, ancestors) {
    const title = resolveStaticString(node.arguments[0]);
    const fnArg = findFunctionArgument(node.arguments);
    if (!fnArg || !fnArg.body) return;
    visit(fnArg.body, title ? ancestors.concat([title]) : ancestors);
  }

  /**
   * Recursively walk the AST looking for `test`-namespaced calls: a bare
   * `test(...)` or `test.skip/only/fixme/fail(...)` is recorded as a test;
   * `test.describe(...)` (including its `.only`/`.skip`/`.fixme` variants)
   * recurses into its body via handleDescribe and is not walked again here.
   * Everything else is walked generically so nested calls are still found.
   */
  function visit(node, ancestors) {
    if (ts.isCallExpression(node)) {
      const memberPath = getMemberPath(node.expression);
      if (memberPath && memberPath[0] === "test") {
        if (memberPath.length === 1) {
          handleTest(node, ancestors);
        } else if (memberPath[1] === "describe") {
          handleDescribe(node, ancestors);
          return; // already recursed into the body above with updated ancestors
        } else if (
          memberPath.length === 2 &&
          TEST_LEVEL_MODIFIERS.has(memberPath[1])
        ) {
          handleTest(node, ancestors);
        }
      }
    }
    ts.forEachChild(node, (child) => visit(child, ancestors));
  }

  visit(sourceFile, []);
  return records;
}

/** Read all of stdin as a single UTF-8 string. */
function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

/**
 * CLI entry point: parse (actualPath, displayPath) pairs and print every
 * file's records as one combined JSON array to stdout.
 *
 * Pairs come from argv by default, or from a JSON array of
 * [actualPath, displayPath] pairs on stdin with `--stdin` - needed once a
 * project has enough spec files that passing every path pair as CLI
 * arguments risks the OS's ARG_MAX limit (parser/static_parser.py switches
 * to this mode).
 */
async function main() {
  const args = process.argv.slice(2);

  if (args[0] === "--stdin") {
    const raw = await readStdin();
    const pathPairs = JSON.parse(raw);
    const allRecords = [];
    for (const [actualPath, displayPath] of pathPairs) {
      allRecords.push(...parseFile(actualPath, displayPath));
    }
    process.stdout.write(JSON.stringify(allRecords, null, 2));
    return;
  }

  if (args.length === 0 || args.length % 2 !== 0) {
    console.error(
      "Usage: node parse_specs.js <actualPath1> <displayPath1> [<actualPath2> <displayPath2> ...]\n" +
        "       node parse_specs.js --stdin   (reads a JSON array of [actualPath, displayPath] pairs from stdin)",
    );
    process.exit(1);
  }

  const allRecords = [];
  for (let i = 0; i < args.length; i += 2) {
    allRecords.push(...parseFile(args[i], args[i + 1]));
  }

  process.stdout.write(JSON.stringify(allRecords, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
