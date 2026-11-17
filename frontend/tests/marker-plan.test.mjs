import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { DEFAULT_PLAN_SETTINGS, buildPlanRequest, capacityPreview, defaultMaterialSettings, planFormErrors, planOutcome,
  selectedPlanOrders, isPlanRunning, hasPlan, plyChoices, plySourceText, solveTimeText } from '../src/marker-plan.js';

test('very fast solve times read as under 0.1 s instead of 0.0 s', () => {
  assert.equal(solveTimeText(0), 'under 0.1 s');
  assert.equal(solveTimeText(0.003), 'under 0.1 s');
  assert.equal(solveTimeText(0.099), 'under 0.1 s');
  assert.equal(solveTimeText(0.1), '0.1 s');
  assert.equal(solveTimeText(2.14), '2.1 s');
});

test('capacity preview is exact floor(table length / consumption) in metres', () => {
  assert.equal(capacityPreview('8', '0.15', 'm'), 53);
  assert.equal(capacityPreview('8', '1.65', 'm'), 4);
  assert.equal(capacityPreview('0.3', '0.1', 'm'), 3); // floating point would give 2
  assert.equal(capacityPreview('8', '165', 'cm'), 4);
  assert.equal(capacityPreview('8', '1500', 'mm'), 5);
  assert.equal(capacityPreview('8', '0.6', 'yd'), 14);
  assert.equal(capacityPreview('8,5', '0,5', 'm'), 17);
  assert.equal(capacityPreview('1', '2', 'm'), 0);
  for (const [length, consumption] of [['', '1'], ['8', ''], ['8', '0'], ['0', '1'], ['8', 'abc'], ['-8', '1']]) {
    assert.equal(capacityPreview(length, consumption, 'm'), null);
  }
  assert.equal(capacityPreview('8', '1', 'kg'), null);
});

const plies = (...values) => ({ max_ply: null, matches: values.map((col_d, id) => ({ id, col_c: 'X', col_d })) });

test('plies-table ranges and several related rows become a list of allowed values', () => {
  assert.deepEqual(plyChoices(plies('80')), [80]);
  assert.deepEqual(plyChoices(plies('70-75')), [70, 71, 72, 73, 74, 75]);
  assert.deepEqual(plyChoices(plies('75 - 70')), [70, 71, 72, 73, 74, 75]);
  assert.deepEqual(plyChoices(plies('50-60', '80', '60')), [50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 80]);
  assert.deepEqual(plyChoices(plies('130', '80')), [80, 130]);
  assert.deepEqual(plyChoices(plies('1-2000')), [1, 2000]);
  assert.deepEqual(plyChoices(plies(null, '75.5')), []);
  assert.deepEqual(plyChoices(undefined), []);
  assert.equal(plySourceText(plies('50-60', null, '80')), '50-60, 80');
});

test('material defaults come from the BOM length and the plies table', () => {
  const plyInfo = { R1371: plies('80'), R2: plies('75.5'), R1860: plies('80-90'), R2020: plies('130', '80') };
  assert.deepEqual(defaultMaterialSettings({ material_code: 'R1371', quantity: '0,95', unit: 'm' }, plyInfo),
    { consumption: '0.95', unit: 'm', max_plies: '80' });
  // A range or several values is never guessed: the user must choose.
  assert.equal(defaultMaterialSettings({ material_code: 'R1860', quantity: '1', unit: 'm' }, plyInfo).max_plies, '');
  assert.equal(defaultMaterialSettings({ material_code: 'R2020', quantity: '1', unit: 'm' }, plyInfo).max_plies, '');
  assert.deepEqual(defaultMaterialSettings({ material_code: 'R9', quantity: '95', unit: 'CM' }, plyInfo),
    { consumption: '95', unit: 'cm', max_plies: '' });
  // A non-length BOM unit is never silently converted into a consumption.
  assert.deepEqual(defaultMaterialSettings({ material_code: 'R2', quantity: '2', unit: 'pcs' }, plyInfo),
    { consumption: '', unit: 'm', max_plies: '' });
});

