import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { filterDocuments, inProgress } from '../src/documentSearch.js';

const techPacks = [
  { id: 't1', filename: 'Spring Jacket.pdf', status: 'needs_review', style_number: 'S-100', tech_pack_number: '16404', created_at: '2026-10-08T09:00:00Z' },
  { id: 't2', filename: 'Cargo Pants.pdf', status: 'processing', style_number: null, tech_pack_number: null },
];
const orders = [
  { id: 'p1', filename: '362928-362960.pdf', status: 'needs_review', contract_count: 33, contract_numbers: ['362928', '362929'], tech_pack_references: ['16404', '19447'] },
  { id: 'p2', filename: 'second.pdf', status: 'failed', contract_count: 0, contract_numbers: [], tech_pack_references: [] },
];

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

test('sidebar shows both tabs and lists extracted documents with their identifiers', async () => {
  const server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom',
  });
  try {
    const { default: Sidebar } = await server.ssrLoadModule('/src/Sidebar.jsx');
    const html = renderToStaticMarkup(React.createElement(Sidebar, {
      tab: 'po', techPacks, purchaseOrders: orders, selected: { po: 'p1' }, onSelect() {}, onUpload() {}, onTabChange() {} }));
    assert.match(html, /aria-selected="true"[^>]*id="tab-po"|id="tab-po"[^>]*aria-selected="true"/);
    assert.match(html, /362928-362960\.pdf/);
    assert.match(html, /33 contracts/);
    assert.match(html, /aria-current="true"/);
    // Inactive tab stays mounted (keeps its own search/file) but hidden.
    assert.match(html, /id="panel-techpack"[^>]*hidden/);
    assert.doesNotMatch(html, /id="panel-po"[^>]*hidden/);
    assert.match(html, /Spring Jacket\.pdf/);
    assert.match(html, /Style S-100/);
  } finally {
    await server.close();
  }
});

test('sidebar shows an empty state per tab and disables extract until a file is chosen', async () => {
  const server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom',
  });
  try {
    const { default: Sidebar } = await server.ssrLoadModule('/src/Sidebar.jsx');
    const html = renderToStaticMarkup(React.createElement(Sidebar, { tab: 'techpack', onSelect() {}, onUpload() {}, onTabChange() {} }));
    assert.match(html, /No Tech Packs yet/);
    assert.match(html, /No purchase orders yet/);
    assert.match(html, /<button[^>]*disabled=""[^>]*>.*?Extract Wovens/);
    assert.match(html, /<button[^>]*disabled=""[^>]*>.*?Extract PO/);
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
    const { default: Sidebar } = await server.ssrLoadModule('/src/Sidebar.jsx');
    const html = renderToStaticMarkup(React.createElement(Sidebar, {
      tab: 'techpack', techPacks, purchaseOrders: orders, onSelect() {}, onUpload() {}, onTabChange() {}, onDelete() {} }));
    assert.match(html, /aria-label="Delete Spring Jacket\.pdf"/);
    assert.match(html, /aria-label="Delete 362928-362960\.pdf"/);
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

test('Marker Plan tab searches both document types and groups the results', async () => {
  const server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom',
  });
  try {
    const { default: Sidebar } = await server.ssrLoadModule('/src/Sidebar.jsx');
    const props = { techPacks, purchaseOrders: orders, selected: { techpack: null, po: 'p1' }, onSelect() {}, onUpload() {}, onTabChange() {}, onDelete() {} };
    const html = renderToStaticMarkup(React.createElement(Sidebar, { ...props, tab: 'plan' }));
    assert.match(html, /id="tab-plan"[^>]*aria-selected="true"|aria-selected="true"[^>]*id="tab-plan"/);
    assert.match(html, /role="tab"[^>]*>Marker Plan</);
    const plan = html.slice(html.indexOf('id="panel-plan"'));
    assert.doesNotMatch(plan.slice(0, plan.indexOf('>')), /hidden/);
    assert.match(plan, /Search Tech Packs and purchase orders/);
    assert.match(plan, /aria-label="Tech Packs"/); assert.match(plan, /aria-label="Purchase Orders"/);
    assert.match(plan, /Spring Jacket\.pdf/); assert.match(plan, /362928-362960\.pdf/);
    assert.match(plan, /aria-current="true"/);
    // The plan tab has no upload control; upload stays on the type tabs.
    assert.doesNotMatch(plan, /type="file"/);
    // When another tab is active, the Marker Plan panel stays mounted but hidden.
    const other = renderToStaticMarkup(React.createElement(Sidebar, { ...props, tab: 'techpack' }));
    assert.match(other, /id="panel-plan"[^>]*hidden/);
  } finally {
    await server.close();
  }
});