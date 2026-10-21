import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadSelectedDocument } from '../src/document-loading.js';

test('a late polling response cannot replace a newly selected document', async () => {
  let selectedId = 'A';
  let displayed = null;
  let resolveOld;
  const oldRequest = new Promise(resolve => { resolveOld = resolve; });
  const fetchDocument = id => id === 'A' ? oldRequest : Promise.resolve({ id: 'B' });
  const commit = row => { displayed = row; };
  const pending = loadSelectedDocument('A', () => selectedId, commit, fetchDocument);
  selectedId = 'B';
  await loadSelectedDocument('B', () => selectedId, commit, fetchDocument);
  resolveOld({ id: 'A' });
  await pending;
  assert.equal(displayed.id, 'B');
});
