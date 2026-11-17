import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { filterPlies, isPliesPath, pageSlice, toPayload, validatePly } from '../src/plies.js';

const rows = [
  { id: 1, col_b: 1, col_c: '1800', col_d: '90-100' },
  { id: 2, col_b: 1, col_c: 'R1330-1000', col_d: '80' },
  { id: 3, col_b: 2, col_c: '818647', col_d: null },
];

test('the Plies dashboard has its own address', () => {
  assert.equal(isPliesPath('/plies'), true);
  assert.equal(isPliesPath('/plies/'), true);
  assert.equal(isPliesPath('/'), false);
  assert.equal(isPliesPath('/plies/5'), false);
  assert.equal(isPliesPath('/other/plies'), false);
  assert.equal(isPliesPath(undefined), false);
});

test('search matches id, B, C and D, every word must match, and blank keeps all rows', () => {
  assert.deepEqual(filterPlies(rows, 'r1330').map(r => r.id), [2]);
  assert.deepEqual(filterPlies(rows, '90-100').map(r => r.id), [1]);
  assert.deepEqual(filterPlies(rows, '818647 2').map(r => r.id), [3]);
  assert.deepEqual(filterPlies(rows, '1800 818647'), []);
  assert.deepEqual(filterPlies(rows, 'zzz'), []);
  assert.equal(filterPlies(rows, '  '), rows);
  assert.equal(filterPlies(rows, ''), rows);
});

test('validation requires a whole-number B and a code in C, and keeps D optional', () => {
  assert.deepEqual(validatePly({ col_b: '1', col_c: '1800', col_d: '' }), {});
  assert.deepEqual(validatePly({ col_b: ' -2 ', col_c: ' x ', col_d: '90-100' }), {});
  assert.match(validatePly({ col_b: '', col_c: 'x' }).col_b, /required/);
  assert.match(validatePly({ col_b: '1.5', col_c: 'x' }).col_b, /whole number/);
  assert.match(validatePly({ col_b: 'one', col_c: 'x' }).col_b, /whole number/);
  assert.match(validatePly({ col_b: '1', col_c: '   ' }).col_c, /required/);
  assert.match(validatePly({ col_b: '1', col_c: 'x'.repeat(101) }).col_c, /100/);
  assert.match(validatePly({ col_b: '1', col_c: 'x', col_d: 'y'.repeat(101) }).col_d, /100/);
  assert.deepEqual(Object.keys(validatePly({ col_b: '', col_c: '' })).sort(), ['col_b', 'col_c']);
});

test('the request body has a numeric B, trimmed text and a null for a blank D', () => {
  assert.deepEqual(toPayload({ col_b: ' 2 ', col_c: ' R1330-1000 ', col_d: '  ' }), { col_b: 2, col_c: 'R1330-1000', col_d: null });
  assert.deepEqual(toPayload({ col_b: '1', col_c: '1800', col_d: ' 90-100 ' }), { col_b: 1, col_c: '1800', col_d: '90-100' });
});

test('paging cuts the list, keeps the page in range and reports the visible span', () => {
  const many = Array.from({ length: 60 }, (_, i) => ({ id: i + 1 }));
  assert.deepEqual(pageSlice(many, 1, 25), { items: many.slice(0, 25), page: 1, pages: 3, from: 1, to: 25 });
  assert.equal(pageSlice(many, 3, 25).items.length, 10);
  assert.deepEqual([pageSlice(many, 3, 25).from, pageSlice(many, 3, 25).to], [51, 60]);
  assert.equal(pageSlice(many, 99, 25).page, 3);
  assert.equal(pageSlice(many, Number.MAX_SAFE_INTEGER, 25).page, 3);
  assert.equal(pageSlice(many, 0, 25).page, 1);
  assert.deepEqual(pageSlice([], 1), { items: [], page: 1, pages: 1, from: 0, to: 0 });
});

test('the dashboard page renders its search, add button and loading state', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom' });
  try {
    const { default: PliesDashboard } = await server.ssrLoadModule('/src/PliesDashboard.jsx');
    const html = renderToStaticMarkup(React.createElement(PliesDashboard, { user: { full_name: 'Root', email: 'r@x.co', is_admin: true, permissions: {} } }));
    assert.match(html, /<h1>Plies<\/h1>/);
    assert.match(html, /aria-label="Search plies"/);
    assert.match(html, /Add ply/);
    assert.match(html, /Loading plies/);
    // The left navigation replaces the old "Back to review" link and marks Plies as the current page.
    assert.match(html, /href="\/"[^>]*>.*?Create Marker Plan/);
    assert.match(html, /<a[^>]*aria-current="page"[^>]*>.*?Plies/);
  } finally { await server.close(); }
});

test('the add and edit dialogs show the three fields with the right title and button', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom' });
  try {
    const { default: PlyFormDialog } = await server.ssrLoadModule('/src/PlyFormDialog.jsx');
    const add = renderToStaticMarkup(React.createElement(PlyFormDialog, { mode: 'add', onSave() {}, onCancel() {} }));
    assert.match(add, /role="dialog"/); assert.match(add, /Add a ply/);
    assert.match(add, /Customer/); assert.match(add, /Material/); assert.match(add, /Maximum plies/); assert.match(add, /optional/);
    assert.match(add, /Add ply<\/button>/);
    const edit = renderToStaticMarkup(React.createElement(PlyFormDialog, { mode: 'edit', initial: rows[1], onSave() {}, onCancel() {} }));
    assert.match(edit, /Edit ply #2/);
    assert.match(edit, /value="R1330-1000"/); assert.match(edit, /value="80"/);
    assert.match(edit, /Save changes/);
    const failed = renderToStaticMarkup(React.createElement(PlyFormDialog, { mode: 'add', error: 'Material is required', onSave() {}, onCancel() {} }));
    assert.match(failed, /role="alert"/); assert.match(failed, /Material is required/);
    const saving = renderToStaticMarkup(React.createElement(PlyFormDialog, { mode: 'add', busy: true, onSave() {}, onCancel() {} }));
    assert.match(saving, /Saving…/); assert.match(saving, /disabled=""/);
  } finally { await server.close(); }
});