test('form errors block impossible settings before the request is sent', () => {
  const settings = { table_length_m: '8', min_plies: '10', time_limit_seconds: '60' };
  const ok = { key: 'a', settings: { consumption: '2', unit: 'm', max_plies: '100' } };
  assert.equal(planFormErrors(settings, [ok]).count, 0);
  const errors = planFormErrors({ table_length_m: '', min_plies: '0', time_limit_seconds: '500' }, [
    { key: 'b', settings: { consumption: '', unit: 'm', max_plies: 'x' } }]);
  assert.deepEqual(Object.keys(errors.form).sort(), ['min_plies', 'table_length_m', 'time_limit_seconds']);
  // The search time per material is 60 to 300 seconds, and starts at 60.
  const timeError = value => planFormErrors({ table_length_m: '8', min_plies: '10', time_limit_seconds: value }, []).form.time_limit_seconds;
  assert.equal(DEFAULT_PLAN_SETTINGS.time_limit_seconds, '60');
  assert.equal(timeError('59'), 'Enter 60 to 300 seconds.');
  assert.equal(timeError('20'), 'Enter 60 to 300 seconds.');
  assert.equal(timeError('301'), 'Enter 60 to 300 seconds.');
  assert.equal(timeError('60'), undefined);
  assert.equal(timeError('300'), undefined);
  assert.deepEqual(Object.keys(errors.materials.b).sort(), ['consumption', 'max_plies']);
  const tooLong = planFormErrors(settings, [{ key: 'c', settings: { consumption: '9', unit: 'm', max_plies: '5' } }]);
  assert.match(tooLong.materials.c.consumption, /capacity is below 1/);
  assert.match(tooLong.materials.c.max_plies, /minimum of 10/);
  const range = { key: 'd', plyChoices: [70, 71, 72], settings: { consumption: '2', unit: 'm', max_plies: '' } };
  // An unchosen range blocks the plan but is not shown as an error.
  const waiting = planFormErrors(settings, [range]);
  assert.deepEqual(waiting.pendingChoices, ['d']);
  assert.equal(waiting.materials.d, undefined);
  assert.equal(waiting.count, 1);
  assert.equal(planFormErrors(settings, [{ ...range, settings: { ...range.settings, max_plies: '72' } }]).count, 0);
});

test('request maps printed PO rows and each material into solver inputs', () => {
  const orders = [{ contract_number: '358449', size_rows: [{ size: 'C48', quantity: '84' }, { size: 'C50', quantity: 42 }, { size: 'C52', quantity: null }] }];
  const materials = [{ row: { material_code: 'R1310', description: 'Shell', placement: 'Body', quantity: '2.09', unit: 'm' }, pageNumber: 37,
    settings: { consumption: '2,09', unit: 'm', max_plies: ' 70 ' } }];
  assert.deepEqual(buildPlanRequest(orders, materials, { table_length_m: '8', min_plies: '10', time_limit_seconds: '60' }), {
    orders: [{ label: '358449', size_rows: [{ size: 'C48', quantity: '84' }, { size: 'C50', quantity: '42' }, { size: 'C52', quantity: null }] }],
    materials: [{ material_code: 'R1310', description: 'Shell', placement: 'Body', page_number: 37, consumption: '2.09', unit: 'm', max_plies: 70 }],
    table_length_m: '8', min_plies: 10, time_limit_seconds: 60,
  });
});

test('selected orders come from the confirmed selection, or from older ids', () => {
  const po = { contract_number: '1', size_rows: [] };
  assert.deepEqual(selectedPlanOrders({ ids: ['x'], orders: [po] }), [po]);
  assert.deepEqual(selectedPlanOrders({ ids: [JSON.stringify(['doc', 0, po]), 'not json'] }), [po]);
  assert.deepEqual(selectedPlanOrders(undefined), []);
});

