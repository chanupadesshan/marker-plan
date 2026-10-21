import assert from 'node:assert/strict';
import { test } from 'node:test';
import { uploadDocuments } from '../src/uploadDocuments.js';

test('paired upload links PO to the saved Tech Pack', async () => {
  const result = await uploadDocuments({ techPack: 'tech', po: 'order' }, {
    techPack: { upload: async () => ({ id: 'tech-id' }) },
    po: { upload: async (file, id) => ({ id: 'po-id', file, tech_pack_id: id }) },
  });
  assert.equal(result.poResult.value.tech_pack_id, 'tech-id');
});

test('PO uploads independently when Tech Pack upload fails', async () => {
  const result = await uploadDocuments({ techPack: 'tech', po: 'order' }, {
    techPack: { upload: async () => { throw new Error('Storage unavailable'); } },
    po: { upload: async (file, id) => ({ id: 'po-id', tech_pack_id: id }) },
  });
  assert.match(result.techPackResult.error, /Storage unavailable/);
  assert.equal(result.poResult.value.tech_pack_id, null);
  assert.match(result.warning, /not linked/);
});

test('PO-only and Tech Pack-only upload do not require the other file', async () => {
  const clients = { techPack: { upload: async () => ({ id: 'tech' }) }, po: { upload: async () => ({ id: 'po' }) } };
  assert.equal((await uploadDocuments({ po: 'order' }, clients)).poResult.value.id, 'po');
  assert.equal((await uploadDocuments({ techPack: 'tech' }, clients)).techPackResult.value.id, 'tech');
});
