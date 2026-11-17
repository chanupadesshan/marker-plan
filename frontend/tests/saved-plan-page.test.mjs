import assert from 'node:assert/strict';
import { test } from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';
import { savedPlanPath, savedPlanId, markerPlanReturnPath, initialWorkspaceTab } from '../src/plan-navigation.js';

test('saved plans have a direct page URL and the return URL selects Marker Plan', () => {
  assert.equal(savedPlanPath('abc-123'), '/marker-plans/abc-123');
  assert.equal(savedPlanId('/marker-plans/abc-123'), 'abc-123');
  assert.equal(savedPlanId('/marker-plans/abc-123/'), 'abc-123');
  for (const path of ['/', '/marker-plans', '/marker-plans/a/b', '/marker-plans/%2f', '/marker-plans/%']) assert.equal(savedPlanId(path), null);
  assert.equal(markerPlanReturnPath, '/?tab=plan');
  assert.equal(initialWorkspaceTab('?tab=plan'), 'plan');
  assert.equal(initialWorkspaceTab('?tab=techpack'), 'techpack');
  assert.equal(initialWorkspaceTab('?tab=po'), 'po');
  assert.equal(initialWorkspaceTab(''), 'style');
  assert.equal(initialWorkspaceTab('?tab=invalid'), 'style');
});

test('history Open is a dedicated page link and the page always has a back link while loading', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try {
    const { SavedPlanActions } = await server.ssrLoadModule('/src/SavedMarkerPlans.jsx');
    const html = renderToStaticMarkup(React.createElement(SavedPlanActions, { plan: { id: 'abc-123', status: 'complete', saved: true, summary: { complete: true } } }));
    assert.match(html, /href="\/marker-plans\/abc-123"[^>]*>Open</);
    assert.match(html, /Download Excel/);
    assert.doesNotMatch(html, />Delete<|>Run again</);
    const editable = renderToStaticMarkup(React.createElement(SavedPlanActions, { canEdit: true, plan: { id: 'abc-123', status: 'complete' } }));
    assert.match(editable, /href="\/marker-plans\/abc-123\?rerun=1"/);
    assert.match(editable, />Delete</);
    const active = renderToStaticMarkup(React.createElement(SavedPlanActions, { canEdit: true, plan: { id: 'abc-123', status: 'running' } }));
    assert.match(active, /disabled="">Run again/);
    assert.match(active, /disabled="">Delete/);
    const { default: Page } = await server.ssrLoadModule('/src/SavedMarkerPlanPage.jsx');
    const page = renderToStaticMarkup(React.createElement(Page, { id: 'abc-123' }));
    assert.match(page, /Back to Marker Plan/);
    assert.match(page, /href="\/\?tab=plan"/);
    assert.match(page, /Loading saved plan/);
    assert.doesNotMatch(page, /Choose Tech Pack|Refresh saved plans/);
  } finally { await server.close(); }
});

