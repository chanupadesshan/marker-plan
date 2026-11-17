import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

test('PO review shows only requested fields with source page links', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom' });
  try {
    const { default: Workspace } = await server.ssrLoadModule('/src/PurchaseOrderWorkspace.jsx');
    const current = { id: 'po-id', filename: 'Order.pdf', status: 'needs_review', page_count: 2, approval_ready: true,
      extraction: { processing_complete: true, orders: [{ contract_number: 'TEST-01', tech_pack_reference: 'TP-1',
        source_pages: [1], warnings: ['Check signature'], size_rows: [{ size: '-C52', quantity: '32', source_page: 1 }] },
        { contract_number: 'TEST-02', size_rows: [], source_pages: [2] }] } };
    const html = renderToStaticMarkup(React.createElement(Workspace, { current, canEdit: true }));
    assert.match(html, /TEST-01/); assert.match(html, /TEST-02/); assert.match(html, /-C52/);
    assert.match(html, /pdf#page=1/); assert.match(html, /Check signature/);
    assert.match(html, /Tech Pack ID/); assert.match(html, /Model ID/);
    assert.match(html, /Quality ID/); assert.match(html, /Color ID/);
    assert.doesNotMatch(html, /Unit price|Currency|Registered|Shipping|Modified by|Signed by|Printed total amount/);
    assert.match(html, /Approve PO/); assert.doesNotMatch(html, /<details[^>]*open/);
    // Approve is offered at the top and again after the contracts.
    assert.equal((html.match(/>Approve PO</g) || []).length, 2);
    assert.ok(html.lastIndexOf('>Approve PO<') > html.lastIndexOf('TEST-02'));
    const failed = renderToStaticMarkup(React.createElement(Workspace, { canEdit: true, current: {
      ...current, status: 'failed', approval_ready: false, error: 'Page 2 failed' } }));
    assert.match(failed, /TEST-01/); assert.match(failed, /Page 2 failed/);
    assert.match(failed, /Retry failed pages/);
    assert.match(failed, /disabled=""[^>]*>Approve PO/);
    assert.equal((failed.match(/disabled=""[^>]*>Approve PO/g) || []).length, 2);
  } finally { await server.close(); }
});
