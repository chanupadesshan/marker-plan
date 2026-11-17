import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { markerMaterialRows, updateMaterialSelection, filterMarkerMaterials, selectVisibleMaterials } from '../src/marker-materials.js';

const material = { material_code: 'R1', description: 'Cotton', quantity: '0.5', unit: 'm', colorways: [] };
const extraction = { page_tables: [
  { page_number: 3, materials: [material, { ...material }] },
  { page_number: 8, materials: [{ ...material, quantity: '0.7' }] },
] };

test('same material codes and repeated rows can be chosen independently', () => {
  const rows = markerMaterialRows(extraction);
  assert.equal(new Set(rows.map(row => row.key)).size, 3);
  const one = updateMaterialSelection(rows, [], rows[0].key, true);
  const two = updateMaterialSelection(rows, one, rows[2].key, true);
  assert.deepEqual(two, [rows[0].key, rows[2].key]);
  assert.deepEqual(updateMaterialSelection(rows, two, rows[0].key, false), [rows[2].key]);
  assert.equal(material.quantity, '0.5');
});

test('changed source rows and invalid keys cannot silently select another material', () => {
  const previous = markerMaterialRows(extraction);
  const changed = structuredClone(extraction);
  changed.page_tables[0].materials[0].material_code = 'R2';
  const rows = markerMaterialRows(changed);
  assert.notEqual(rows[0].key, previous[0].key);
  assert.deepEqual(updateMaterialSelection(rows, [previous[0].key], 'not-a-material', true), []);
});

test('older extractions without page tables still supply selectable materials', () => {
  const rows = markerMaterialRows({ materials: [material] });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].row.material_code, 'R1');
});

test('material search matches only codes, including partial codes and mixed case', () => {
  const rows = markerMaterialRows({ materials: [material, { ...material, material_code: 'R2020' }, { ...material, material_code: null }] });
  assert.deepEqual(filterMarkerMaterials(rows, ' r20 ').map(entry => entry.row.material_code), ['R2020']);
  assert.equal(filterMarkerMaterials(rows, 'Cotton').length, 0);
  assert.equal(filterMarkerMaterials(rows, 'missing').length, 0);
  assert.equal(filterMarkerMaterials(rows, ' ').length, 3);
});

test('selecting search matches retains previously selected hidden materials', () => {
  const rows = markerMaterialRows({ materials: [material, { ...material, material_code: 'R2020' }] });
  const visible = filterMarkerMaterials(rows, '2020');
  assert.deepEqual(selectVisibleMaterials(rows, [rows[0].key], visible), rows.map(entry => entry.key));
});

test('Marker Plan shows checkboxes and a selected-material summary, normal review does not', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom' });
  try {
    const { default: Workspace } = await server.ssrLoadModule('/src/DocumentWorkspace.jsx');
    const rows = markerMaterialRows(extraction);
    const current = { id: 'tech-1', filename: 'Tech Pack.pdf', status: 'needs_review', extraction,
      ply_info: { R1: { max_ply: 75, matches: [{ id: 1, col_c: 'R1', col_d: '75' }] } } };
    const plain = renderToStaticMarkup(React.createElement(Workspace, { current }));
    assert.doesNotMatch(plain, /type="checkbox"|Selected materials/);
    const html = renderToStaticMarkup(React.createElement(Workspace, { current,
      markerSelection: { selectedKeys: [rows[2].key], onChange() {} } }));
    assert.doesNotMatch(html, /type="checkbox"/);
    assert.match(html, /Edit selection/);
    assert.match(html, /Material selection confirmed/);
    assert.match(html, /Selected materials/);
    assert.match(html, /1 selected/);
    assert.match(html, /0\.7 m/);
    const summary = html.slice(html.indexOf('aria-label="Selected marker plan materials"'));
    for (const column of ['Material code / Dev No', 'Description', 'Composition', 'Placement type / Placement', 'Qty', 'Max ply']) {
      assert.ok(summary.includes(`<th>${column}</th>`), `selected table includes ${column}`);
    }
    assert.equal((summary.match(/<tbody><tr/g) || []).length, 1);
    assert.doesNotMatch(summary, /type="checkbox"/);
    const initial = renderToStaticMarkup(React.createElement(Workspace, { current,
      markerSelection: { selectedKeys: [], onChange() {} } }));
    assert.match(initial, /Select all/);
    assert.match(initial, /aria-label="Search materials by code"/);
    assert.equal((initial.match(/type="checkbox"/g) || []).length, 3);
    assert.match(initial, /<button type="button" class="primary-button" disabled="">OK<\/button>/);
    const failed = renderToStaticMarkup(React.createElement(Workspace, { current: { ...current, status: 'failed' },
      markerSelection: { selectedKeys: [], onChange() {} } }));
    assert.match(failed, /type="checkbox"[^>]*disabled=""/);
    assert.match(failed, /<button type="button" class="primary-button" disabled="">OK<\/button>/);
  } finally { await server.close(); }
});

test('filtered Wovens rows retain their original checkbox identity and selected state', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom' });
  try {
    const { default: Table } = await server.ssrLoadModule('/src/WovensTable.jsx');
    const source = { page_tables: [{ page_number: 7, materials: [material, { ...material, material_code: 'R2020' }] }] };
    const rows = markerMaterialRows(source);
    const html = renderToStaticMarkup(React.createElement(Table, { extraction: source, selection: {
      visibleKeys: new Set([rows[1].key]), selectedKeys: new Set([rows[1].key]), onToggle() {} } }));
    assert.equal((html.match(/type="checkbox"/g) || []).length, 1);
    assert.match(html, /Select R2020, page 7, row 2/);
    assert.match(html, /checked=""/);
    assert.doesNotMatch(html, />R1</);
  } finally { await server.close(); }
});
