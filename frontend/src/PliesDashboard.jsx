import React, { useEffect, useState } from 'react';
import { AlertTriangle, Check, Pencil, Plus, Search, Trash2, X } from 'lucide-react';
import { pliesApi } from './api.js';
import AppShell from './AppShell.jsx';
import { PLY_COLUMNS, filterPlies, pageSlice, toPayload } from './plies.js';
import PlyFormDialog from './PlyFormDialog.jsx';
import { useConfirm } from './useConfirm.jsx';

/** Purpose: Show a value in the table. Input: value - any value. Output: the value, or '—' when it is missing or empty. */
const dash = value => value == null || value === '' ? '—' : value;

/**
 * Purpose: The Plies dashboard, a separate page where the rows of the plies table can be searched,
 * added, edited and deleted. Changes are saved to the database straight away.
 * Input: user - the signed-in person; onSignOut - called by the Sign out button.
 * Output: the page: top bar, summary figures, search, the table with Edit and Delete buttons, and paging.
 */
export default function PliesDashboard({ user, onSignOut }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [form, setForm] = useState(null);        // null, or { mode: 'add' | 'edit', row }
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [highlightId, setHighlightId] = useState(null);
  const [confirm, dialog] = useConfirm();

  /**
   * Purpose: Load every ply row from the server.
   * Input: none.
   * Output: a promise that finishes when the list is loaded; a failure shows a message and keeps the old rows.
   */
  async function load() {
    try {
      setRows(await pliesApi.list());
      setLoadError('');
    } catch (e) { setLoadError(e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);
  // Bring a just-added or just-edited row into view (a new row sits at the end of the last page).
  useEffect(() => {
    if (highlightId != null) document.querySelector('tr.just-saved')?.scrollIntoView({ block: 'nearest' });
  }, [highlightId, rows, page]);

  /**
   * Purpose: Save the add/edit form: create a new row or update the one being edited.
   * Input: values - the form's text fields { col_b, col_c, col_d }.
   * Output: a promise that finishes when saved. On success the dialog closes and the list reloads; on failure
   * the dialog stays open with the server's message.
   */
  async function onSave(values) {
    setSaving(true); setFormError(''); setError('');
    try {
      const body = toPayload(values);
      if (form.mode === 'edit') {
        const saved = await pliesApi.update(form.row.id, body);
        setMessage(`Ply #${saved.id} was updated.`);
        setHighlightId(saved.id);
      } else {
        const saved = await pliesApi.create(body);
        setMessage(`Ply #${saved.id} was added.`);
        setHighlightId(saved.id);
        // A new row has the highest id, so clear the search and show the last page where it appears.
        setQuery(''); setPage(Number.MAX_SAFE_INTEGER);
      }
      setForm(null);
      await load();
    } catch (e) { setFormError(e.message); }
    finally { setSaving(false); }
  }

  /**
   * Purpose: Delete a row after the user confirms in a dialog.
   * Input: row - the ply row to delete.
   * Output: a promise that finishes when the row is deleted or the user cancels; a failure shows a message.
   */
  async function onDelete(row) {
    if (!await confirm({ tone: 'danger', title: 'Delete this ply?', confirmLabel: 'Delete',
      detail: `#${row.id} · B ${row.col_b} · C ${row.col_c} · D ${dash(row.col_d)}`,
      message: "This permanently removes the row from the plies table. This can't be undone." })) return;
    setError(''); setMessage('');
    try {
      await pliesApi.remove(row.id);
      setRows(list => list.filter(entry => entry.id !== row.id));
      setMessage(`Ply #${row.id} was deleted.`);
    } catch (e) { setError(`Delete failed: ${e.message}`); }
    finally { load(); }
  }

  const visible = filterPlies(rows, query);
  const view = pageSlice(visible, page);
  const missingD = rows.filter(row => !row.col_d).length;

  return <AppShell user={user} onSignOut={onSignOut} active="plies" title="Plies"
    actions={<button type="button" className="vp-action" onClick={() => { setFormError(''); setForm({ mode: 'add' }); }}><Plus size={15}/> Add ply</button>}>
    {dialog}
    {form && <PlyFormDialog key={form.row?.id ?? 'new'} mode={form.mode} initial={form.row} busy={saving} error={formError}
      onSave={onSave} onCancel={() => { if (!saving) { setForm(null); setFormError(''); } }}/>}
    <main className="workspace plies-workspace">
      {error && <div className="alert error" role="alert"><AlertTriangle size={18}/><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}>Dismiss</button></div>}
      {message && <div className="alert success" role="status"><Check size={18}/><span>{message}</span><button aria-label="Dismiss message" onClick={() => setMessage('')}>Dismiss</button></div>}
      {loadError && <div className="alert error" role="alert"><AlertTriangle size={18}/><span>Could not load the plies: {loadError}</span><button onClick={load}>Retry</button></div>}

      <div className="plies-stats" aria-label="Summary">
        <div><strong>{rows.length}</strong><span>Total rows</span></div>
        <div><strong>{query ? visible.length : rows.length}</strong><span>{query ? 'Matching search' : 'Showing'}</span></div>
        <div><strong>{missingD}</strong><span>Without {PLY_COLUMNS[2].label}</span></div>
      </div>

      <section className="panel plies-panel">
        <div className="plies-toolbar">
          <label className="side-search plies-search"><Search size={15} aria-hidden="true"/>
            <input type="search" value={query} placeholder="Search id, B, C or D" aria-label="Search plies"
              onChange={event => { setQuery(event.target.value); setPage(1); }}/>
            {query && <button type="button" className="icon-button" aria-label="Clear search" onClick={() => { setQuery(''); setPage(1); }}><X size={14}/></button>}
          </label>
        </div>

        {loading ? <div className="loading-workspace" role="status"><span className="spinner"/> Loading plies…</div> :
          !view.items.length ? <p className="plies-empty">{rows.length ? 'No rows match your search.' : 'There are no plies yet. Use “Add ply” to create the first one.'}</p> :
          <div className="table-scroll"><table className="plies-table">
            <thead><tr><th>ID</th>{PLY_COLUMNS.map(column => <th key={column.key}>{column.label}</th>)}<th className="actions-heading">Actions</th></tr></thead>
            <tbody>{view.items.map(row => <tr key={row.id} className={row.id === highlightId ? 'just-saved' : undefined}>
              <td className="muted-cell">{row.id}</td>
              <td>{row.col_b}</td><td><strong>{row.col_c}</strong></td><td>{dash(row.col_d)}</td>
              <td><div className="row-actions">
                <button type="button" className="icon-button" aria-label={`Edit ply ${row.id}`} title="Edit"
                  onClick={() => { setFormError(''); setForm({ mode: 'edit', row }); }}><Pencil size={15}/></button>
                <button type="button" className="icon-button row-delete-inline" aria-label={`Delete ply ${row.id}`} title="Delete"
                  onClick={() => onDelete(row)}><Trash2 size={15}/></button>
              </div></td>
            </tr>)}</tbody>
          </table></div>}

        {!loading && visible.length > 0 && <div className="plies-pager">
          <span>Showing {view.from}–{view.to} of {visible.length}</span>
          <div className="button-group">
            <button type="button" className="secondary-button" disabled={view.page <= 1} onClick={() => setPage(view.page - 1)}>Previous</button>
            <span className="pager-page">Page {view.page} of {view.pages}</span>
            <button type="button" className="secondary-button" disabled={view.page >= view.pages} onClick={() => setPage(view.page + 1)}>Next</button>
          </div>
        </div>}
      </section>
    </main>
  </AppShell>;
}
