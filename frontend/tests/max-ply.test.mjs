import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const material = code => ({ material_code: code, description: 'Cotton', placement: 'Main', quantity: '0.95', unit: 'm', colorways: [] });
const extraction = { page_tables: [{ page_number: 3, colorway_headers: [], materials: [
  material('R1371'), material('R1936'), material('R1342'), material('R9999')] }] };
const plyInfo = {
  R1371: { max_ply: 75, matches: [{ id: 3, col_c: '1371', col_d: '70-75' }] },
  R1936: { max_ply: 80, matches: [{ id: 101, col_c: '1936', col_d: '50-60' }, { id: 146, col_c: 'R1936-9800', col_d: '80' }] },
  R1342: { max_ply: null, matches: [{ id: 170, col_c: '1342', col_d: null }] },
};

async function render(props) {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom' });
  try {
    const { default: WovensTable } = await server.ssrLoadModule('/src/WovensTable.jsx');
    return renderToStaticMarkup(React.createElement(WovensTable, props));
  } finally { await server.close(); }
}

test('the Wovens table has a Max ply column after Qty with each material\'s maximum', async () => {
  const html = await render({ extraction, plyInfo });
  assert.match(html, /<th>Qty<\/th><th>Max ply<\/th>/);
  // R1371: one related row whose value is a range, so the range is shown under the maximum
  assert.match(html, /<strong>75<\/strong><small>70-75<\/small>/);
  // R1936: two related rows, the largest wins and the count is shown
  assert.match(html, /<strong>80<\/strong><small>2 entries<\/small>/);
});

test('hovering the maximum lists every related plies row', async () => {
  const html = await render({ extraction, plyInfo });
  assert.match(html, /title="From the plies table: #101 1936 → 50-60; #146 R1936-9800 → 80"/);
});

test('a material with no related row, or no value in Column D, shows a dash', async () => {
  const html = await render({ extraction, plyInfo });
  assert.match(html, /title="No related row in the plies table">—</);               // R9999
  assert.match(html, /title="From the plies table: #170 1342 → no value">—</);      // R1342
  assert.equal((html.match(/<strong>\d+<\/strong>/g) || []).length, 2);              // only 75 and 80 are numbers
});

test('the table still renders when the server sends no ply information', async () => {
  const html = await render({ extraction });
  assert.match(html, /<th>Max ply<\/th>/);
  assert.equal((html.match(/No related row in the plies table/g) || []).length, 4);
});
