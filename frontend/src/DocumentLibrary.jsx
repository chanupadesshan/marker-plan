import React, { useState } from 'react';
import { ArrowLeft, Search } from 'lucide-react';
import { DocumentRow } from './Sidebar.jsx';
import { filterDocuments, latestDocuments } from './documentSearch.js';

export default function DocumentLibrary({ kind, items, selectedId, busy, onSelect, onDelete, onBack, error, message }) {
  const [query, setQuery] = useState('');
  const visible = latestDocuments(filterDocuments(items, query), Infinity);
  const label = kind === 'po' ? 'purchase orders' : 'Tech Packs';
  return <main className="workspace document-library">
    <button type="button" className="secondary-button library-back" onClick={onBack}><ArrowLeft size={16}/> Back</button>
    {error && <div className="alert error" role="alert">{error}</div>}
    {message && <div className="alert success" role="status">{message}</div>}
    <div className="library-heading"><div><h2>All {label}</h2><p>{visible.length} of {items.length} documents · Latest first</p></div>
      <label className="side-search"><Search size={16} aria-hidden="true"/><input type="search" aria-label={`Search all ${label}`} placeholder="Search documents" value={query} onChange={event => setQuery(event.target.value)}/></label>
    </div>
    <section className="document-topbar library-cards" aria-label={`All ${label}`}>
      <div className="document-list side-list is-expanded">{visible.map(item => <DocumentRow key={item.id} kind={kind} item={item} selected={item.id === selectedId} busy={busy} onSelect={onSelect} onDelete={onDelete}/>)}</div>
      {!visible.length && <p className="empty-small">{query ? 'No documents match your search.' : 'No documents yet.'}</p>}
    </section>
  </main>;
}
