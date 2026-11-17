import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createBomDraft, bomPayload, validateBomDraft } from '../src/bom-editor.js';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';

const row = { material_code: 'R1514', quantity: '1.65', unit: 'm', source_pages: [1],
  colorways: [{ code: '8933', name: 'Navy', material_color_code: '8904', fabric_reference: 'ref' }] };
test('page edits preserve source and original data, omit derived materials and rebuild colorway headers', () => {
  const source = { style_number: null, warnings: ['note'], request_usage: [{ tokens: 1 }], materials: [row],
    page_tables: [{ page_number: 1, materials: [row], colorway_headers: [{ code: '8933', name: 'Navy' }] },
      { page_number: 2, materials: [{ ...row, source_pages: [2] }], colorway_headers: [] }] };
  const draft = createBomDraft(source);
  draft.page_tables[0].materials[0].colorways[0].code = '9000';
  draft.page_tables[0].materials[0].description = 'Corrected';
  const payload = bomPayload(draft, source);
  assert.equal('materials' in payload, false);
  assert.equal(source.page_tables[0].materials[0].description, undefined);
  assert.equal(payload.page_tables[1].materials[0].material_code, 'R1514');
  assert.deepEqual(payload.page_tables[0].colorway_headers, [{ code: '9000', name: 'Navy' }]);
  assert.equal(payload.page_tables[0].materials[0].colorways[0].fabric_reference, 'ref');
  assert.deepEqual(payload.warnings, ['note']);
});
test('unrelated saves preserve printed colour headings without assigned material variants', () => {
  const source = { page_tables: [{ page_number: 1, materials: [row], colorway_headers: [
    { code: '8933', name: 'Navy' }, { code: '1000', name: 'White' }] }] };
  const draft = createBomDraft(source);
  draft.style_number = '1478';
  assert.deepEqual(bomPayload(draft, source).page_tables[0].colorway_headers, source.page_tables[0].colorway_headers);
  draft.page_tables[0].materials[0].colorways[0].code = '9000';
  assert.deepEqual(bomPayload(draft, source).page_tables[0].colorway_headers, [
    { code: '9000', name: 'Navy' }, { code: '1000', name: 'White' }]);
});
test('legacy drafts keep flat materials and optional document numbers', () => {
  const draft = createBomDraft({ materials: [row], source_pages: [3], style_number: null });
  assert.equal(bomPayload(draft).materials[0].material_code, 'R1514');
  assert.deepEqual(validateBomDraft(draft), {});
});
test('validation flags empty rows, nonpositive quantities and missing units without rejecting decimal commas', () => {
  const draft = createBomDraft({ materials: [{ material_code: '', quantity: '-1', unit: '' }] });
  const errors = validateBomDraft(draft);
  assert.ok(errors['0.0.material_code']);
  assert.ok(errors['0.0.quantity']);
  assert.ok(errors['0.0.unit']);
  draft.materials = [{ ...row, quantity: '0,32' }];
  assert.deepEqual(validateBomDraft(draft), {});
  draft.materials = [];
  assert.ok(validateBomDraft(draft).materials);
});

test('review exposes Edit BOM only for permitted users and keeps technical JSON read-only', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try {
    const { default: Workspace } = await server.ssrLoadModule('/src/DocumentWorkspace.jsx');
    const current = { id: 'bom', filename: 'BOM.pdf', status: 'needs_review', extraction: { materials: [row] } };
    const render = props => renderToStaticMarkup(React.createElement(Workspace, { current, ...props }));
    assert.match(render({ canEdit: true }), />Edit BOM</);
    assert.doesNotMatch(render({ canEdit: false }), />Edit BOM</);
    assert.doesNotMatch(render({ canEdit: true }), /Edit JSON|extraction-json/);
    for (const status of ['queued', 'processing', 'failed']) {
      assert.doesNotMatch(render({ canEdit: true, current: { ...current, status } }), />Edit BOM</);
    }
    const { default: Editor } = await server.ssrLoadModule('/src/BomEditor.jsx');
    const html = renderToStaticMarkup(React.createElement(Editor, { extraction: current.extraction }));
    for (const label of ['Style number', 'Tech pack number', 'Material code', 'Composition', 'Quantity', 'Unit', 'Edit colours', 'Save changes', 'Cancel', 'Add row', 'Remove row']) assert.ok(html.includes(label), label);
    assert.match(html, /value="1.65"/);
  } finally { await server.close(); }
});
