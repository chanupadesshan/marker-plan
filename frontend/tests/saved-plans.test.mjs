import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const job = { id: 'saved-plan', status: 'complete', saved: true, created_at: '2026-10-27T03:00:00Z',
  sizes: ['S'], quantities: [10], total_quantity: 10, order_labels: ['361061'], warnings: [],
  settings: { time_limit_seconds: 20 }, summary: { complete: true, marker_count: 1, lay_count: 1, failed: 0 }, materials: [] };

test('saved results offer an authenticated Excel download only for complete validated plans', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try {
    const { MarkerPlanResults } = await server.ssrLoadModule('/src/MarkerCuttingPlan.jsx');
    const render = value => renderToStaticMarkup(React.createElement(MarkerPlanResults, { job: value }));
    const html = render(job);
    assert.match(html, /Download Excel/);
    assert.match(html, /\/api\/marker-plans\/saved-plan\/excel/);
    assert.match(html, /Saved to database/);
    assert.doesNotMatch(render({ ...job, status: 'running' }), /Download Excel/);
    assert.doesNotMatch(render({ ...job, summary: { complete: false, failed: 1 } }), /Download Excel/);
    const failedSave = render({ ...job, saved: false, persistence_error: 'Unable to save result' });
    assert.match(failedSave, /Unable to save result/);
    assert.doesNotMatch(failedSave, /Download Excel|Saved to database/);
  } finally { await server.close(); }
});

test('Marker Plan exposes saved history before materials or POs are selected', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try {
    const { default: App } = await server.ssrLoadModule('/src/SavedMarkerPlans.jsx');
    const html = renderToStaticMarkup(React.createElement(App));
    assert.match(html, /Saved plans/);
    assert.match(html, /Refresh saved plans/);
    assert.match(html, /Loading saved plans/);
  } finally { await server.close(); }
});

test('plan results use neutral text and collapsed details while failed plans stay explicit', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try {
    const { MarkerPlanResults } = await server.ssrLoadModule('/src/MarkerCuttingPlan.jsx');
    const base = { number: 1, marker_prefix: 'B01-', material_code: 'R1514', consumption: '1.65',
      unit: 'm', max_plies: 70, capacity: 4, state: 'done' };
    const result = { status: 'FEASIBLE', validated: true, marker_count: 4, lay_count: 4,
      marker_lower_bound: 3, elapsed_seconds: 0.7, markers: [], lays: [], production: [] };
    const render = (status, extra = {}) => renderToStaticMarkup(React.createElement(MarkerPlanResults, {
      job: { ...job, ...extra, materials: [{ ...base, result: { ...result, status,
        validated: ['FEASIBLE', 'OPTIMAL'].includes(status), message: status === 'ERROR' ? 'Solver unavailable' : '' } }] },
    }));
    for (const status of ['FEASIBLE', 'OPTIMAL', 'ERROR']) {
      const html = render(status);
      assert.doesNotMatch(html, /class="[^"]*(?:alert (?:error|success)|plan-outcome|status (?:approved|failed|needs_review))/);
      assert.match(html, /<details class="plan-details">/);
      assert.doesNotMatch(html, /<details class="plan-details"[^>]*open/);
    }
    const failed = render('ERROR', { summary: { complete: false, failed: 1 } });
    assert.match(failed, /Solver unavailable/);
    assert.match(failed, /1 of 1 materials have no plan/);
    assert.doesNotMatch(failed, /Download Excel/);
    const unsaved = render('FEASIBLE', { saved: false, persistence_error: 'Result could not be saved' });
    assert.match(unsaved, /Result could not be saved/);
    assert.doesNotMatch(unsaved, /class="alert error"/);
  } finally { await server.close(); }
});
