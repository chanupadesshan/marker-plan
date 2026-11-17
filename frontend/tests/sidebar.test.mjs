import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { filterDocuments, inProgress, filterTechPacks, latestDocuments } from '../src/documentSearch.js';

const techPacks = [
  { id: 't1', filename: 'Spring Jacket.pdf', status: 'needs_review', style_number: 'S-100', tech_pack_number: '16404', created_at: '2026-10-08T09:00:00Z' },
  { id: 't2', filename: 'Cargo Pants.pdf', status: 'processing', style_number: null, tech_pack_number: null },
];
const orders = [
  { id: 'p1', filename: '362928-362960.pdf', status: 'needs_review', contract_count: 33, contract_numbers: ['362928', '362929'], tech_pack_references: ['16404', '19447'] },
  { id: 'p2', filename: 'second.pdf', status: 'failed', contract_count: 0, contract_numbers: [], tech_pack_references: [] },
];

test('document previews show the latest five uploads without changing the source order', () => {
  const items = [3, 1, 6, 2, 5, 4].map(day => ({ id: day, created_at: `2026-10-0${day}T09:00:00Z` }));
  const original = [...items];
  assert.deepEqual(latestDocuments(items).map(item => item.id), [6, 5, 4, 3, 2]);
  assert.deepEqual(latestDocuments(items, Infinity).map(item => item.id), [6, 5, 4, 3, 2, 1]);
  assert.deepEqual(items, original);
  assert.deepEqual(latestDocuments([{ id: 'missing' }, { id: 'invalid', created_at: 'invalid' }, ...items]).map(item => item.id), [6, 5, 4, 3, 2]);
  assert.deepEqual(latestDocuments([]), []);
});

test('search matches file names, extracted identifiers and status', () => {
  assert.deepEqual(filterDocuments(techPacks, 'jacket').map(i => i.id), ['t1']);
  assert.deepEqual(filterDocuments(techPacks, 's-100').map(i => i.id), ['t1']);
  assert.deepEqual(filterDocuments(techPacks, 'needs review').map(i => i.id), ['t1']);
  assert.deepEqual(filterDocuments(orders, '362929').map(i => i.id), ['p1']);
  assert.deepEqual(filterDocuments(orders, '19447').map(i => i.id), ['p1']);
  assert.deepEqual(filterDocuments(orders, 'FAILED').map(i => i.id), ['p2']);
});

test('every search term must match, blank search keeps the list, and no match returns nothing', () => {
  assert.deepEqual(filterDocuments(orders, 'second failed').map(i => i.id), ['p2']);
  assert.deepEqual(filterDocuments(orders, '362928 second'), []);
  assert.equal(filterDocuments(orders, '   '), orders);
  assert.equal(filterDocuments(orders, ''), orders);
  assert.deepEqual(filterDocuments(orders, 'zzz'), []);
});

test('in-progress detection drives sidebar status polling', () => {
  assert.equal(inProgress(techPacks), true);
  assert.equal(inProgress(orders), false);
  assert.equal(inProgress([{ status: 'queued' }]), true);
  assert.equal(inProgress([]), false);
});

test('the Tech Pack library lists the styles with their identifiers and PO counts', async () => {
  const server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom',
  });
  try {
    const { ArchiveList } = await server.ssrLoadModule('/src/Sidebar.jsx');
    const styles = [{ ...techPacks[0], design_number: '1845', po_count: 2 }, techPacks[1]];
    const html = renderToStaticMarkup(React.createElement(ArchiveList, {
      kind: 'techpack', items: styles, selectedId: 't1', onSelect() {}, onDelete() {} }));
    assert.match(html, /document-topbar/);
    assert.doesNotMatch(html, /<aside/);
    assert.doesNotMatch(html, /role="tab"/);
    assert.match(html, /Spring Jacket\.pdf/);
    assert.match(html, /Style S-100 · Quality ID 1845 · 2 POs/);
    assert.match(html, /aria-current="true"/);
    assert.doesNotMatch(html, /Purchase orders without a Tech Pack/);
  } finally {
    await server.close();
  }
});

test('Create Marker Plan shows only the Tech Pack upload, with extract disabled until a file is chosen, and no card list', async () => {
  const server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom',
  });
  try {
    const { default: Sidebar } = await server.ssrLoadModule('/src/Sidebar.jsx');
    const html = renderToStaticMarkup(React.createElement(Sidebar, { onUpload() {} }));
    assert.match(html, /<button[^>]*disabled=""[^>]*>.*?Extract Wovens/);
    assert.doesNotMatch(html, /Extract PO/);
    assert.equal((html.match(/type="file"/g) || []).length, 1);
    assert.doesNotMatch(html, /document-row|type="search"|Search styles/);
    // A person who may not edit Tech Packs gets no upload.
    const readOnly = renderToStaticMarkup(React.createElement(Sidebar, { canUpload: false }));
    assert.doesNotMatch(readOnly, /type="file"/);
  } finally {
    await server.close();
  }
});

