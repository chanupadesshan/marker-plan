import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { ADMIN_PATH, can, isAdminPath } from '../src/permissions.js';

/** Purpose: Load a module through Vite, run the callback with it, then stop the server. Input: file - '/src/X.jsx'; run - async (module) => void. Output: a promise. */
async function withModule(file, run) {
  const server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, watch: null }, appType: 'custom',
  });
  try { await run(await server.ssrLoadModule(file)); } finally { await server.close(); }
}

test('the sign-in page has only email and password and no register form', async () => {
  await withModule('/src/AuthPage.jsx', ({ default: AuthPage }) => {
    const html = renderToStaticMarkup(React.createElement(AuthPage, { onSignedIn() {} }));
    assert.match(html, /<h1>Welcome back<\/h1>/);
    assert.match(html, /Email/);
    assert.match(html, />Sign in</);
    assert.match(html, /autoComplete="current-password"|autocomplete="current-password"/);
    assert.match(html, /Ask an administrator/);
    assert.doesNotMatch(html, /Create (an )?account|Full name|Confirm password/);
  });
});

test('sign-in validation asks for a valid email and a password', async () => {
  await withModule('/src/AuthPage.jsx', ({ validateAuthForm }) => {
    assert.deepEqual(Object.keys(validateAuthForm({ email: '', password: '' })).sort(), ['email', 'password']);
    assert.deepEqual(validateAuthForm({ email: ' a@b.co ', password: 'x' }), {});
  });
});

test('can() follows the view/edit levels and admins can do everything', () => {
  const user = { is_admin: false, permissions: { plies: 'view', usage: 'edit' } };
  assert.equal(can(user, 'plies'), true);
  assert.equal(can(user, 'plies', 'edit'), false);
  assert.equal(can(user, 'usage', 'view'), true);
  assert.equal(can(user, 'usage', 'edit'), true);
  assert.equal(can(user, 'techpacks'), false);
  assert.equal(can({ is_admin: true, permissions: {} }, 'techpacks', 'edit'), true);
  assert.equal(can(null, 'plies'), false);
});

test('the Users page lives at /admin/users', () => {
  assert.equal(ADMIN_PATH, '/admin/users');
  assert.equal(isAdminPath('/admin/users'), true);
  assert.equal(isAdminPath('/admin/users/'), true);
  assert.equal(isAdminPath('/'), false);
});

test('the Users page renders its heading and an Add user button', async () => {
  await withModule('/src/UsersAdmin.jsx', ({ default: UsersAdmin }) => {
    const html = renderToStaticMarkup(React.createElement(UsersAdmin, { user: { id: '1', full_name: 'Root', email: 'r@x.co', is_admin: true, permissions: {} } }));
    assert.match(html, /Users and permissions/);
    assert.match(html, /Add user/);
  });
});
