import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import AuthPage from './AuthPage.jsx';
import PliesDashboard from './PliesDashboard.jsx';
import UsageDashboard from './UsageDashboard.jsx';
import UsersAdmin from './UsersAdmin.jsx';
import AuditLog from './AuditLog.jsx';
import SavedMarkerPlanPage from './SavedMarkerPlanPage.jsx';
import { initialWorkspaceTab, savedPlanId } from './plan-navigation.js';
import { authApi, authToken } from './api.js';
import { isAdminPath } from './permissions.js';
import { canOpen, landingHref } from './nav.js';
import { isAuditPath } from './audit.js';
import { isPliesPath } from './plies.js';
import { isUsagePath } from './usage.js';
import './styles.css';
import './theme.css';
import './vivid.css';
import './reference-ui.css';
import './login-motion.css';
import './dropdowns.css';
import './brand-logo.css';

// The Plies, Usage, Users and Activity log pages are their own pages at /plies, /usage, /admin/users and /admin/audit; every other address shows the review screen.
const path = window.location.pathname;
const planId = savedPlanId(path);
const Page = planId ? SavedMarkerPlanPage : isPliesPath(path) ? PliesDashboard : isUsagePath(path) ? UsageDashboard : isAdminPath(path) ? UsersAdmin : isAuditPath(path) ? AuditLog : App;
// What the address asks for, in the terms canOpen() understands.
const request = planId ? { page: 'saved-plan' } : isPliesPath(path) ? { page: 'plies' } : isUsagePath(path) ? { page: 'usage' }
  : isAdminPath(path) ? { page: 'users' } : isAuditPath(path) ? { page: 'audit' } : { page: 'review', tab: initialWorkspaceTab(window.location.search) };

/**
 * Purpose: Show the sign-in page until a person is signed in, then the requested page. A saved token is checked
 * with the server first; a rejected token (now or later, on any request) returns the person to sign-in.
 * A person who may not open the requested page is sent to the first page they may use; one who may use none is told to ask an admin.
 * Input: none.
 * Output: the loading state, the sign-in page, the requested page with the signed-in user, or a short message.
 */
function Root() {
  // undefined: checking a saved token; null: signed out; object: the signed-in user.
  const [user, setUser] = useState(authToken.get() ? undefined : null);

  useEffect(() => {
    if (user !== undefined) return;
    authApi.me().then(result => setUser(result.user)).catch(() => { authToken.clear(); setUser(null); });
  }, []);
  useEffect(() => {
    const expired = () => setUser(null);
    window.addEventListener('auth-expired', expired);
    return () => window.removeEventListener('auth-expired', expired);
  }, []);

  /** Purpose: Sign out. Input: none. Output: nothing (forgets the token and returns to the main address, so the next person to sign in starts from the start and not on this person's page). */
  function signOut() {
    authToken.clear();
    window.location.assign('/');
  }

  // Someone who may not open this page goes to the first one they may (the list is built from the same rules as the menu, so it is always open to them).
  const blocked = Boolean(user) && !canOpen(user, request);
  const landing = blocked ? landingHref(user) : null;
  useEffect(() => { if (landing) window.location.replace(landing); }, [landing]);

  if (user === undefined) return <div className="auth-shell"><div className="loading-workspace" role="status"><span className="spinner"/> Checking your session…</div></div>;
  if (user === null) return <AuthPage onSignedIn={setUser} />;
  if (landing) return <div className="auth-shell"><div className="loading-workspace" role="status"><span className="spinner"/> Taking you to a page you can use…</div></div>;
  if (blocked) return <div className="auth-shell" style={{ padding: 24 }}><div className="auth-card"><h1>No access yet</h1>
    <p className="auth-lead">Your account is not allowed to use any pages yet. Ask an administrator to give you access, then sign in again.</p>
    <button className="secondary-button" onClick={signOut}>Sign out</button></div></div>;
  return <Page id={planId} user={user} onSignOut={signOut} />;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><Root /></React.StrictMode>);
