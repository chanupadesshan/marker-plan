import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

test('the initial screen renders the upload and review workspace', async () => {
  const server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null },
    appType: 'custom',
  });
  try {
    const { default: App } = await server.ssrLoadModule('/src/App.jsx');
    const html = renderToStaticMarkup(React.createElement(App));
    assert.match(html, /Upload Tech Pack/);
    assert.match(html, /Wovens data review/);
    assert.match(html, /Upload PO/);
    assert.match(html, /Choose purchase order PDF/);
  } finally {
    await server.close();
  }
});

test('Wovens tables keep one material row and separate colorway columns per page', async () => {
  const server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom',
  });
  try {
    const { default: WovensTable } = await server.ssrLoadModule('/src/WovensTable.jsx');
    const row = { material_code: 'R1371', description: 'Cotton', placement: 'Main fabric', quantity: '0.95 m', unit: 'm',
      colorways: [{ code: '8833', name: 'Navy/HV yellow', material_color_code: '8800', material_color_name: 'Navy' },
        { code: '8853', name: 'Navy/HV orange', material_color_code: '8800', material_color_name: 'Navy' }] };
    const html = renderToStaticMarkup(React.createElement(WovensTable, { extraction: {
      page_tables: [{ page_number: 37, materials: [row] },
        { page_number: 43, materials: [{ ...row, colorways: [{ code: '9955', name: 'Black/HV Red', material_color_code: '9900' }] }] }],
    } }));
    assert.equal((html.match(/<table/g) || []).length, 2);
    assert.equal((html.match(/<tbody><tr>/g) || []).length, 2);
    assert.match(html, /8833/);
    assert.match(html, /8853/);
    assert.match(html, /9955/);
    assert.doesNotMatch(html, /0\.95 m m/);
    assert.doesNotMatch(html, /<th[^>]*>PDF pages|<th[^>]*>Fabric reference/);
  } finally { await server.close(); }
});

test('token usage distinguishes truncation and unavailable counts', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom' });
  try {
    const { default: TokenUsage } = await server.ssrLoadModule('/src/TokenUsage.jsx');
    const html = renderToStaticMarkup(React.createElement(TokenUsage, { entries: [{
      page: 37, stage: 'extraction', attempt: 1, input_tokens: 1200, output_tokens: 6500,
      total_tokens: 7700, output_limit: 6500, finish_reason: 'length', status: 'token_limit',
    }, { page: 43, status: 'request_error' }] }));
    assert.match(html, /Token usage/);
    assert.match(html, /Token limit reached/);
    assert.match(html, /Unavailable/);
    const old = renderToStaticMarkup(React.createElement(TokenUsage, { entries: [] }));
    assert.match(old, /not recorded/);
  } finally { await server.close(); }
});

test('review workspace prioritizes BOM and keeps technical details closed', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom' });
  try {
    const { default: DocumentWorkspace } = await server.ssrLoadModule('/src/DocumentWorkspace.jsx');
    const current = { id: 'test', filename: 'Tech Pack.pdf', status: 'needs_review', selected_pages: [7],
      extraction: { materials: [{ material_code: 'R1', quantity: '1', unit: 'm' }], warnings: [] } };
    const html = renderToStaticMarkup(React.createElement(DocumentWorkspace, { current }));
    assert.match(html, /Tech Pack.pdf/);
    assert.match(html, /Approve BOM/);
    assert.ok(html.indexOf('wovens-table') < html.indexOf('Token usage'));
    assert.match(html, /<details class="technical-details">/);
    assert.doesNotMatch(html, /<details[^>]*open/);
    const failed = renderToStaticMarkup(React.createElement(DocumentWorkspace, { current: {
      ...current, status: 'failed', error: 'No material rows', extraction: { materials: [], warnings: [] },
    } }));
    assert.match(failed, /No material rows to review/);
    assert.doesNotMatch(failed, /class="wovens-table"/);
    assert.match(failed, /disabled=""[^>]*>.*?Approve BOM/s);
  } finally { await server.close(); }
});
