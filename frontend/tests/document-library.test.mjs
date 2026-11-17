import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

test('the styles preview links to a separate all-styles page with Back and all cards', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try {
    const { ArchiveList: Sidebar } = await server.ssrLoadModule('/src/Sidebar.jsx');
    const { default: Library } = await server.ssrLoadModule('/src/DocumentLibrary.jsx');
    const items = Array.from({ length: 7 }, (_, index) => ({ id: `${index}`, filename: `Document-${index}.pdf`, status: 'approved', created_at: `2026-10-0${index + 1}T09:00:00Z` }));
    const preview = renderToStaticMarkup(React.createElement(Sidebar, { kind: 'techpack', items, selectedId: null }));
    assert.equal((preview.match(/class="document-row"/g) || []).length, 5);
    assert.match(preview, /href="\/\?tab=techpack&amp;view=documents"/);
    assert.doesNotMatch(preview, /<strong title="Document-0\.pdf"|Show less/);
    for (const kind of ['techpack']) {
      const html = renderToStaticMarkup(React.createElement(Library, { kind, items, onBack() {} }));
      assert.equal((html.match(/class="document-row"/g) || []).length, 7);
      assert.match(html, /Back<\/button>/);
      assert.match(html, /type="search"/);
      assert.ok(html.indexOf('Document-6.pdf') < html.indexOf('Document-0.pdf'));
    }
  } finally { await server.close(); }
});