test('saved plan requests preserve order, fabric colour and source metadata', () => {
  const orders = [{ contract_number: '361061', model_id: '1478', quality_id: '1514', color_id: '8933',
    tech_pack_reference: '24409', filename: 'orders.pdf', size_rows: [{ size: '-C48', quantity: '84' }] }];
  const materials = [{ row: { material_code: 'R1514', composition: 'Cotton', placement_type: 'Shell',
    colorways: [{ code: '8933', name: 'Navy/HV yellow', material_color_code: '8904', material_color_name: 'Navy' }] },
    pageNumber: 1, settings: { consumption: '1.65', unit: 'm', max_plies: '70' } }];
  const result = buildPlanRequest(orders, materials, { table_length_m: '8', min_plies: '10', time_limit_seconds: '60' },
    { id: 'source-id', filename: 'boms.pdf', style_number: '1478', tech_pack_number: '24409' });
  assert.equal(result.tech_pack_id, 'source-id');
  assert.equal(result.tech_pack_filename, 'boms.pdf');
  assert.equal(result.orders[0].model_id, '1478');
  assert.equal(result.orders[0].source_filename, 'orders.pdf');
  assert.equal(result.materials[0].placement_type, 'Shell');
  assert.equal(result.materials[0].colorways[0].material_color_code, '8904');
});

test('outcomes separate marker proof from lay proof and never call a limited search optimal', () => {
  const optimal = planOutcome({ status: 'OPTIMAL', marker_count: 2, lay_count: 5, lay_minimum_proven: false }, 20);
  assert.equal(optimal.tone, 'approved');
  assert.match(optimal.lines[0], /2 unique markers is the proven minimum/);
  assert.match(optimal.lines[1], /not proven/);
  assert.match(planOutcome({ status: 'OPTIMAL', marker_count: 1, lay_count: 2, lay_minimum_proven: true }, 20).lines[1], /also the proven minimum/);
  const feasible = planOutcome({ status: 'FEASIBLE', marker_count: 4, lay_count: 9, marker_lower_bound: 2 }, 20);
  assert.equal(feasible.tone, 'needs_review');
  assert.doesNotMatch(feasible.lines.join(' '), /is the proven minimum/);
  assert.match(feasible.lines.join(' '), /fewer markers may be possible/);
  assert.match(feasible.lines.join(' '), /At least 2 markers/);
  assert.match(planOutcome({ status: 'UNKNOWN', marker_count: 0, lay_count: 0 }, 20).lines[0], /within 20 seconds.*does not prove/);
  assert.equal(planOutcome({ status: 'INFEASIBLE', marker_count: 0, lay_count: 0 }, 20).tone, 'failed');
  assert.match(planOutcome({ status: 'MODEL_TOO_LARGE', marker_count: 0, lay_count: 0 }, 20).label, /Too large/);
  assert.equal(planOutcome({ status: 'INVALID_INPUT', marker_count: 0, lay_count: 0, message: 'Bad' }, 20).lines[0], 'Bad');
  assert.ok(!hasPlan({ status: 'OPTIMAL', validated: false }));
  assert.ok(hasPlan({ status: 'FEASIBLE', validated: true }));
  assert.ok(isPlanRunning({ status: 'running' }) && !isPlanRunning({ status: 'complete' }) && !isPlanRunning(null));
});

const extraction = { page_tables: [{ page_number: 37, materials: [{ material_code: 'R1845', description: 'Main', placement: 'Body', quantity: '2', unit: 'm' }] }] };

async function withComponent(run) {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom' });
  try {
    const { markerMaterialRows } = await server.ssrLoadModule('/src/marker-materials.js');
    const { default: Plan } = await server.ssrLoadModule('/src/MarkerCuttingPlan.jsx');
    await run(Plan, markerMaterialRows(extraction).map(entry => entry.key));
  } finally { await server.close(); }
}

