import assert from 'node:assert/strict';
import { test } from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';
import { changePoMode, togglePlanPo, matchingPlanOrders, allPlanOrders, searchPlanOrders } from '../src/marker-po.js';

test('search finds each PO by its own Tech Pack ID across documents without a BOM or mandatory model restriction', () => {
  const orders = allPlanOrders([
    { id: 'pdf1', extraction: { orders: [
      { contract_number: 'A', tech_pack_reference: '16404', model_id: '1805' },
      { contract_number: 'B', tech_pack_reference: '31717', model_id: '1555' },
    ] } },
    { id: 'pdf2', extraction: { orders: [{ contract_number: 'C', tech_pack_reference: 'TP 16404', model_id: '1806' }] } },
  ]);
  assert.deepEqual(searchPlanOrders(orders, '16404').map(po => po.contract_number), ['A', 'C']);
  assert.deepEqual(searchPlanOrders(orders, 'TP 16404', '1806').map(po => po.contract_number), ['C']);
  assert.equal(searchPlanOrders(orders).length, 3);
  assert.equal(searchPlanOrders(orders, '999').length, 0);
  assert.equal(new Set(orders.map(po => po.id)).size, 3);
});

test('individual POs within one PDF are matched by Tech Pack ID and remain separately selectable', () => {
  const documents = [{ id: 'pdf-1', filename: 'Orders.pdf', extraction: { orders: [
    { contract_number: '100', tech_pack_reference: 'TP10', color_id: 'Blue' },
    { contract_number: '101', tech_pack_reference: 'TP10', color_id: 'Red' },
    { contract_number: '102', tech_pack_reference: 'TP20' },
  ] } }];
  const matches = matchingPlanOrders(documents, ' tp10 ');
  assert.deepEqual(matches.map(po => po.contract_number), ['100', '101']);
  assert.equal(new Set(matches.map(po => po.id)).size, 2);
  assert.deepEqual(togglePlanPo([matches[0].id], matches[1].id, true, 'single'), [matches[1].id]);
  assert.equal(togglePlanPo([matches[0].id], matches[1].id, true, 'multiple').length, 2);
  assert.deepEqual(matchingPlanOrders(documents, ''), []);
  assert.deepEqual(matchingPlanOrders(documents, 'TP1'), []);
});

test('single PO replaces the previous choice; multiple POs can be added and removed', () => {
  assert.deepEqual(togglePlanPo(['a'], 'b', true, 'single'), ['b']);
  assert.deepEqual(togglePlanPo(['a'], 'b', true, 'multiple'), ['a', 'b']);
  assert.deepEqual(togglePlanPo(['a', 'b'], 'a', false, 'multiple'), ['b']);
  assert.deepEqual(togglePlanPo(['a'], 'a', true, 'multiple'), ['a']);
  assert.deepEqual(changePoMode(['a', 'b'], 'single'), ['a']);
  assert.deepEqual(changePoMode(['a', 'b'], 'multiple'), ['a', 'b']);
});

test('PO matching normalizes Tech Pack prefixes and filters Model IDs exactly', () => {
  const documents = [{ id: 'pdf', extraction: { orders: [
    { tech_pack_reference: '31717', model_id: '1555', contract_number: 'A' },
    { tech_pack_reference: 'TP 31717', model_id: '1805', contract_number: 'B' },
    { tech_pack_reference: '16404', model_id: '1555', contract_number: 'C' },
  ] } }];
  assert.deepEqual(matchingPlanOrders(documents, 'TP 31717', '1555').map(po => po.contract_number), ['A']);
  assert.equal(matchingPlanOrders(documents, '31717').length, 2);
  assert.deepEqual(matchingPlanOrders(documents, '31717', '155'), []);
});

test('PO selector asks for mode first and displays saved choices with edit action', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom' });
  try {
    const { default: Selector, PoSizeCells } = await server.ssrLoadModule('/src/MarkerPoSelection.jsx');
    const sizes = renderToStaticMarkup(React.createElement(PoSizeCells, { order: { size_rows: [
      { size: 'C52', quantity: '32' }, { size: 'C52', quantity: 0 }, { size: 'C54', quantity: null },
    ] } }));
    assert.equal((sizes.match(/C52/g) || []).length, 2);
    assert.match(sizes, /C54/);
    assert.match(sizes, />32</);
    assert.match(sizes, />0</);
    assert.match(sizes, /—/);
    assert.doesNotMatch(sizes, /Source document/);
    const purchaseOrders = [{ id: 'a', filename: 'First.pdf' }, { id: 'b', filename: 'Second.pdf' }];
    const initial = renderToStaticMarkup(React.createElement(Selector, { purchaseOrders }));
    assert.match(initial, /Individual PO or multiple POs/);
    assert.match(initial, /Individual PO/);
    assert.match(initial, /Multiple POs/);
    assert.doesNotMatch(initial, /Select First.pdf/);
    const saved = renderToStaticMarkup(React.createElement(Selector, { purchaseOrders,
      value: { mode: 'multiple', ids: ['b'] } }));
    assert.match(saved, /Edit selection/);
    assert.match(saved, /Loading individual purchase orders/);
    assert.doesNotMatch(saved, /First.pdf/);
    assert.match(saved, /approved purchase orders submitted for this Tech Pack/);
    assert.doesNotMatch(saved, /Tech Pack ID is required/);
  } finally { await server.close(); }
});
