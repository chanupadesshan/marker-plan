import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Check, Pencil, Plus, ShieldCheck, Trash2 } from 'lucide-react';
import { adminApi } from './api.js';
import AppShell from './AppShell.jsx';
import { useConfirm } from './useConfirm.jsx';

const LEVEL_LABELS = { none: 'No access', view: 'View only', edit: 'View and edit' };

/**
 * Purpose: Check the Add user / Edit user form before it is sent.
 * Input: mode - 'add' or 'edit'; values - { full_name, email, password }.
 * Output: an object of messages keyed by field name; empty when the form is fine. A password is required when adding
 * and, when editing, only checked if one was typed.
 */
export function validateUserForm(mode, values) {
  const errors = {};
  if (!values.full_name.trim()) errors.full_name = 'Enter a name';
  if (mode === 'add' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(values.email.trim())) errors.email = 'Enter a valid email address';
  if ((mode === 'add' || values.password) && values.password.length < 8) errors.password = 'Use at least 8 characters';
  return errors;
}

/**
 * Purpose: A summary of what a user can do, for the table.
 * Input: user - a user from the server; features - [{ key, label }].
 * Output: 'Admin (full access)', 'No access', or the granted features such as 'Plies (view), Usage (edit)'.
 */
export function describeAccess(user, features) {
  if (user.is_admin) return 'Admin (full access)';
  const granted = features.filter(feature => user.permissions?.[feature.key])
    .map(feature => `${feature.label} (${user.permissions[feature.key]})`);
  return granted.length ? granted.join(', ') : 'No access';
}