test('settings form shows each material with its capacity and waits for a table length', async () => {
  await withComponent(async (Plan, keys) => {
    const orders = [{ contract_number: '1', size_rows: [{ size: 'S', quantity: '400' }] }];
    const plyInfo = { R1845: plies('120') };
    const empty = renderToStaticMarkup(React.createElement(Plan, { extraction, plyInfo, materialKeys: keys, orders, onChange() {} }));
    assert.match(empty, /Cutting settings/);
    assert.match(empty, /R1845/);
    assert.match(empty, /Plies table: 120/);
    assert.match(empty, /aria-label="Maximum plies for R1845"[^>]*value="120"/);
    assert.doesNotMatch(empty, /Choose maximum plies/);
    // A range in the plies table becomes a required choice instead of a prefilled number.
    const rangeSettings = { table_length_m: '8', min_plies: '10', time_limit_seconds: '60', materials: {} };
    const range = renderToStaticMarkup(React.createElement(Plan, { extraction, plyInfo: { R1845: plies('70-75', '80') }, materialKeys: keys, orders,
      value: { settings: rangeSettings }, onChange() {} }));
    assert.match(range, /<select aria-label="Choose maximum plies for R1845"/);
    assert.match(range, /<option value="" selected="">Choose…<\/option>/);
    assert.equal((range.match(/<option value="(7\d|80)"/g) || []).length, 7);
    assert.match(range, /Other value…/);
    assert.match(range, /Range: 70-75, 80/);
    assert.doesNotMatch(range, /field-error/);
    assert.doesNotMatch(range, /<select[^>]*aria-invalid="true"/);
    assert.match(range, /Choose the maximum plies for 1 material with a plies range/);
    assert.match(range, /disabled=""[^>]*>.*?Generate cutting plan/s);
    const chosen = renderToStaticMarkup(React.createElement(Plan, { extraction, plyInfo: { R1845: plies('70-75', '80') }, materialKeys: keys, orders,
      value: { settings: { ...rangeSettings, materials: { [keys[0]]: { consumption: '2', unit: 'm', max_plies: '72' } } } }, onChange() {} }));
    assert.match(chosen, /<option value="72" selected="">72<\/option>/);
    assert.match(chosen, /Range: 70-75, 80/);
    assert.doesNotMatch(chosen, /disabled=""[^>]*>.*?Generate cutting plan/s);
    const custom = renderToStaticMarkup(React.createElement(Plan, { extraction, plyInfo: { R1845: plies('70-75') }, materialKeys: keys, orders,
      value: { settings: { ...rangeSettings, materials: { [keys[0]]: { consumption: '2', unit: 'm', max_plies: '68', custom_max_plies: true } } } }, onChange() {} }));
    assert.match(custom, /aria-label="Maximum plies for R1845"[^>]*value="68"/);
    assert.match(custom, /Choose from the plies table/);
    assert.match(empty, /Enter the usable table length/);
    assert.match(empty, /disabled=""[^>]*>.*?Generate cutting plan/s);
    assert.doesNotMatch(empty, /fabric savings|efficiency/i);
    const ready = renderToStaticMarkup(React.createElement(Plan, { extraction, plyInfo, materialKeys: keys, orders,
      value: { settings: { table_length_m: '8', min_plies: '10', time_limit_seconds: '60', materials: {} } }, onChange() {} }));
    assert.match(ready, /<strong>4<\/strong>/);
    assert.doesNotMatch(ready, /disabled=""[^>]*>.*?Generate cutting plan/s);
  });
});

