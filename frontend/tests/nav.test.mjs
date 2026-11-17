import assert from 'node:assert/strict';
import { test } from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';
import { canOpen, landingHref, visibleNav, workspaceHref } from '../src/nav.js';

const only = (feature, level = 'view') => ({ is_admin: false, permissions: { [feature]: level } });
const PAGES = [{ page: 'review', tab: 'style' }, { page: 'review', tab: 'techpack' }, { page: 'review', tab: 'po' }, { page: 'review', tab: 'plan' },
  { page: 'saved-plan' }, { page: 'plies' }, { page: 'usage' }, { page: 'users' }, { page: 'audit' }];
const openable = user => PAGES.filter(request => canOpen(user, request)).map(request => request.page === 'review' ? `review:${request.tab}` : request.page);

test('every kind of user lands on a page they can open', () => {
  const landing = {
    admin: [{ is_admin: true, permissions: {} }, '/'],
    techpacks: [only('techpacks'), '/'],
    purchase_orders: [only('purchase_orders'), '/?tab=po'],
    marker_plan: [only('marker_plan'), '/?tab=plan'],
    plies: [only('plies'), '/plies'],
    usage: [only('usage', 'edit'), '/usage'],
    // The first allowed page in menu order wins when someone has several.
    plies_and_usage: [{ is_admin: false, permissions: { plies: 'view', usage: 'view' } }, '/plies'],
    po_and_usage: [{ is_admin: false, permissions: { usage: 'view', purchase_orders: 'edit' } }, '/?tab=po'],
  };
  for (const [name, [user, expected]] of Object.entries(landing)) assert.equal(landingHref(user), expected, name);
  // No permissions at all (or nobody signed in) means no page to send them to.
  assert.equal(landingHref({ is_admin: false, permissions: {} }), null);
  assert.equal(landingHref(null), null);
  // Permissions that do not exist are ignored, and admin-only pages are never a landing page for non-admins.
  assert.equal(landingHref({ is_admin: false, permissions: { users: 'edit', audit: 'edit', nonsense: 'edit' } }), null);
});

test('the landing page is always one the same person is allowed to open', () => {
  const people = [{ is_admin: true, permissions: {} }, only('techpacks'), only('purchase_orders'), only('marker_plan'), only('plies'), only('usage'),
    { is_admin: false, permissions: { plies: 'view', usage: 'edit', purchase_orders: 'view' } }];
  for (const user of people) {
    const href = landingHref(user);
    const url = new URL(href, 'http://x');
    const request = url.pathname === '/plies' ? { page: 'plies' } : url.pathname === '/usage' ? { page: 'usage' }
      : { page: 'review', tab: url.searchParams.get('tab') || 'style' };
    assert.ok(canOpen(user, request), `${JSON.stringify(user)} -> ${href}`);
  }
});

test('each page is closed to people without its permission', () => {
  assert.deepEqual(openable({ is_admin: true, permissions: {} }), ['review:style', 'review:techpack', 'review:po', 'review:plan', 'saved-plan', 'plies', 'usage', 'users', 'audit']);
  assert.deepEqual(openable(only('techpacks')), ['review:style', 'review:techpack']);
  assert.deepEqual(openable(only('purchase_orders')), ['review:po']);
  assert.deepEqual(openable(only('marker_plan')), ['review:plan', 'saved-plan']);
  assert.deepEqual(openable(only('plies')), ['plies']);
  assert.deepEqual(openable(only('usage')), ['usage']);
  assert.deepEqual(openable({ is_admin: false, permissions: {} }), []);
  assert.deepEqual(openable(null), []);
  // The main screen with no tab is the Tech Pack view.
  assert.equal(canOpen(only('usage'), { page: 'review' }), false);
  assert.equal(canOpen(only('techpacks'), { page: 'review' }), true);
});

const links = user => visibleNav(user).flatMap(section => section.items.map(item => item.label));

test('the navigation shows only what each person may use', () => {
  assert.deepEqual(links(null), []);
  assert.deepEqual(links({ is_admin: true, permissions: {} }),
    ['Create Marker Plan', 'Tech Packs', 'Purchase Orders', 'Marker Plans', 'Plies', 'Usage', 'Users and permissions', 'Activity log']);
  assert.deepEqual(links({ is_admin: false, permissions: { plies: 'view', usage: 'edit', techpacks: 'view' } }), ['Create Marker Plan', 'Tech Packs', 'Plies', 'Usage']);
  // Admin-only pages are never offered on a permission alone.
  assert.ok(!links({ is_admin: false, permissions: { users: 'edit', audit: 'edit' } }).includes('Activity log'));
  assert.deepEqual(visibleNav({ is_admin: false, permissions: { usage: 'view' } }).map(section => section.label), ['System management']);
});

test('links open the right address', () => {
  assert.equal(workspaceHref('style'), '/');
  assert.equal(workspaceHref('techpack'), '/?tab=techpack');
  assert.equal(workspaceHref('po'), '/?tab=po');
  assert.equal(workspaceHref('plan'), '/?tab=plan');
  const hrefs = Object.fromEntries(visibleNav({ is_admin: true, permissions: {} }).flatMap(section => section.items).map(item => [item.key, item.href]));
  assert.deepEqual(hrefs, { style: '/', techpack: '/?tab=techpack', po: '/?tab=po', plan: '/?tab=plan', plies: '/plies', usage: '/usage', users: '/admin/users', audit: '/admin/audit' });
});

test('the page frame marks the current page, shows counts and switches views without reloading', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try {
    const { default: AppShell } = await server.ssrLoadModule('/src/AppShell.jsx');
    const user = { full_name: 'Ann Admin', email: 'ann@example.com', is_admin: true, permissions: {} };
    const html = renderToStaticMarkup(React.createElement(AppShell, { user, active: 'po', title: 'Purchase Orders', counts: { techpack: 6, po: 3 }, onNavigate() {} },
      React.createElement('p', null, 'page body')));
    assert.match(html, /<h1>Purchase Orders<\/h1>/);
    assert.match(html, /page body/);
    assert.match(html, /<button[^>]*aria-current="page"[^>]*>.*?Purchase Orders/);
    assert.match(html, /vp-nav-count">6</);
    assert.match(html, /vp-nav-count">3</);
    assert.match(html, /<a[^>]*href="\/usage"/);
    assert.match(html, /<a[^>]*href="\/admin\/audit"/);
    assert.match(html, /Ann Admin/);
    assert.match(html, /Sign out/);
    // Without a switch handler (any page but the review screen) the review links are plain addresses.
    const other = renderToStaticMarkup(React.createElement(AppShell, { user, active: 'plies', title: 'Plies' }));
    assert.match(other, /<a[^>]*href="\/\?tab=po"/);
    assert.match(other, /<a[^>]*aria-current="page"[^>]*>.*?Plies/);
    assert.doesNotMatch(other, /vp-nav-count/);
  } finally { await server.close(); }
});