test('every list row has its own delete button, disabled while extraction is running', async () => {
  const server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom',
  });
  try {
    const { ArchiveList } = await server.ssrLoadModule('/src/Sidebar.jsx');
    const html = renderToStaticMarkup(React.createElement(ArchiveList, {
      kind: 'techpack', items: techPacks, onSelect() {}, onDelete() {} }));
    assert.match(html, /aria-label="Delete Spring Jacket\.pdf"/);
    // Cargo Pants.pdf is still processing, so it cannot be deleted yet.
    assert.match(html, /disabled=""[^>]*aria-label="Delete Cargo Pants\.pdf"|aria-label="Delete Cargo Pants\.pdf"[^>]*disabled=""/);
    assert.doesNotMatch(html, /disabled=""[^>]*aria-label="Delete Spring Jacket\.pdf"/);
    // Select and delete are sibling buttons; a button must never be nested in another button.
    assert.doesNotMatch(html, /<button[^>]*>(?:(?!<\/button>).)*<button/);
  } finally {
    await server.close();
  }
});
test('confirm dialog renders nothing when closed and an accessible dialog when open', async () => {
  const server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom',
  });
  try {
    const { default: ConfirmDialog } = await server.ssrLoadModule('/src/ConfirmDialog.jsx');
    assert.equal(renderToStaticMarkup(React.createElement(ConfirmDialog, { open: false, title: 'x' })), '');
    const danger = renderToStaticMarkup(React.createElement(ConfirmDialog, { open: true, tone: 'danger', title: 'Delete this purchase order?',
      message: 'This cannot be undone.', detail: 'Order.pdf', confirmLabel: 'Delete', onConfirm() {}, onCancel() {} }));
    assert.match(danger, /role="alertdialog"/); assert.match(danger, /aria-modal="true"/);
    assert.match(danger, /Delete this purchase order\?/); assert.match(danger, /Order\.pdf/);
    assert.match(danger, /danger-button[^>]*>Delete</); assert.match(danger, />Cancel</);
    const approve = renderToStaticMarkup(React.createElement(ConfirmDialog, { open: true, title: 'Approve?', confirmLabel: 'Approve PO' }));
    assert.match(approve, /primary-button[^>]*>Approve PO</); assert.doesNotMatch(approve, /danger-button/);
  } finally {
    await server.close();
  }
});
test('one Tech Pack number finds the Tech Pack and the POs that reference it', () => {
  assert.deepEqual(filterDocuments(techPacks, '16404').map(i => i.id), ['t1']);
  assert.deepEqual(filterDocuments(orders, '16404').map(i => i.id), ['p1']);
  assert.deepEqual(filterDocuments(techPacks, '19447'), []);
  assert.deepEqual(filterDocuments(orders, '19447').map(i => i.id), ['p1']);
});

test('printed TP number search works with or without prefix and without Style ID', () => {
 const items = [{id: 'a', tech_pack_number: 'TP 31717'}, {id: 'b', tech_pack_number: '16404', style_number: '1555'}, {id: 'c', style_number: '31717'}];
 assert.deepEqual(filterTechPacks(items, '1555'), []);
 assert.deepEqual(filterTechPacks(items, '').map(row => row.id), ['a', 'b', 'c']);
 for (const query of ['31717', 'tp 31717']) assert.deepEqual(filterTechPacks(items, query).map(row => row.id), ['a']);
 for (const query of ['TP 16404']) assert.deepEqual(filterTechPacks(items, query).map(row => row.id), ['b']);
});

test('Marker Plan includes all saved Tech Packs when TP numbers are missing', () => {
  const items = [
    { id: 'combined', filename: 'tech-pack-two-boms.pdf', status: 'approved', tech_pack_number: null },
    { id: 'missing', filename: '1459 TP 32197 updated.pdf', status: 'approved', tech_pack_number: null },
    { id: 'numbered', filename: '1555 bulk.pdf', status: 'approved', tech_pack_number: 'TP 31717' },
  ];
  assert.deepEqual(filterTechPacks(items, '').map(row => row.id), ['combined', 'missing', 'numbered']);
  assert.deepEqual(filterTechPacks(items, '32197').map(row => row.id), ['missing']);
  assert.deepEqual(filterTechPacks(items, 'two-boms').map(row => row.id), ['combined']);
  assert.deepEqual(filterTechPacks(items, 'TP 31717').map(row => row.id), ['numbered']);
  assert.deepEqual(filterTechPacks(items, 'not found'), []);
});


test('the Tech Pack and PO libraries list saved documents with search and delete but no upload', async () => {
  const server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom',
  });
  try {
    const { ArchiveList } = await server.ssrLoadModule('/src/Sidebar.jsx');
    const po = renderToStaticMarkup(React.createElement(ArchiveList, { kind: 'po', items: [{ ...orders[0], linked_to: 'Style 1449 · Quality ID 1845' }, orders[1]], selectedId: 'p1', onSelect() {}, onDelete() {} }));
    assert.match(po, /Saved purchase orders/);
    assert.match(po, /33 contracts · Style 1449 · Quality ID 1845/);
    assert.match(po, /aria-label="Delete 362928-362960\.pdf"/);
    assert.match(po, /Search purchase orders/);
    assert.doesNotMatch(po, /type="file"/);
    const tp = renderToStaticMarkup(React.createElement(ArchiveList, { kind: 'techpack', items: techPacks, onSelect() {}, onDelete() {} }));
    assert.match(tp, /Saved Tech Packs/);
    assert.match(tp, /Spring Jacket\.pdf/);
    assert.doesNotMatch(tp, /type="file"/);
    assert.match(renderToStaticMarkup(React.createElement(ArchiveList, { kind: 'po', items: [], onSelect() {} })), /Add one in Create Marker Plan/);
  } finally {
    await server.close();
  }
});