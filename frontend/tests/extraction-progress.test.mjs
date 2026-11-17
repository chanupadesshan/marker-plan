import { test } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';

test('Tech Pack progress shows real page counts and indeterminate upload/queue states', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try {
    const { default: Progress } = await server.ssrLoadModule('/src/TechPackProgress.jsx');
    const render = props => renderToStaticMarkup(React.createElement(Progress, props));
    const upload = render({ uploading: true });
    assert.match(upload, /Uploading Tech Pack/);
    assert.doesNotMatch(upload, /aria-valuenow/);
    const active = render({ current: { status: 'processing', progress: { stage: 'extracting', completed_pages: 2, total_pages: 4, percent: 50 } } });
    assert.match(active, /aria-valuenow="50"/);
    assert.match(active, /2 of 4 material pages read/);
    assert.doesNotMatch(render({ current: { status: 'queued' } }), /aria-valuenow/);
    assert.equal(render({ current: { status: 'failed' } }), '');
    assert.equal(render({ current: { status: 'needs_review' } }), '');
    const poUpload = render({ uploading: true, kind: 'po' });
    assert.match(poUpload, /Uploading Purchase Order/);
    assert.doesNotMatch(poUpload, /Tech Pack|BOM/);
    const po = render({ kind: 'po', current: { status: 'processing', progress: { stage: 'extracting', completed_pages: 1, total_pages: 3, percent: 33 } } });
    assert.match(po, /1 of 3 PO pages read/);
    assert.match(po, /aria-valuenow="33"/);
    assert.doesNotMatch(po, /material pages|BOM/);
  } finally { await server.close(); }
});