test('results show unique markers, their lays, and required versus produced quantities', async () => {
  const result = { status: 'OPTIMAL', message: 'Minimum unique marker count proven.', marker_count: 2, lay_count: 3, secondary_optimal: false,
    marker_lower_bound: 2, elapsed_seconds: 1.2, validated: true, marker_minimum_proven: true, lay_minimum_proven: false,
    markers: [{ id: 'B01-M01', counts: [1, 2, 1], sets_per_marker: 4, lay_numbers: [1, 2], lay_count: 2, total_plies: 200, sets_cut: 800 },
      { id: 'B01-M02', counts: [0, 0, 4], sets_per_marker: 4, lay_numbers: [3], lay_count: 1, total_plies: 25, sets_cut: 100 }],
    lays: [{ number: 1, marker_id: 'B01-M01', counts: [1, 2, 1], plies: 100, sets: 400 },
      { number: 2, marker_id: 'B01-M01', counts: [1, 2, 1], plies: 100, sets: 400 },
      { number: 3, marker_id: 'B01-M02', counts: [0, 0, 4], plies: 25, sets: 100 }],
    production: [{ size: 'S', required: 200, produced: 200, difference: 0 }, { size: 'M', required: 400, produced: 400, difference: 0 },
      { size: 'L', required: 300, produced: 300, difference: 0 }], progress: [] };
  const job = { id: 'j', status: 'complete', sizes: ['S', 'M', 'L'], total_quantity: 900, warnings: ['Contract 1 lists size S in 2 rows; their quantities were added together.'],
    settings: { time_limit_seconds: 20 }, summary: { complete: true, marker_count: 2, lay_count: 3, failed: 0 },
    materials: [{ number: 1, marker_prefix: 'B01-', material_code: 'R1845', page_number: 37, consumption: '2', unit: 'm', consumption_m: '2',
      max_plies: 100, capacity: 4, state: 'done', live: null, result }] };
  await withComponent(async (Plan, keys) => {
    const html = renderToStaticMarkup(React.createElement(Plan, { extraction, materialKeys: keys, orders: [], value: { job }, onChange() {} }));
    assert.match(html, /Markers and lays/);
    assert.match(html, /Minimum markers proven/);
    assert.match(html, /lay count \(3 lays\) is not proven/);
    assert.equal((html.match(/<strong>B01-M01<\/strong>/g) || []).length, 3); // marker row + two lays
    assert.match(html, /Lay 1: 100/);
    assert.match(html, /Lay 3: 25/);
    assert.match(html, /Required/);
    assert.match(html, /Produced/);
    assert.equal((html.match(/>Exact</g) || []).length, 3);
    assert.match(html, /independent validator/);
    assert.match(html, /quantities were added together/);
    assert.match(html, /2 unique markers and 3 lays in total/);
    assert.match(html, /Solved in 1\.2 s/);
    assert.doesNotMatch(html, /without a search/);
    // The one-marker shortcut is explained and its near-zero time is not shown as 0.0 s.
    const quick = { ...result, marker_count: 1, lay_count: 2, one_marker_shortcut: true, lay_minimum_proven: true, elapsed_seconds: 0.002,
      markers: [result.markers[0]], lays: result.lays.slice(0, 2) };
    const shortcut = renderToStaticMarkup(React.createElement(Plan, { extraction, materialKeys: keys, orders: [],
      value: { job: { ...job, materials: [{ ...job.materials[0], result: quick }] } }, onChange() {} }));
    assert.match(shortcut, /Solved in under 0\.1 s/);
    assert.doesNotMatch(shortcut, /0\.0 s/);
    assert.match(shortcut, /Worked out directly, without a search/);
  });
});

test('timeouts, infeasible orders and running materials are explained without a plan', async () => {
  const failed = (status, message) => ({ status, message, marker_count: 0, lay_count: 0, secondary_optimal: false, marker_lower_bound: null,
    elapsed_seconds: 20, validated: false, marker_minimum_proven: false, lay_minimum_proven: false, markers: [], lays: [], production: [], progress: [] });
  const base = { number: 1, marker_prefix: 'B01-', material_code: 'R1', consumption: '2', unit: 'm', consumption_m: '2', max_plies: 100, capacity: 4 };
  const job = { id: 'j', status: 'complete', sizes: ['S'], total_quantity: 10, warnings: [], settings: { time_limit_seconds: 20 },
    summary: { complete: false, marker_count: null, lay_count: null, failed: 2 },
    materials: [{ ...base, state: 'done', result: failed('UNKNOWN', 'No plan found within the time budget. Try a larger budget.') },
      { ...base, number: 2, marker_prefix: 'B02-', state: 'done', result: failed('INFEASIBLE', 'No plan satisfies all cutting rules.') }] };
  await withComponent(async (Plan, keys) => {
    const html = renderToStaticMarkup(React.createElement(Plan, { extraction, materialKeys: keys, orders: [], value: { job }, onChange() {} }));
    assert.match(html, /Search time ran out/);
    assert.match(html, /does not prove that no plan exists/);
    assert.match(html, /No plan possible/);
    assert.match(html, /2 of 2 materials have no plan/);
    assert.doesNotMatch(html, /Unique markers/);
    const running = { ...job, status: 'running', summary: null, materials: [{ ...base, state: 'running', result: null,
      live: { phase: 'markers', elapsed_seconds: 3.4, marker_count: 3, lay_count: 7 } }] };
    const live = renderToStaticMarkup(React.createElement(Plan, { extraction, materialKeys: keys, orders: [], value: { job: running }, onChange() {} }));
    assert.match(live, /Searching for fewer markers/);
    assert.match(live, /best so far 3 markers, 7 lays/);
    assert.match(live, /Solving material 1 of 1/);
    assert.match(live, /disabled=""[^>]*>.*?Generating…/s);
  });
});
