import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const order = { contract_number: '362928', model_id: '1805', quality_id: '2513', size_rows: [], source_pages: [1], warnings: [] };
const current = (extra = {}) => ({ id: 'p1', filename: 'po.pdf', status: 'needs_review', page_count: 3, approval_ready: true, id_check: 'match',
  extraction: { orders: [order], warnings: ['Page 2 skipped (Model ID 1817): it does not match this Tech Pack.', 'Check colour'] },
  skipped_pages: [{ page: 2, model_id: '1817', quality_id: '1534', contract_number: '362929' }, { page: 3, model_id: '1875', quality_id: null, contract_number: null }], ...extra });

test('skipped pages are listed with the IDs read and can be extracted too', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try {
    const { default: Workspace } = await server.ssrLoadModule('/src/PurchaseOrderWorkspace.jsx');
    const html = renderToStaticMarkup(React.createElement(Workspace, { current: current(), canEdit: true, onExtractSkipped() {} }));
    assert.match(html, /2 of 3 pages were skipped: not for this Tech Pack/);
    assert.match(html, /Page 2 · contract 362929 — Model ID 1817, Quality ID 1534/);
    assert.match(html, /Page 3 — Model ID 1875/);
    assert.match(html, />Extract the skipped pages too</);
    // The skipped-page notes are not repeated in the general notes.
    assert.match(html, /1 notes to review/);
    // No button while it is being read, or for a viewer; nothing at all when no page was skipped.
    assert.doesNotMatch(renderToStaticMarkup(React.createElement(Workspace, { current: current(), canEdit: false })), /Extract the skipped pages too/);
    const running = renderToStaticMarkup(React.createElement(Workspace, { current: current({ status: 'processing' }), canEdit: true }));
    assert.doesNotMatch(running, /pages were skipped/);
    assert.doesNotMatch(renderToStaticMarkup(React.createElement(Workspace, { current: current({ skipped_pages: [] }), canEdit: true })), /skipped/);
  } finally { await server.close(); }
});
