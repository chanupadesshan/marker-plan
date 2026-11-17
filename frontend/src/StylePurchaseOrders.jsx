import React, { useRef, useState } from 'react';
import { FileText, FileUp, Lock, ScanText, X } from 'lucide-react';
import { DocumentRow } from './Sidebar.jsx';
import TechPackProgress from './TechPackProgress.jsx';
import { designIds, groupOrders, isApproved, lockedReason } from './po-link.js';

/**
 * Purpose: The purchase-order stage of a style: show the IDs the purchase order must carry, take the PO upload, and list this
 * style's POs under headings by how their IDs compare (matching, style matches but no Quality ID, not matching).
 * Input: props - techPack: the style's Tech Pack list entry (with style_number and design_numbers); orders: its linked POs, each with an id_check;
 * selectedId: the PO open below; busy: something is running; canUpload: may add a PO; canDelete: may delete one;
 * onSelect(id), onUpload(file) (a promise of true when accepted) and onDelete(item): callbacks.
 * Output: the panel element.
 */
export default function StylePurchaseOrders({ techPack, orders, selectedId, busy, canUpload, canDelete, onSelect, onUpload, onDelete }) {
  const input = useRef(null);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const designs = designIds(techPack);

  /** Purpose: Upload the chosen PO for this style, and clear the choice if it was accepted. Input: none. Output: a promise. */
  async function extract() {
    if (!file) return;
    setUploading(true);
    try {
      if (await onUpload(file) !== false) setFile(null);
    } finally { setUploading(false); }
  }

  if (!isApproved(techPack)) return <section className="panel style-po-panel"><p className="side-hint" role="status"><Lock size={14}/> {lockedReason('po', techPack)}</p></section>;
  const idBox = (label, match, value) => <div className={`id-box ${value ? '' : 'missing'}`}>
    <small>{label}</small><strong>{value || 'Not found'}</strong><span>{match}</span></div>;
  return <section className="panel style-po-panel" aria-label="Purchase orders for this style">
    <div className="panel-heading"><div><h2>Submit the purchase order</h2>
      <p>The purchase order must carry these IDs from the approved Tech Pack.
        If the PO shows no Quality ID, it is listed separately for you to check before approving.</p></div></div>
    <div className="id-boxes">
      {idBox('Style number', 'must equal the PO Model ID', techPack.style_number)}
      {idBox(designs.length > 1 ? 'Quality IDs' : 'Quality ID', designs.length > 1 ? 'the PO Quality ID must be one of these' : 'must equal the PO Quality ID', designs.join(' · '))}
    </div>
    {canUpload && <div className="style-po-upload">
      <div className={`side-upload ${file ? 'has-file' : ''}`}>
        <input ref={input} className="visually-hidden" type="file" accept="application/pdf,.pdf" aria-label="Choose purchase order PDF"
          disabled={busy} onChange={event => {
            const selected = event.target.files?.[0];
            if (selected) setFile(selected);
            event.target.value = '';
          }}/>
        <button type="button" className="side-upload-picker" disabled={busy} onClick={() => input.current?.click()}>
          {file ? <FileText size={20}/> : <FileUp size={20}/>}
          <span><strong title={file?.name}>{file ? file.name : 'Upload purchase order'}</strong>
            <small>{file ? 'Click to change file' : 'Choose the PO PDF for this Tech Pack'}</small></span>
        </button>
        {file && <button type="button" className="icon-button" disabled={busy} aria-label="Remove purchase order file" onClick={() => setFile(null)}><X size={15}/></button>}
      </div>
      <button type="button" className="primary-button side-extract" disabled={!file || busy} onClick={extract}>
        <ScanText size={16}/>{busy ? 'Uploading…' : 'Extract PO'}</button>
    </div>}
    {uploading && <TechPackProgress uploading kind="po"/>}
    {!orders.length && <p className="empty-small">No purchase order submitted for this Tech Pack yet.</p>}
    {groupOrders(orders).map(group => <div key={group.key} className={`po-group ${group.key}`}>
      <div className="sidebar-header"><h3>{group.title}<span>{group.items.length}</span></h3></div>
      <p className="side-hint">{group.note}</p>
      <div className="document-topbar style-po-list"><div className="document-list side-list is-expanded">
        {group.items.map(item => <DocumentRow key={item.id} kind="po" item={item} selected={item.id === selectedId} busy={busy}
          canDelete={canDelete} onSelect={(kind, id) => onSelect(id)} onDelete={(kind, entry) => onDelete(entry)}/>)}
      </div></div>
    </div>)}
  </section>;
}
