#!/usr/bin/env node
// Static AST reader for Playwright .spec.ts files.
//
// Finds every `test(...)` definition (including test.skip/.only/.fixme/.fail
// and tests nested in test.describe blocks), whether or not it ever ran, so
// callers can catch tests and Jira annotations that a JSON run report would
// never show (skipped, grep-filtered out, or just never executed).
//
// Emits raw facts as JSON (title, location, tag option, leading comment
// text) for parser/static_parser.py to interpret. Jira-key extraction and
// other business logic intentionally stay in Python, not duplicated here.
//
// Usage: node parse_specs.js <actualPath1> <displayPath1> [<actualPath2> <displayPath2> ...]
// actualPath is read from disk; displayPath is what's emitted as "file" (so
// callers can pass an absolute path to read while keeping a repo-relative
// path in the output).

'use strict';

const ts = require('typescript');
const fs = require('fs');

const TEST_LEVEL_MODIFIERS = new Set(['skip', 'only', 'fixme', 'fail']);

function getMemberPath(expr) {
  if (ts.isIdentifier(expr)) return [expr.text];
  if (ts.isPropertyAccessExpression(expr)) {
    const base = getMemberPath(expr.expression);
    if (!base) return null;
    return base.concat([expr.name.text]);
  }
  return null;
}

// Only resolves titles that are plain strings in source (string literal or
// template literal with no ${...} substitutions). A dynamic title (built in
// a loop, interpolated) can't be known statically — those tests are only
// knowable from a real run report, by design; see CLAUDE.md.
function resolveStaticString(node) {
  if (!node) return null;
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    return node.text;
  }
  return null;
}

function findFunctionArgument(args) {
  return args.find((a) => ts.isArrowFunction(a) || ts.isFunctionExpression(a));
}

function findOptionsObjectArgument(args) {
  return args.find((a) => ts.isObjectLiteralExpression(a));
}

function extractTagOption(optionsArg) {
  if (!optionsArg) return [];
  const tagProp = optionsArg.properties.find(
    (p) => ts.isPropertyAssignment(p) && ts.isIdentifier(p.name) && p.name.text === 'tag'
  );
  if (!tagProp) return [];
  const init = tagProp.initializer;
  if (ts.isStringLiteralLike(init)) return [init.text];
  if (ts.isArrayLiteralExpression(init)) {
    return init.elements.filter(ts.isStringLiteralLike).map((e) => e.text);
  }
  return [];
}

function getLeadingCommentsText(node, sourceFile) {
  const fullText = sourceFile.getFullText();
  const ranges = ts.getLeadingCommentRanges(fullText, node.getFullStart()) || [];
  return ranges.map((r) => fullText.slice(r.pos, r.end)).join('\n');
}

function parseFile(filePath, displayPath) {
  const text = fs.readFileSync(filePath, 'utf8');
  const sourceFile = ts.createSourceFile(filePath, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const records = [];

  function handleTest(node, ancestors) {
    const title = resolveStaticString(node.arguments[0]);
    if (title === null) return;

    const optionsArg = findOptionsObjectArgument(node.arguments);
    const pos = sourceFile.getLineAndCharacterOfPosition(node.getStart());

    records.push({
      title,
      ancestors: ancestors.slice(),
      file: displayPath,
      line: pos.line + 1,
      column: pos.character + 1,
      tag_option: extractTagOption(optionsArg),
      leading_comment_text: getLeadingCommentsText(node, sourceFile),
    });
  }

  function handleDescribe(node, ancestors) {
    const title = resolveStaticString(node.arguments[0]);
    const fnArg = findFunctionArgument(node.arguments);
    if (!fnArg || !fnArg.body) return;
    visit(fnArg.body, title ? ancestors.concat([title]) : ancestors);
  }

  function visit(node, ancestors) {
    if (ts.isCallExpression(node)) {
      const memberPath = getMemberPath(node.expression);
      if (memberPath && memberPath[0] === 'test') {
        if (memberPath.length === 1) {
          handleTest(node, ancestors);
        } else if (memberPath[1] === 'describe') {
          handleDescribe(node, ancestors);
          return; // already recursed into the body above with updated ancestors
        } else if (memberPath.length === 2 && TEST_LEVEL_MODIFIERS.has(memberPath[1])) {
          handleTest(node, ancestors);
        }
      }
    }
    ts.forEachChild(node, (child) => visit(child, ancestors));
  }

  visit(sourceFile, []);
  return records;
}

function main() {
  const args = process.argv.slice(2);
  if (args.length === 0 || args.length % 2 !== 0) {
    console.error('Usage: node parse_specs.js <actualPath1> <displayPath1> [<actualPath2> <displayPath2> ...]');
    process.exit(1);
  }

  const allRecords = [];
  for (let i = 0; i < args.length; i += 2) {
    allRecords.push(...parseFile(args[i], args[i + 1]));
  }

  process.stdout.write(JSON.stringify(allRecords, null, 2));
}

main();