/** Purpose: Up to two capital letters for an avatar. Input: name - a full name. Output: e.g. 'AL' for 'Ada Lovelace'. */
export function initials(name) {
  const parts = (name || '?').trim().split(/\s+/);
  return ((parts[0]?.[0] || '?') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

/**
 * Purpose: Show what a user can do as small coloured badges: Admin, one per granted area (green for edit), or No access.
 * Input: props - user: a user from the server; features: [{ key, label }].
 * Output: the badges.
 */
function AccessChips({ user, features }) {
  if (user.is_admin) return <div className="access-chips"><span className="chip admin">Admin · full access</span></div>;
  const granted = features.filter(feature => user.permissions?.[feature.key]);
  if (!granted.length) return <div className="access-chips"><span className="chip none">No access</span></div>;
  return <div className="access-chips">{granted.map(feature => <span key={feature.key} className={`chip ${user.permissions[feature.key]}`}>
    {feature.label} · {user.permissions[feature.key]}</span>)}</div>;
}
/**
 * Purpose: The dialog for creating a user or editing one: name, email (new users only), password, admin and active
 * switches, and a None / View / Edit choice for every feature.
 * Input: props - mode: 'add' or 'edit'; initial: the user being edited; features: [{ key, label }]; isSelf: the user
 * being edited is the signed-in admin (their own admin/active switches are locked); busy; error: a failed-save message;
 * onSave(payload); onCancel().
 * Output: the dialog element. Mount it only while open so each opening starts fresh.
 */
function UserDialog({ mode, initial, features, isSelf, busy, error, onSave, onCancel }) {
  const [values, setValues] = useState({ full_name: initial?.full_name ?? '', email: initial?.email ?? '', password: '' });
  const [isAdmin, setIsAdmin] = useState(!!initial?.is_admin);
  const [isActive, setIsActive] = useState(initial?.is_active ?? true);
  const [levels, setLevels] = useState(() => Object.fromEntries(features.map(feature =>
    [feature.key, (!initial?.is_admin && initial?.permissions?.[feature.key]) || 'none'])));
  const [errors, setErrors] = useState({});
  const first = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    first.current?.focus();
    return () => { if (previous instanceof HTMLElement) previous.focus(); };
  }, []);

  /** Purpose: Check the form and, if valid, hand the payload to the parent to save. Input: event - the submit. Output: nothing. */
  function submit(event) {
    event.preventDefault();
    const found = validateUserForm(mode, values);
    setErrors(found);
    if (Object.keys(found).length) return;
    const permissions = isAdmin ? {} : levels;
    onSave(mode === 'add'
      ? { email: values.email.trim(), full_name: values.full_name.trim(), password: values.password, is_admin: isAdmin, permissions }
      : { full_name: values.full_name.trim(), password: values.password, is_admin: isAdmin, is_active: isActive, permissions });
  }

  /** Purpose: One text input with its message. Input: key, label, type, extra props. Output: the markup. */
  const text = (key, label, type, extra = {}) => <label className="ply-field">
    <span>{label}{extra.hint && <small> {extra.hint}</small>}</span>
    <input ref={key === 'full_name' ? first : undefined} type={type} value={values[key]} disabled={busy || extra.disabled}
      autoComplete={extra.autoComplete} aria-invalid={errors[key] ? 'true' : undefined}
      onChange={event => { setValues(previous => ({ ...previous, [key]: event.target.value })); setErrors(previous => ({ ...previous, [key]: undefined })); }}/>
    {errors[key] && <em className="field-error">{errors[key]}</em>}
  </label>;

  return <div className="dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onCancel(); }}
    onKeyDown={event => { if (event.key === 'Escape' && !busy) onCancel(); }}>
    <form className="dialog-card form user-dialog" role="dialog" aria-modal="true" aria-labelledby="user-form-title" onSubmit={submit} noValidate>
      <h2 id="user-form-title">{mode === 'edit' ? `Edit ${initial.full_name}` : 'Add user'}</h2>
      {text('full_name', 'Full name', 'text', { autoComplete: 'off' })}
      {text('email', 'Email', 'email', { disabled: mode === 'edit', autoComplete: 'off' })}
      {text('password', mode === 'edit' ? 'New password' : 'Password', 'password',
        { autoComplete: 'new-password', hint: mode === 'edit' ? '(leave blank to keep the current one)' : '(at least 8 characters)' })}
      <label className="check-field"><input type="checkbox" checked={isAdmin} disabled={busy || isSelf} onChange={event => setIsAdmin(event.target.checked)}/>
        <span><strong>Admin</strong> — full access, and can manage users</span></label>
      {mode === 'edit' && <label className="check-field"><input type="checkbox" checked={isActive} disabled={busy || isSelf} onChange={event => setIsActive(event.target.checked)}/>
        <span><strong>Active</strong> — untick to stop this person signing in</span></label>}
      <fieldset className="permission-grid" disabled={busy || isAdmin}>
        <legend>Access{isAdmin && ' (admins can use everything)'}</legend>
        {features.map(feature => <label key={feature.key}><span>{feature.label}</span>
          <select value={isAdmin ? 'edit' : levels[feature.key]} onChange={event => setLevels(previous => ({ ...previous, [feature.key]: event.target.value }))}>
            {Object.entries(LEVEL_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>)}
      </fieldset>
      {error && <div className="alert error" role="alert"><span>{error}</span></div>}
      <div className="dialog-actions">
        <button type="button" className="secondary-button" disabled={busy} onClick={onCancel}>Cancel</button>
        <button type="submit" className="primary-button" disabled={busy}>{busy ? 'Saving…' : mode === 'edit' ? 'Save changes' : 'Add user'}</button>
      </div>
    </form>
  </div>;
}

/**
 * Purpose: The Users page (admins only): see everyone, add a user, change a person's role and per-feature access,
 * reset a password, disable an account, or delete it. Changes save to the database straight away.
 * Input: user - the signed-in admin; onSignOut - called by the Sign out button.
 * Output: the page.
 */
export default function UsersAdmin({ user, onSignOut }) {
  const [users, setUsers] = useState([]);
  const [features, setFeatures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [form, setForm] = useState(null);        // null, or { mode: 'add' | 'edit', row }
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [confirm, dialog] = useConfirm();

  /** Purpose: Load the users and the grantable features. Input: none. Output: a promise; a failure shows a message with Retry. */
  async function load() {
    try {
      const [list, meta] = await Promise.all([adminApi.list(), adminApi.features()]);
      setUsers(list); setFeatures(meta.features); setLoadError('');
    } catch (e) { setLoadError(e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  /**
   * Purpose: Create or update a user from the dialog.
   * Input: payload - the form values from the dialog.
   * Output: a promise; on success the dialog closes and the list reloads, on failure the dialog stays open with the message.
   */
  async function onSave(payload) {
    setSaving(true); setFormError('');
    try {
      const adding = form.mode === 'add';
      const saved = await (adding ? adminApi.create(payload) : adminApi.update(form.row.id, payload));
      setForm(null); setMessage(adding ? `${saved.full_name} was added.` : `${saved.full_name} was updated.`);
      await load();
    } catch (e) { setFormError(e.message); }
    finally { setSaving(false); }
  }

  /**
   * Purpose: Delete a user after the admin confirms.
   * Input: row - the user to delete.
   * Output: a promise; failures show an error message.
   */
  async function onDelete(row) {
    if (!await confirm({ tone: 'danger', title: 'Delete this user?', confirmLabel: 'Delete', detail: `${row.full_name} (${row.email})`,
      message: 'They will no longer be able to sign in. Documents they uploaded are kept. This can\'t be undone.' })) return;
    setError(''); setMessage('');
    try {
      await adminApi.remove(row.id);
      setMessage(`${row.full_name} was deleted.`);
      await load();
    } catch (e) { setError(e.message); }
  }

  return <AppShell user={user} onSignOut={onSignOut} active="users" title="Users and permissions"
    actions={<button type="button" className="vp-action" disabled={!features.length} onClick={() => { setFormError(''); setForm({ mode: 'add' }); }}><Plus size={15}/> Add user</button>}>
    {dialog}
    {form && <UserDialog key={form.row?.id ?? 'new'} mode={form.mode} initial={form.row} features={features} busy={saving} error={formError}
      isSelf={form.row?.id === user?.id} onSave={onSave} onCancel={() => { if (!saving) { setForm(null); setFormError(''); } }}/>}
    <main className="workspace plies-workspace">
      {error && <div className="alert error" role="alert"><AlertTriangle size={18}/><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}>Dismiss</button></div>}
      {message && <div className="alert success" role="status"><Check size={18}/><span>{message}</span><button aria-label="Dismiss message" onClick={() => setMessage('')}>Dismiss</button></div>}
      {loadError && <div className="alert error" role="alert"><AlertTriangle size={18}/><span>Could not load the users: {loadError}</span><button onClick={load}>Retry</button></div>}

      <section className="panel plies-panel">
        <div className="plies-toolbar">
          <span className="users-note"><ShieldCheck size={15}/> Admins can use everything. For everyone else, choose what each area allows.</span>
        </div>
        {loading ? <div className="loading-workspace" role="status"><span className="spinner"/> Loading users…</div> :
          !users.length ? <p className="plies-empty">No users yet.</p> :
          <div className="table-scroll"><table className="plies-table">
            <thead><tr><th>User</th><th>Access</th><th>Status</th><th className="actions-heading">Actions</th></tr></thead>
            <tbody>{users.map(row => <tr key={row.id}>
              <td><div className="person"><span className="person-avatar" aria-hidden="true">{initials(row.full_name)}</span>
                <span><strong>{row.full_name}{row.id === user?.id && <small className="muted-cell"> (you)</small>}</strong><small>{row.email}</small></span></div></td>
              <td title={describeAccess(row, features)}><AccessChips user={row} features={features}/></td>
              <td><span className={`status ${row.is_active ? 'approved' : 'failed'}`}>{row.is_active ? 'Active' : 'Disabled'}</span></td>
              <td><div className="row-actions">
                <button type="button" className="icon-button" aria-label={`Edit ${row.full_name}`} title="Edit"
                  onClick={() => { setFormError(''); setForm({ mode: 'edit', row }); }}><Pencil size={15}/></button>
                <button type="button" className="icon-button row-delete-inline" aria-label={`Delete ${row.full_name}`} title="Delete"
                  disabled={row.id === user?.id} onClick={() => onDelete(row)}><Trash2 size={15}/></button>
              </div></td>
            </tr>)}</tbody>
          </table></div>}
      </section>
    </main>
  </AppShell>;
}
