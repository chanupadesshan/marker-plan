import assert from 'node:assert/strict';
import { test } from 'node:test';
import { AUDIT_PATH, actionLabel, auditQuery, formatWhen, hasDetails, isAuditPath, planFacts, planMaterials, showValue, statusLabel, summarizeEntry } from '../src/audit.js';

test('the Activity log lives at /admin/audit', () => {
  assert.equal(AUDIT_PATH, '/admin/audit');
  assert.ok(isAuditPath('/admin/audit') && isAuditPath('/admin/audit/'));
  assert.ok(!isAuditPath('/admin/users') && !isAuditPath(undefined));
});

test('actions and statuses read in plain words', () => {
  assert.equal(actionLabel('po.edit'), 'Edited purchase order');
  assert.equal(actionLabel('techpack.approve'), 'Approved Tech Pack');
  assert.equal(actionLabel('something.new'), 'something.new');
  assert.equal(statusLabel('needs_review'), 'Needs review');
  assert.equal(statusLabel(undefined), 'Unknown');
});

test('entries are summarised for the table', () => {
  const edit = { action: 'techpack.edit', details: { changes: [{}, {}, {}], more_changes: 0, previous_status: 'approved', new_status: 'needs_review' } };
  assert.equal(summarizeEntry(edit), '3 changes (Approved → Needs review)');
  assert.equal(summarizeEntry({ action: 'po.edit', details: { changes: [{}], previous_status: 'needs_review', new_status: 'needs_review' } }), '1 change');
  assert.equal(summarizeEntry({ action: 'po.edit', details: { changes: [] } }), 'No changes to the data');
  assert.equal(summarizeEntry({ action: 'po.edit', details: { changes: new Array(200).fill({}), more_changes: 1 } }), '201+ changes');
  assert.equal(summarizeEntry({ action: 'po.approve', details: { previous_status: 'needs_review', new_status: 'approved' } }), 'Needs review → Approved');
  assert.equal(summarizeEntry({ action: 'po.approve', details: {} }), 'Approved');
});

test('marker plan entries show their inputs and result in plain words', () => {
  const details = { tech_pack_filename: 'tp.pdf', orders: ['355800', '359259'], total_quantity: 800, table_length_m: '8', min_plies: 10,
    time_limit_seconds: 5, materials: [{ material_code: 'R1845', consumption: '2', unit: 'm', max_plies: 120 }],
    summary: { complete: true, marker_count: 3, lay_count: 4, failed: 0 } };
  assert.equal(actionLabel('marker_plan.create'), 'Generated marker plan');
  assert.equal(actionLabel('marker_plan.delete'), 'Deleted marker plan');
  assert.equal(actionLabel('marker_plan.download'), 'Downloaded marker plan Excel');
  assert.equal(summarizeEntry({ action: 'marker_plan.create', target_type: 'marker_plan', details }), '1 material, 800 garments');
  assert.equal(summarizeEntry({ action: 'marker_plan.download', target_type: 'marker_plan', details: {} }), 'Marker plan');
  assert.deepEqual(planFacts(details), [['Tech Pack', 'tp.pdf'], ['Purchase orders', '355800, 359259'], ['Garments', '800'],
    ['Table length', '8 m'], ['Minimum plies', '10'], ['Time limit', '5 s per material'],
    ['Materials', 'R1845 (2 m, max 120 plies)'], ['Result', 'Complete: 3 markers, 4 lays']]);
  assert.deepEqual(planFacts({ summary: { complete: false, failed: 1 } }), [['Result', '1 material not planned']]);
  assert.deepEqual(planFacts(undefined), []);
});

test('values and times are shown safely', () => {
  assert.equal(showValue(''), '(empty)');
  assert.equal(showValue(null), '(empty)');
  assert.equal(showValue(0), '0');
  assert.equal(formatWhen(null), '—');
  assert.equal(formatWhen('not a date'), '—');
  assert.match(formatWhen('2026-11-02T10:01:00Z'), /2026/);
});

test('the log query pages and leaves out empty filters', () => {
  assert.equal(auditQuery(), 'limit=25&offset=0');
  assert.equal(auditQuery({ page: 2, action: 'po.edit', search: ' 359 ' }), 'limit=25&offset=50&action=po.edit&search=359');
});

test('marker plan materials are listed one per row, and only entries with something to show can be expanded', () => {
  const details = { materials: [{ material_code: 'R1514', consumption: 1.65, unit: 'm', max_plies: 70 }, { consumption: 0.32, unit: 'm', max_plies: 60 }] };
  assert.deepEqual(planMaterials(details), [{ code: 'R1514', consumption: '1.65 m', maxPlies: 70 }, { code: 'Material', consumption: '0.32 m', maxPlies: 60 }]);
  assert.deepEqual(planMaterials({}), []);
  assert.equal(hasDetails({ target_type: 'marker_plan', details: { tech_pack_filename: 'tp.pdf' } }), true);
  assert.equal(hasDetails({ target_type: 'marker_plan', details: {} }), false);
  assert.equal(hasDetails({ target_type: 'po', details: { changes: [{ path: 'a', before: 1, after: 2 }] } }), true);
  assert.equal(hasDetails({ target_type: 'po', details: { changes: [] } }), false);
  assert.equal(hasDetails({ target_type: 'techpack', details: { previous_status: 'needs_review', new_status: 'approved' } }), false);
});