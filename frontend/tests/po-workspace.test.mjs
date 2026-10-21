import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

test('PO review shows contracts, exact sizes, source pages and blank prices', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom' });
  try {
    const { default: Workspace } = await server.ssrLoadModule('/src/PurchaseOrderWorkspace.jsx');
    const current = { id: 'po-id', filename: 'Order.pdf', status: 'needs_review', page_count: 2, approval_ready: true,
      extraction: { processing_complete: true, orders: [{ contract_number: 'TEST-01', tech_pack_reference: 'TP-1',
        source_pages: [1], warnings: ['Check signature'], size_rows: [{ size: '-C52', quantity: '32', source_page: 1 }] },
        { contract_number: 'TEST-02', size_rows: [], source_pages: [2] }] } };
    const html = renderToStaticMarkup(React.createElement(Workspace, { current }));
    assert.match(html, /TEST-01/); assert.match(html, /TEST-02/); assert.match(html, /-C52/);
    assert.match(html, /pdf#page=1/); assert.match(html, /Check signature/);
    assert.match(html, /Unit price/); assert.doesNotMatch(html, /0\.00/);
    assert.match(html, /Approve PO/); assert.doesNotMatch(html, /<details[^>]*open/);
    const failed = renderToStaticMarkup(React.createElement(Workspace, { current: {
      ...current, status: 'failed', approval_ready: false, error: 'Page 2 failed' } }));
    assert.match(failed, /TEST-01/); assert.match(failed, /Page 2 failed/);
    assert.match(failed, /disabled=""[^>]*>Approve PO/);
  } finally { await server.close(); }
});
