import assert from 'node:assert/strict';
import { test } from 'node:test';
import { projectKeyFromContext, resolveProjectKey } from './projectContext.js';

test('projectKeyFromContext reads extension.project.key', () => {
  assert.equal(projectKeyFromContext({ extension: { project: { id: '1', key: 'KAN', type: 'software' } } }), 'KAN');
  assert.equal(projectKeyFromContext({ extension: { project: { key: ' ABC ' } } }), 'ABC');
});

test('projectKeyFromContext is null when there is no project', () => {
  assert.equal(projectKeyFromContext(undefined), null);
  assert.equal(projectKeyFromContext({}), null);
  assert.equal(projectKeyFromContext({ extension: {} }), null);
  assert.equal(projectKeyFromContext({ extension: { project: { key: '  ' } } }), null);
});

test('resolveProjectKey prefers override, then detected, then fallback', () => {
  assert.equal(resolveProjectKey({ override: 'XYZ', detected: 'KAN', fallback: 'DEF' }), 'XYZ');
  assert.equal(resolveProjectKey({ override: '  ', detected: 'KAN', fallback: 'DEF' }), 'KAN');
  assert.equal(resolveProjectKey({ override: '', detected: null, fallback: 'DEF' }), 'DEF');
});
