import React, { useRef, useState } from 'react';
import { FileText, FileUp, ScanText, Search, Trash2, X } from 'lucide-react';
import { filterDocuments } from './documentSearch.js';

// Upload tabs. The Marker Plan tab has no upload: it searches both document types at once.
const TABS = {
  techpack: { label: 'Tech Pack', uploadLabel: 'Upload Tech Pack', inputLabel: 'Choose Tech Pack PDF',
    extractLabel: 'Extract Wovens', searchLabel: 'Search Tech Packs', placeholder: 'File, style or Tech Pack no.',
    empty: 'No Tech Packs yet. Upload a PDF to extract its Wovens BOM.' },
  po: { label: 'Purchase Order', uploadLabel: 'Upload PO', inputLabel: 'Choose purchase order PDF',
    extractLabel: 'Extract PO', searchLabel: 'Search purchase orders', placeholder: 'File, contract or Tech Pack ID',
    empty: 'No purchase orders yet. Upload a PDF to extract contracts and sizes.' },
};
const PLAN_LABEL = 'Marker Plan';

const statusText = status => (status || '').replaceAll('_', ' ');

function subtitle(kind, item) {
  if (kind === 'po') {
    if (!item.contract_count) return statusText(item.status);
    return `${statusText(item.status)} · ${item.contract_count} ${item.contract_count === 1 ? 'contract' : 'contracts'}`;
  }
  const reference = item.style_number ? `Style ${item.style_number}` : item.tech_pack_number ? `TP ${item.tech_pack_number}` : '';
  return [statusText(item.status), reference].filter(Boolean).join(' · ');
}

function dateLabel(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '';
}

function SearchBox({ value, onChange, label, placeholder }) {
  return <label className="side-search"><Search size={15} aria-hidden="true"/>
    <input type="search" value={value} onChange={event => onChange(event.target.value)} placeholder={placeholder} aria-label={label}/>
    {value && <button type="button" className="icon-button" aria-label="Clear search" onClick={() => onChange('')}><X size={14}/></button>}
  </label>;
}

function DocumentRow({ kind, item, selected, busy, onSelect, onDelete }) {
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
    <button type="button" className="icon-button row-delete" disabled={busy || running}
      aria-label={`Delete ${item.filename}`} title={running ? 'Wait until extraction finishes to delete' : 'Delete'}
      onClick={() => onDelete?.(kind, item)}><Trash2 size={15}/></button>
  </div>;
}

function TabPanel({ kind, hidden, items, selectedId, busy, onSelect, onUpload, onDelete }) {
  const config = TABS[kind];
  const input = useRef(null);
  const [file, setFile] = useState(null);
  const [query, setQuery] = useState('');
  const visible = filterDocuments(items, query);
  async function extract() {
    if (!file) return;
    const accepted = await onUpload(kind, file);
    if (accepted !== false) setFile(null);
  }
  return <div role="tabpanel" id={`panel-${kind}`} aria-labelledby={`tab-${kind}`} className="side-panel" hidden={hidden}>
    <div className={`side-upload ${file ? 'has-file' : ''}`}>
      <input ref={input} className="visually-hidden" type="file" accept="application/pdf,.pdf" aria-label={config.inputLabel}
        disabled={busy} onChange={event => {
          const selected = event.target.files?.[0];
          if (selected) setFile(selected);
          event.target.value = '';
        }}/>
      <button type="button" className="side-upload-picker" disabled={busy} onClick={() => input.current?.click()}>
        {file ? <FileText size={20}/> : <FileUp size={20}/>}
        <span><strong title={file?.name}>{file ? file.name : config.uploadLabel}</strong>
          <small>{file ? 'Click to change file' : 'Choose a PDF from your computer'}</small></span>
      </button>
      {file && <button type="button" className="icon-button" disabled={busy} aria-label={`Remove ${config.label} file`} onClick={() => setFile(null)}><X size={15}/></button>}
    </div>
    <button type="button" className="primary-button side-extract" disabled={!file || busy} onClick={extract}>
      <ScanText size={16}/>{busy ? 'Uploading…' : config.extractLabel}</button>

    <SearchBox value={query} onChange={setQuery} label={config.searchLabel} placeholder={config.placeholder}/>

    <div className="sidebar-header"><h3>Extracted<span>{query ? `${visible.length} of ${items.length}` : items.length}</span></h3></div>
    <div className="document-list side-list">
      {visible.map(item => <DocumentRow key={item.id} kind={kind} item={item} selected={item.id === selectedId}
        busy={busy} onSelect={onSelect} onDelete={onDelete}/>)}
      {!visible.length && <p className="empty-small">{items.length ? 'No matches. Try a different file name or number.' : config.empty}</p>}
    </div>
  </div>;
}

