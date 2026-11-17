import React, { useState } from 'react';
import { openFile } from './api.js';
import TokenUsage from './TokenUsage.jsx';
import PurchaseOrderEditor from './PurchaseOrderEditor.jsx';
import TechPackProgress from './TechPackProgress.jsx';

/** Purpose: Show a field value. Input: item - any value. Output: the value, or '—' when it is missing or empty. */
const value = item => item == null || item === '' ? '—' : item;
const fields = [['tech_pack_reference', 'Tech Pack ID'], ['model_id', 'Model ID'], ['quality_id', 'Quality ID'],
  ['color_id', 'Color ID'], ['total_quantity', 'Total quantity']];

/**
 * Purpose: Show a purchase order for review: its status, each contract's IDs and size/quantity table,
 * warnings, approval controls and a simple contract/size editor for permitted users.
 * Input: current PO, busy/canEdit flags and approve/save/retry callbacks.
 * Output: the PO review view.
 */
export default function PurchaseOrderWorkspace({ current, busy = false, canEdit = false,
  onApprove, onSaveData, onRetry, onExtractSkipped }) {
  const [editing, setEditing] = useState(false);
  const extraction = current.extraction;
  const orders = extraction?.orders || [];
  const processing = ['queued', 'processing'].includes(current.status);
  const base = `/api/purchase-orders/${current.id}`;
  // ID mismatches and skipped pages have their own messages, so they are not repeated in the notes.
  const notes = (extraction?.warnings || []).filter(text => !text.startsWith('ID mismatch: ') && !/^Page \d+ skipped/.test(text));
  const skipped = current.skipped_pages || [];
  // Same button at the top and after the contracts, so a long PO can be approved without scrolling back up.
  const approveButton = <button className="primary-button" disabled={!canEdit || editing || busy || processing || !current.approval_ready || !orders.length || current.status === 'approved'} onClick={onApprove}>{current.status === 'approved' ? 'Approved' : 'Approve PO'}</button>;
  return <>
    <section className="document-overview">
      <div className="document-title-row"><div className="document-title"><span className="eyebrow">PURCHASE ORDER</span><h2>{current.filename}</h2></div>
        <span className={`status ${current.status}`}>{current.status?.replaceAll('_', ' ')}</span></div>
      <div className="document-toolbar"><div className="document-facts"><span>{current.page_count ?? '—'} PDF pages</span><span>{orders.length} contracts</span></div>
        <div className="button-group"><a className="secondary-button" href={`${base}/pdf`} onClick={e => openFile(e, `${base}/pdf`)} target="_blank" rel="noreferrer">View PDF</a>
          {canEdit && extraction && !processing && current.status !== 'failed' && !editing && <button className="secondary-button" disabled={busy} onClick={() => setEditing(true)}>Edit PO</button>}
          {approveButton}</div></div>
    </section>
    {current.error && <div className="alert error" role="alert"><div><strong>PO extraction needs attention</strong><p>{current.error}</p><p>Completed page results remain available. Retry to process only failed or pending pages.</p>
      {canEdit && current.status === 'failed' && <button className="secondary-button" disabled={busy} onClick={onRetry}>Retry failed pages</button>}</div></div>}
    {!!skipped.length && !processing && <div className="alert warning" role="status"><div>
      <strong>{skipped.length} of {current.page_count} {skipped.length === 1 ? 'page was' : 'pages were'} skipped: not for this Tech Pack</strong>
      <p>Only the pages whose Model ID and Quality ID fit this Tech Pack were read. The others belong to other styles or Quality IDs.</p>
      <ul>{skipped.map(item => <li key={item.page}>Page {item.page}{item.contract_number ? ` · contract ${item.contract_number}` : ''}{' — '}
        {[item.model_id && `Model ID ${item.model_id}`, item.quality_id && `Quality ID ${item.quality_id}`].filter(Boolean).join(', ') || 'IDs not read'}</li>)}</ul>
      <p>If a page was skipped by mistake, for example its header was misread, you can read the skipped pages too.</p>
      {canEdit && ['needs_review', 'failed'].includes(current.status) && <button className="secondary-button" disabled={busy} onClick={onExtractSkipped}>Extract the skipped pages too</button>}</div></div>}
    {current.id_check === 'no_design' && !processing && <div className="alert warning" role="status"><div><strong>No Quality ID on this purchase order</strong>
      <p>The Model ID matches the Tech Pack's style number, but the purchase order shows no Quality ID, so it cannot be checked against the Tech Pack. Compare it with the Tech Pack's Quality IDs before approving.</p></div></div>}
    {!!current.id_mismatches?.length && <div className={`alert ${processing ? 'warning' : 'error'}`} role="alert"><div>
      <strong>{processing ? 'Possible mismatch with its Tech Pack, found while reading' : 'This purchase order does not match its Tech Pack'}</strong>
      <ul>{current.id_mismatches.map((text, index) => <li key={index}>{text.replace(/^ID mismatch: /, '')}</li>)}</ul>
      <p>{processing
        ? 'Extraction is still running, so more contracts may be checked. When it finishes, delete this purchase order and upload the right one if it is the wrong file.'
        : 'It cannot be approved until the IDs match. Correct them if they were misread, or upload the right purchase order.'}</p></div></div>}
    {processing && <TechPackProgress current={current} kind="po"/>}
    {!!notes.length && <details className="warning-box"><summary>{notes.length} notes to review</summary><ul>{notes.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
    {editing && <PurchaseOrderEditor extraction={extraction} busy={busy} onCancel={() => setEditing(false)}
      onSave={async payload => { await onSaveData(payload); setEditing(false); }}/>}
    {!editing && orders.map((order, index) => <section className="panel po-contract" key={index}>
      <div className="panel-heading"><div><span className="eyebrow">CONTRACT NO.</span><h2>{order.contract_number || 'Unidentified contract'}</h2></div>
        <div className="button-group">{order.source_pages?.map(page => <a className="secondary-button" key={page} target="_blank" rel="noreferrer" href={`${base}/pdf#page=${page}`} onClick={e => openFile(e, `${base}/pdf#page=${page}`)}>PDF page {page}</a>)}</div></div>
      <dl className="po-facts">{fields.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{value(order[key])}</dd></div>)}</dl>
      {!!order.warnings?.length && <ul className="po-notes">{order.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}
      <div className="table-scroll"><table><thead><tr><th>Size</th><th>Quantity</th></tr></thead>
        <tbody>{order.size_rows?.map((row, i) => <tr key={i}><td>{value(row.size)}</td><td>{value(row.quantity)}</td></tr>)}</tbody></table></div>
    </section>)}
    {!editing && orders.length > 0 && <div className="po-approve-bar"><p>{current.status === 'approved' ? 'This purchase order has been approved.' : 'Check the values against the source PDF before approving.'}</p>{approveButton}</div>}
    {!editing && !processing && !orders.length &&<section className="empty-result"><h2>No purchase orders to review</h2><p>Check the source PDF and page outcomes below.</p></section>}
    <details className="technical-details"><summary>Technical details · token usage and page outcomes</summary><div className="technical-content">
      <p>Model: {current.model || 'Unavailable'}</p><TokenUsage entries={current.request_usage || []}/>
      {extraction && <><p>{extraction.page_results?.length || 0} of {current.page_count ?? '—'} pages completed.</p>
        <ul>{extraction.page_results?.map(page => <li key={page.page_number}>Page {page.page_number}: {page.result.page_kind}</li>)}</ul>
        </>}
    </div></details>
  </>;
}
