import React, { useRef, useState } from 'react';
import { FileText, FileUp, ScanText, Search, Trash2, X } from 'lucide-react';
import { filterDocuments, latestDocuments } from './documentSearch.js';
import TechPackProgress from './TechPackProgress.jsx';
import { checkLabel, designIds } from './po-link.js';

/** Purpose: Make a status readable. Input: status - e.g. 'needs_review'. Output: the text with spaces, e.g. 'needs review'. */
const statusText = status => (status || '').replaceAll('_', ' ');

/**
 * Purpose: Build the small line under a document's name in the list.
 * Input: kind - 'techpack' (a style) or 'po' (a purchase order without a Tech Pack); item - the list entry.
 * Output: text such as 'needs review · Style 1449 · Quality ID 1845 · 2 POs' for a style, or 'approved · 33 contracts' for a PO.
 */
function subtitle(kind, item) {
  if (kind === 'po') {
    const contracts = item.contract_count ? `${item.contract_count} ${item.contract_count === 1 ? 'contract' : 'contracts'}` : '';
    return [statusText(item.status), contracts, checkLabel(item.id_check), item.linked_to].filter(Boolean).join(' · ');
  }
  const reference = [item.style_number ? `Style ${item.style_number}` : item.tech_pack_number ? `TP ${item.tech_pack_number}` : '',
    designIds(item).length ? `Quality ID${designIds(item).length > 1 ? 's' : ''} ${designIds(item).join(', ')}` : '',
    typeof item.po_count === 'number' ? `${item.po_count} ${item.po_count === 1 ? 'PO' : 'POs'}` : ''];
  return [statusText(item.status), ...reference].filter(Boolean).join(' · ');
}

/**
 * Purpose: Format an upload time for the list.
 * Input: value - an ISO date string, or nothing.
 * Output: a short local date and time, or '' when missing or invalid.
 */
function dateLabel(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '';
}

/**
 * Purpose: A search field with a clear button.
 * Input: props - value: the text; onChange(text): called on every change; label: the accessible name; placeholder.
 * Output: the search field element.
 */
function SearchBox({ value, onChange, label, placeholder }) {
  return <label className="side-search"><Search size={15} aria-hidden="true"/>
    <input type="search" value={value} onChange={event => onChange(event.target.value)} placeholder={placeholder} aria-label={label}/>
    {value && <button type="button" className="icon-button" aria-label="Clear search" onClick={() => onChange('')}><X size={14}/></button>}
  </label>;
}

/**
 * Purpose: One document in a list: a button to open it and a trash button to delete it. Delete is
 * disabled while the document is queued or processing, because the extraction is still writing to it.
 * Input: props - kind: 'techpack' or 'po'; item: the list entry; selected: it is the open one; busy: disable
 * the delete button; onSelect(kind, id) and onDelete(kind, item): callbacks.
 * Output: the row element.
 */
export function DocumentRow({ kind, item, selected, busy, onSelect, onDelete, canDelete = true }) {
  // A running extraction still writes to its row, so it cannot be deleted until it finishes.
  const running = ['queued', 'processing'].includes(item.status);
  return <div className="document-row">
    <button type="button" className={`document-entry ${selected ? 'selected' : ''}`}
      aria-current={selected ? 'true' : undefined} onClick={() => onSelect(kind, item.id)}>
      <FileText className="doc-file-icon" size={17}/>
      <span className="doc-copy"><strong title={item.filename}>{item.filename}</strong>
        <small><i className={`status-dot ${item.status}`}/>{subtitle(kind, item)}</small>
        {item.created_at && <time dateTime={item.created_at}>{dateLabel(item.created_at)}</time>}</span>
    </button>
    {canDelete && <button type="button" className="icon-button row-delete" disabled={busy || running}
      aria-label={`Delete ${item.filename}`} title={running ? 'Wait until extraction finishes to delete' : 'Delete'}
      onClick={() => onDelete?.(kind, item)}><Trash2 size={15}/></button>}
  </div>;
}

/**
 * Purpose: The start of Create Marker Plan: upload a Tech Pack to start a style. Saved Tech Packs are in the Tech Packs
 * tab, and a style's purchase order is submitted inside the style.
 * Input: props - busy: an upload is running; canUpload; onUpload(kind, file): called with the chosen PDF.
 * Output: the panel element.
 */