// One search box over every Tech Pack and purchase order, results grouped by type.
function PlanPanel({ hidden, techPacks, purchaseOrders, selected, busy, onSelect, onDelete }) {
  const [query, setQuery] = useState('');
  const groups = [
    { kind: 'techpack', title: 'Tech Packs', items: filterDocuments(techPacks, query) },
    { kind: 'po', title: 'Purchase Orders', items: filterDocuments(purchaseOrders, query) },
  ];
  const total = techPacks.length + purchaseOrders.length;
  const matches = groups.reduce((sum, group) => sum + group.items.length, 0);
  return <div role="tabpanel" id="panel-plan" aria-labelledby="tab-plan" className="side-panel" hidden={hidden}>
    <p className="side-hint">Search every Tech Pack and purchase order at once. A Tech Pack number finds the Tech Pack and the POs that reference it.</p>
    <SearchBox value={query} onChange={setQuery} label="Search Tech Packs and purchase orders" placeholder="File, style, contract or Tech Pack ID"/>
    <div className="sidebar-header"><h3>Results<span>{query ? `${matches} of ${total}` : total}</span></h3></div>
    <div className="document-list side-list">
      {groups.filter(group => group.items.length).map(group => <section key={group.kind} className="plan-group" aria-label={group.title}>
        <h4>{group.title}<span>{group.items.length}</span></h4>
        {group.items.map(item => <DocumentRow key={item.id} kind={group.kind} item={item} selected={item.id === selected[group.kind]}
          busy={busy} onSelect={onSelect} onDelete={onDelete}/>)}
      </section>)}
      {!matches && <p className="empty-small">{total ? 'No matches. Try a different file name or number.' : 'Nothing extracted yet. Upload a Tech Pack or purchase order from its tab.'}</p>}
    </div>
  </div>;
}

export default function Sidebar({ tab, onTabChange, techPacks = [], purchaseOrders = [], selected = {}, busy = false, onSelect, onUpload, onDelete }) {
  const lists = { techpack: techPacks, po: purchaseOrders };
  const tabs = [...Object.entries(TABS).map(([kind, config]) => [kind, config.label, lists[kind].length]), ['plan', PLAN_LABEL, null]];
  return <aside className="sidebar side-nav" aria-label="Documents">
    <div role="tablist" aria-label="Document type" className="side-tabs">
      {tabs.map(([kind, label, count]) => <button key={kind} type="button" role="tab" id={`tab-${kind}`} aria-selected={tab === kind}
        aria-controls={`panel-${kind}`} className={tab === kind ? 'active' : ''} onClick={() => onTabChange(kind)}>
        {label}{count !== null && <span>{count}</span>}</button>)}
    </div>
    {/* All panels stay mounted so each tab keeps its own search text and chosen file. */}
    {Object.keys(TABS).map(kind => <TabPanel key={kind} kind={kind} hidden={tab !== kind} items={lists[kind]}
      selectedId={selected[kind]} busy={busy} onSelect={onSelect} onUpload={onUpload} onDelete={onDelete}/>)}
    <PlanPanel hidden={tab !== 'plan'} techPacks={techPacks} purchaseOrders={purchaseOrders} selected={selected}
      busy={busy} onSelect={onSelect} onDelete={onDelete}/>
  </aside>;
}
