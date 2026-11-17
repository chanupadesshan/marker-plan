import assert from 'node:assert/strict';
import { test } from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';
import { markerMaterialRows, materialCategory } from '../src/marker-materials.js';

const colorways = [{ code: '9900', name: 'Black', material_color_code: '9900', material_color_name: 'Black' }];
const wovens = { category: 'wovens', material_code: 'R1845', quantity: '0.89', unit: 'm', placement: 'Main Fabric', colorways };
const knits = { category: 'knits', material_code: 'R1980', quantity: '0.02', unit: 'm', placement: 'Inside Phone Pocket', colorways };
const extraction = { style_number: '1449', materials: [wovens, knits],
  page_tables: [{ page_number: 3, materials: [wovens, knits], colorway_headers: [{ code: '9900', name: 'Black' }] }], warnings: [] };
const current = extraction => ({ id: 'tp', filename: 'Tech Pack.pdf', status: 'needs_review', selected_pages: [3], extraction });

async function render(run) {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try { return await run(server); } finally { await server.close(); }
}

test('rows without a category (saved before Knits were read) are Wovens', () => {
  assert.equal(materialCategory({ material_code: 'R1' }), 'wovens');
  assert.equal(materialCategory({ category: 'knits' }), 'knits');
  assert.equal(materialCategory(undefined), 'wovens');
});

test('Marker Plan offers Wovens and Knits rows, each with its category and the same keys as before', () => {
  const rows = markerMaterialRows(extraction);
  assert.deepEqual(rows.map(entry => [entry.row.material_code, entry.category]), [['R1845', 'wovens'], ['R1980', 'knits']]);
  const wovensOnly = markerMaterialRows({ page_tables: [{ page_number: 3, materials: [wovens], colorway_headers: [] }] });
  assert.equal(wovensOnly.length, 1);
  assert.equal(wovensOnly[0].key, rows[0].key);
});

test('the review screen shows a Wovens card and a Knits card, each with its own rows', async () => {
  await render(async server => {
    const { default: Workspace } = await server.ssrLoadModule('/src/DocumentWorkspace.jsx');
    const html = renderToStaticMarkup(React.createElement(Workspace, { current: current(extraction) }));
    assert.match(html, /<h2>Wovens BOM<\/h2>/);
    assert.match(html, /<h2>Knits BOM<\/h2>/);
    assert.match(html, /aria-label="Wovens table page 3"/);
    assert.match(html, /aria-label="Knits table page 3"/);
    const knitsStart = html.indexOf('<h2>Knits BOM</h2>');
    assert.ok(html.indexOf('R1845') < knitsStart && html.indexOf('R1980') > knitsStart, 'each row sits under its own heading');
    assert.equal(html.match(/R1980/g).length, 1);
  });
});

test('a Tech Pack with only Wovens looks as it did before', async () => {
  await render(async server => {
    const { default: Workspace } = await server.ssrLoadModule('/src/DocumentWorkspace.jsx');
    const { category, ...legacy } = wovens;
    const old = { materials: [legacy], page_tables: [{ page_number: 3, materials: [legacy], colorway_headers: [] }], warnings: [] };
    const html = renderToStaticMarkup(React.createElement(Workspace, { current: current(old) }));
    assert.match(html, /<h2>Wovens BOM<\/h2>/);
    assert.doesNotMatch(html, /Knits BOM|Knits table/);
  });
});

test('a Tech Pack with only Knits shows just the Knits card', async () => {
  await render(async server => {
    const { default: Workspace } = await server.ssrLoadModule('/src/DocumentWorkspace.jsx');
    const only = { materials: [knits], page_tables: [{ page_number: 3, materials: [knits], colorway_headers: [] }], warnings: [] };
    const html = renderToStaticMarkup(React.createElement(Workspace, { current: current(only) }));
    assert.match(html, /<h2>Knits BOM<\/h2>/);
    assert.doesNotMatch(html, /<h2>Wovens BOM<\/h2>/);
  });
});

test('in Marker Plan both the Wovens and the Knits rows are shown and selectable, each under its own table', async () => {
  await render(async server => {
    const { default: Workspace } = await server.ssrLoadModule('/src/DocumentWorkspace.jsx');
    const html = renderToStaticMarkup(React.createElement(Workspace, { current: current(extraction), markerSelection: { selectedKeys: [], onChange() {} } }));
    assert.match(html, /<h2>Wovens and Knits BOM<\/h2>/);
    assert.match(html, /R1845/);
    assert.match(html, /R1980/);
    assert.match(html, /aria-label="Wovens table page 3"/);
    assert.match(html, /aria-label="Knits table page 3"/);
    assert.ok(html.indexOf('R1845') < html.indexOf('aria-label="Knits table page 3"') && html.indexOf('R1980') > html.indexOf('aria-label="Knits table page 3"'));
    assert.equal((html.match(/type="checkbox"/g) || []).length, 2);
  });
});

test('the editor lets each row be set to Wovens or Knits', async () => {
  await render(async server => {
    const { default: Editor } = await server.ssrLoadModule('/src/BomEditor.jsx');
    const html = renderToStaticMarkup(React.createElement(Editor, { extraction, busy: false, onSave() {}, onCancel() {} }));
    assert.match(html, /<th>Section<\/th>/);
    assert.equal((html.match(/<option value="knits"/g) || []).length, 2);
    assert.match(html, /<option value="knits" selected="">Knits<\/option>/);
    assert.match(html, /<option value="wovens" selected="">Wovens<\/option>/);
  });
});
