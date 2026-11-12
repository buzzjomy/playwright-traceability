import assert from 'node:assert/strict';
import { test } from 'node:test';
import { BACKEND_URL, uploadCommand } from './ciSnippet.js';

test('uploadCommand targets the backend and uses the real script flags', () => {
  const command = uploadCommand();
  assert.match(command, new RegExp(`--backend-url ${BACKEND_URL}`));
  assert.match(command, /--report /);
  assert.match(command, /--specs-dir /);
});

test('uploadCommand never embeds a key - it comes from the INGEST_API_KEY env var', () => {
  assert.doesNotMatch(uploadCommand(), /pwt_/);
  assert.doesNotMatch(uploadCommand(), /--api-key/);
  assert.match(uploadCommand(), /INGEST_API_KEY/);
});
