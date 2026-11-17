import React, { useEffect, useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight, ShieldCheck } from 'lucide-react';
import { auditApi } from './api.js';
import AppShell from './AppShell.jsx';
import { PAGE_SIZE, actionLabel, auditQuery, formatWhen, hasDetails, planFacts, planMaterials, showValue, summarizeEntry } from './audit.js';

/**
 * Purpose: The full detail of one log entry, shown in a panel across the whole table under its row: for a marker plan its
 * settings in a grid and its materials in a small table; for an edit each change as field, before and after.
 * Input: entry - an audit entry from the server.
 * Output: the panel.
 */
function EntryPanel({ entry }) {
  if (entry.target_type === 'marker_plan') {
    const materials = planMaterials(entry.details);
    return <div className="audit-panel">
      <dl className="audit-facts-grid">{planFacts(entry.details).filter(([label]) => label !== 'Materials')
        .map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      {!!materials.length && <div className="audit-materials table-scroll"><table>
        <thead><tr><th>Material</th><th>Consumption</th><th>Max plies</th></tr></thead>
        <tbody>{materials.map((item, index) => <tr key={index}><td>{item.code}</td><td>{item.consumption}</td><td>{item.maxPlies}</td></tr>)}</tbody>
      </table></div>}
    </div>;
  }
  return <div className="audit-panel">
    <div className="audit-materials table-scroll"><table>
      <thead><tr><th>Field</th><th>Before</th><th>After</th></tr></thead>
      <tbody>{(entry.details?.changes || []).map((change, index) => <tr key={index}>
        <td><code>{change.path}</code></td>
        <td className="audit-before">{showValue(change.before)}</td>
        <td className="audit-after">{showValue(change.after)}</td>
      </tr>)}</tbody>
    </table></div>
    {entry.details?.more_changes > 0 && <p className="audit-more">Plus at least {entry.details.more_changes} more changes that are not listed.</p>}
  </div>;
}

/**
 * Purpose: The Activity log, an admin-only page listing who edited or approved Tech Packs and purchase orders and who
 * created, deleted or downloaded marker plans, and when, with what changed. It can be filtered by action and searched by file or person.
 * Input: user - the signed-in admin; onSignOut - called by the Sign out button.
 * Output: the page: top bar, filters, the table of entries and previous/next paging.
 */
export default function AuditLog({ user, onSignOut }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [page, setPage] = useState(0);
  const [action, setAction] = useState('');
  const [typed, setTyped] = useState('');
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(() => new Set());

  /** Purpose: Load the current page of the log. Input: none. Output: a promise; a failure shows a message and keeps the old rows. */
  async function load() {
    try {
      setData(await auditApi.list(auditQuery({ page, action, search })));
      setError('');
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, [page, action, search]);

  /** Purpose: Open or close one entry's details. Input: id - the entry's id. Output: nothing. */
  function toggle(id) {
    setOpen(previous => { const next = new Set(previous); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }

  const total = data?.total ?? 0;
  const last = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);

  return <AppShell user={user} onSignOut={onSignOut} active="audit" title="Activity log">
    <main className="workspace plies-workspace">
      {error && <div className="alert error" role="alert"><AlertTriangle size={18}/><span>Could not load the activity log: {error}</span><button onClick={load}>Retry</button></div>}

      <section className="panel plies-panel">
        <div className="plies-toolbar">
          <span className="users-note"><ShieldCheck size={15}/> Every edit and approval of a Tech Pack or purchase order, and every marker plan created, deleted or downloaded, newest first. Entries cannot be changed or removed.</span>
          <form className="audit-filters" onSubmit={event => { event.preventDefault(); setPage(0); setSearch(typed); }}>
            <select aria-label="Filter by action" value={action} onChange={event => { setPage(0); setAction(event.target.value); }}>
              <option value="">All actions</option>
              {(data?.actions || []).map(name => <option key={name} value={name}>{actionLabel(name)}</option>)}
            </select>
            <input type="search" aria-label="Search by file or person" placeholder="File, name or email" value={typed} onChange={event => setTyped(event.target.value)}/>
            <button type="submit" className="secondary-button">Search</button>
          </form>
        </div>

        {!data && !error && <div className="loading-workspace" role="status"><span className="spinner"/> Loading activity…</div>}
        {data && (!data.items.length ? <p className="plies-empty">{action || search ? 'No activity matches these filters.' : 'Nothing has been recorded yet. Edits and approvals will appear here.'}</p> :
          <div className="table-scroll"><table className="plies-table audit-table"><thead><tr><th>When</th><th>Who</th><th>Action</th><th>Document</th><th>Details</th></tr></thead>
            <tbody>{data.items.map(entry => {
              const expandable = hasDetails(entry), expanded = expandable && open.has(entry.id);
              return <React.Fragment key={entry.id}>
                <tr className={expanded ? 'audit-open' : undefined}>
                  <td>{formatWhen(entry.created_at)}</td>
                  <td><strong>{entry.user_name}</strong><br/><small>{entry.user_email}</small></td>
                  <td>{actionLabel(entry.action)}</td>
                  <td>{entry.target_name}</td>
                  <td>{expandable
                    ? <button type="button" className="audit-toggle" aria-expanded={expanded} onClick={() => toggle(entry.id)}>
                      {expanded ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}{summarizeEntry(entry)}</button>
                    : <span>{summarizeEntry(entry)}</span>}</td>
                </tr>
                {expanded && <tr className="audit-expanded"><td colSpan={5}><EntryPanel entry={entry}/></td></tr>}
              </React.Fragment>;
            })}</tbody></table></div>)}

        {data && total > PAGE_SIZE && <div className="audit-pager">
          <button type="button" className="secondary-button" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page + 1} of {last + 1} · {total} entries</span>
          <button type="button" className="secondary-button" disabled={page >= last} onClick={() => setPage(page + 1)}>Next</button>
        </div>}
      </section>
    </main>
  </AppShell>;
}
