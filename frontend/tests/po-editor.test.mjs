import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createPoDraft, poPayload, validatePoDraft, poSizeTotal } from '../src/po-editor.js';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';

const order = { contract_number: '355800', tech_pack_reference: '16926', model_id: '1449', quality_id: '1845', color_id: '8699',
  total_quantity: '1,410', source_pages: [2], warnings: ['Check colour'],
  size_rows: [30,90,210,240,330,270,150,30,30,30].map((quantity, index) => ({ size: `C${44 + index * 2}`, quantity: String(quantity), source_page: 2 })) };

test('PO draft preserves repeated size rows, source evidence and printed values while submitting orders only', () => {
  const source = { orders: [order, { ...order, contract_number: 'Other' }], page_results: [{ page_number: 2 }], request_usage: [{ tokens: 12 }] };
  const draft = createPoDraft(source);
  draft.orders[0].size_rows[0].size = 'C46';
  draft.orders[0].model_id = 'Changed';
  const payload = poPayload(draft);
  assert.deepEqual(Object.keys(payload), ['orders']);
  assert.equal(source.orders[0].model_id, '1449');
  assert.equal(payload.orders[0].total_quantity, '1,410');
  assert.equal(payload.orders[0].size_rows.filter(row => row.size === 'C46').length, 2);
  assert.equal(payload.orders[0].size_rows[0].source_page, 2);
  assert.deepEqual(payload.orders[0].source_pages, [2]);
  assert.deepEqual(payload.orders[0].warnings, ['Check colour']);
  assert.equal(payload.orders[1].model_id, '1449');
});

test('PO review gates editing by permission and processing state and uses simple fields instead of JSON', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try {
    const { default: Workspace } = await server.ssrLoadModule('/src/PurchaseOrderWorkspace.jsx');
    const current = { id: 'po', filename: 'PO.pdf', status: 'needs_review', approval_ready: true, extraction: { orders: [order] } };
    const render = props => renderToStaticMarkup(React.createElement(Workspace, { current, ...props }));
    assert.match(render({ canEdit: true }), />Edit PO</);
    assert.doesNotMatch(render({ canEdit: false }), />Edit PO</);
    assert.doesNotMatch(render({ canEdit: true }), /Edit PO JSON|po-json/);
    for (const status of ['queued', 'processing', 'failed']) {
      assert.doesNotMatch(render({ canEdit: true, current: { ...current, status } }), />Edit PO</);
    }
    const { default: Editor } = await server.ssrLoadModule('/src/PurchaseOrderEditor.jsx');
    const html = renderToStaticMarkup(React.createElement(Editor, { extraction: current.extraction }));
    for (const text of ['Contract number', 'Tech Pack ID', 'Quality ID', 'Colour ID', 'Size quantity sum:', '1410', 'Save changes', 'Cancel', 'Add size row', 'Add contract']) assert.ok(html.includes(text), text);
    assert.match(html, /value="1,410"/);
  } finally { await server.close(); }
});
test('contract 355800 size sum matches grouped printed totals without altering the original total', () => {
  assert.equal(poSizeTotal(order), '1410');
  for (const total_quantity of ['1,410', '1.410', '1 410', '1\u00a0410', '1410', '1410.00']) {
    assert.deepEqual(validatePoDraft({ orders: [{ ...order, total_quantity }] }), {}, total_quantity);
  }
  assert.ok(validatePoDraft({ orders: [{ ...order, total_quantity: '1400' }] })['0.total_quantity']);
});
test('PO validation flags missing contract/size, fractional or negative quantities, empty contracts and malformed totals', () => {
  assert.ok(validatePoDraft({ orders: [] }).orders);
  assert.ok(validatePoDraft({ orders: [{ ...order, contract_number: '', size_rows: [] }] })['0.contract_number']);
  assert.ok(validatePoDraft({ orders: [{ ...order, size_rows: [] }] })['0.size_rows']);
  for (const quantity of ['', '-1', '1.5', 'text']) {
    const errors = validatePoDraft({ orders: [{ ...order, size_rows: [{ size: '', quantity }] }] });
    assert.ok(errors['0.0.size']); assert.ok(errors['0.0.quantity']);
  }
  assert.ok(validatePoDraft({ orders: [{ ...order, total_quantity: '1,410.00' }] })['0.total_quantity']);
  assert.equal(poSizeTotal({ size_rows: [{ quantity: '0' }, { quantity: '30.0' }, { quantity: '1 000' }] }), '1030');
  assert.equal(poSizeTotal({ size_rows: [{ quantity: 'unknown' }] }), null);
});
