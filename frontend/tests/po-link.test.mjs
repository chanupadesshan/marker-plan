import test from 'node:test';
import assert from 'node:assert/strict';
import { checkLabel, designIds, enrichStyles, groupOrders, isApproved, linkedOrders, lockedReason, planOrders, styleSteps, techPackIds } from '../src/po-link.js';

const orders = [
  { id: 'p1', tech_pack_id: 'b', status: 'approved', id_check: 'match', contract_numbers: ['111', '222'] },
  { id: 'p2', tech_pack_id: 'b', status: 'needs_review', id_check: 'no_design', contract_numbers: ['333'] },
  { id: 'p3', tech_pack_id: 'b', status: 'needs_review', id_check: 'mismatch' },
  { id: 'p4', tech_pack_id: 'gone', status: 'approved' }, { id: 'p5', tech_pack_id: 'b', status: 'processing' },
];

test('only an approved Tech Pack takes a purchase order', () => {
  assert.equal(isApproved({ status: 'approved' }), true);
  for (const status of ['queued', 'processing', 'needs_review', 'failed']) assert.equal(isApproved({ status }), false, status);
});

test('a style groups its purchase orders', () => {
  assert.deepEqual(linkedOrders(orders, 'b').map(order => order.id), ['p1', 'p2', 'p3', 'p5']);
  const [style] = enrichStyles([{ id: 'b' }], orders);
  assert.deepEqual([style.po_count, style.approved_po_count, style.contract_numbers], [4, 1, ['111', '222', '333']]);
});

test('stages unlock in order: PO after the Tech Pack is approved, marker plan after a PO is approved too', () => {
  const state = (pack, list) => styleSteps(pack, list).map(step => `${step.key}:${step.state}`);
  assert.deepEqual(state({ status: 'processing' }, []), ['techpack:current', 'po:locked', 'plan:locked']);
  assert.deepEqual(state({ status: 'needs_review' }, []), ['techpack:current', 'po:locked', 'plan:locked']);
  assert.deepEqual(state({ status: 'approved' }, []), ['techpack:complete', 'po:current', 'plan:locked']);
  assert.deepEqual(state({ status: 'approved' }, [{ status: 'needs_review' }]), ['techpack:complete', 'po:current', 'plan:locked']);
  assert.deepEqual(state({ status: 'needs_review' }, [{ status: 'approved' }]), ['techpack:current', 'po:locked', 'plan:locked']);
  assert.deepEqual(state({ status: 'approved' }, [{ status: 'approved' }]), ['techpack:complete', 'po:complete', 'plan:current']);
  assert.match(lockedReason('po', { status: 'needs_review' }), /Approve the Tech Pack extraction first/);
  assert.match(lockedReason('plan', { status: 'approved' }), /Approve at least one matching purchase order/);
});

test('a marker plan offers only approved purchase orders that do not contradict the Tech Pack', () => {
  const list = [{ id: 'a', status: 'approved', id_check: 'match' }, { id: 'b', status: 'approved', id_check: 'no_design' },
    { id: 'c', status: 'approved', id_check: 'mismatch' }, { id: 'd', status: 'needs_review', id_check: 'match' }, { id: 'e', status: 'approved' }];
  assert.deepEqual(planOrders(list).map(order => order.id), ['a', 'b', 'e']);
  assert.deepEqual(planOrders(undefined), []);
  // The marker plan stage opens only when such a purchase order exists.
  assert.equal(styleSteps({ status: 'approved' }, [list[2], list[3]])[2].state, 'locked');
  assert.equal(styleSteps({ status: 'approved' }, [list[1]])[2].state, 'current');
});

test('purchase orders are listed under headings by how their IDs compare, empty headings left out', () => {
  const groups = groupOrders(linkedOrders(orders, 'b'));
  assert.deepEqual(groups.map(group => [group.key, group.items.map(order => order.id)]),
    [['match', ['p1']], ['no_design', ['p2']], ['mismatch', ['p3']], ['unchecked', ['p5']]]);
  assert.match(groups[1].title, /no Quality ID/);
  assert.deepEqual(groupOrders([]), []);
  assert.deepEqual(groupOrders([{ id: 'x', id_check: 'match' }]).map(group => group.key), ['match']);
  assert.equal(checkLabel('no_design'), 'No Quality ID on PO');
  assert.equal(checkLabel('unchecked'), '');
});

test('names the style and every Quality ID when known', () => {
  assert.deepEqual(designIds({ design_numbers: ['1845', '1146'] }), ['1845', '1146']);
  assert.deepEqual(designIds({ design_number: '1845' }), ['1845']);
  assert.deepEqual(designIds({}), []);
  assert.equal(techPackIds({ style_number: '1459', design_numbers: ['1845', '1146', '1142'] }), 'Style 1459 · Quality IDs 1845, 1146, 1142');
  assert.equal(techPackIds({ style_number: '1459' }), 'Style 1459');
  assert.equal(techPackIds({}), '');
});