function StylesPanel({ busy, canUpload, onUpload }) {
  const input = useRef(null);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);

  /** Purpose: Upload the chosen Tech Pack, and clear the choice if it was accepted. Input: none. Output: a promise that finishes when done. */
  async function extract() {
    if (!file) return;
    setUploading(true);
    try {
      const accepted = await onUpload('techpack', file);
      if (accepted !== false) setFile(null);
    } finally { setUploading(false); }
  }

  return <div role="tabpanel" id="panel-styles" className="side-panel">
    {canUpload && <>
      <div className={`side-upload ${file ? 'has-file' : ''}`}>
        <input ref={input} className="visually-hidden" type="file" accept="application/pdf,.pdf" aria-label="Choose Tech Pack PDF"
          disabled={busy} onChange={event => {
            const selected = event.target.files?.[0];
            if (selected) setFile(selected);
            event.target.value = '';
          }}/>
        <button type="button" className="side-upload-picker" disabled={busy} onClick={() => input.current?.click()}>
          {file ? <FileText size={20}/> : <FileUp size={20}/>}
          <span><strong title={file?.name}>{file ? file.name : 'Upload Tech Pack'}</strong>
            <small>{file ? 'Click to change file' : 'Start a new style from its Tech Pack PDF'}</small></span>
        </button>
        {file && <button type="button" className="icon-button" disabled={busy} aria-label="Remove Tech Pack file" onClick={() => setFile(null)}><X size={15}/></button>}
      </div>
      <button type="button" className="primary-button side-extract" disabled={!file || busy} onClick={extract}>
        <ScanText size={16}/>{busy ? 'Uploading…' : 'Extract Wovens and Knits'}</button>
    </>}

    {!canUpload && <p className="side-hint">You can open saved Tech Packs from the Tech Packs tab.</p>}
    {uploading && <TechPackProgress uploading kind="techpack"/>}
  </div>;
}

/**
 * Purpose: A library list: every Tech Pack, or every purchase order, to search, open and delete. Nothing is uploaded here;
 * documents are added in Create Marker Plan.
 * Input: props - kind: 'techpack' or 'po'; items: the list entries (a PO has linked_to, the style it belongs to); selectedId: the open one;
 * busy; onSelect(kind, id), onDelete(kind, item), onBrowse(): callbacks.
 * Output: the list element.
 */
export function ArchiveList({ kind, items, selectedId, busy, onSelect, onDelete, onBrowse }) {
  const [query, setQuery] = useState('');
  const label = kind === 'po' ? 'purchase orders' : 'Tech Packs';
  const visible = filterDocuments(items, query);
  const searching = Boolean(query.trim());
  const cards = latestDocuments(visible, searching ? Infinity : 5);
  return <section className="sidebar side-nav document-topbar" aria-label={`Saved ${label}`}>
    <div role="tabpanel" id={`panel-${kind}`} className="side-panel">
      <SearchBox value={query} onChange={setQuery} label={`Search ${label}`}
        placeholder={kind === 'po' ? 'File, contract or Tech Pack' : 'File, style, Quality ID or Tech Pack no.'}/>
      <div className="sidebar-header"><h3>Saved {label}<span>{query ? `${visible.length} of ${items.length}` : items.length}</span></h3></div>
      <div id={`documents-${kind}`} className={`document-list side-list ${searching ? 'is-expanded' : ''}`}>
        {cards.map(item => <DocumentRow key={item.id} kind={kind} item={item} selected={item.id === selectedId}
          busy={busy} onSelect={onSelect} onDelete={onDelete}/>)}
        {!visible.length && <p className="empty-small">{items.length ? 'No matches. Try a different file name or number.'
          : `No ${label} yet. Add one in Create Marker Plan.`}</p>}
      </div>
      {!searching && visible.length > 5 && <div className="document-list-footer">
        <span>Showing {cards.length} of {visible.length} {label} · Latest first</span>
        <a className="secondary-button" href={`/?tab=${kind}&view=documents`} onClick={event => {
          if (onBrowse && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); onBrowse(kind); }
        }}>Read more</a>
      </div>}
    </div>
  </section>;
}

/**
 * Purpose: The top document bar of the Create Marker Plan view.
 * Input: props - busy: an upload is running; canUpload: may add a Tech Pack; onUpload(kind, file): called with the chosen PDF.
 * Output: the sidebar element.
 */
export default function Sidebar({ busy = false, canUpload = true, onUpload }) {
  return <section className="sidebar side-nav document-topbar" aria-label="Start a style">
    <StylesPanel busy={busy} canUpload={canUpload} onUpload={onUpload}/>
  </section>;
}
