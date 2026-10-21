import React from 'react';
import TokenUsage from './TokenUsage.jsx';

const value = item => item == null || item === '' ? '—' : item;
const fields = [['tech_pack_reference', 'Tech Pack'], ['model_id', 'Model'], ['quality_id', 'Quality'],
  ['color_id', 'Color'], ['registered_date', 'Registered'], ['shipping_date', 'Shipping'],
  ['total_quantity', 'Total quantity'], ['total_amount', 'Printed total amount'], ['currency', 'Currency'],
  ['modified_by', 'Modified by'], ['signed_by', 'Signed by']];

export default function PurchaseOrderWorkspace({ current, busy = false, showEditor = false, editor = '',
  onApprove, onToggleEditor, onEditorChange, onSave }) {
  const extraction = current.extraction;
  const orders = extraction?.orders || [];
  const processing = ['queued', 'processing'].includes(current.status);
  const base = `/api/purchase-orders/${current.id}`;
  return <>
    <section className="document-overview">
      <div className="document-title-row"><div className="document-title"><span className="eyebrow">PURCHASE ORDER</span><h2>{current.filename}</h2></div>
        <span className={`status ${current.status}`}>{current.status?.replaceAll('_', ' ')}</span></div>
      <div className="document-toolbar"><div className="document-facts"><span>{current.page_count ?? '—'} PDF pages</span><span>{orders.length} contracts</span></div>
        <div className="button-group"><a className="secondary-button" href={`${base}/pdf`} target="_blank" rel="noreferrer">View PDF</a>
          {extraction && <a className="secondary-button" href={`${base}/json`}>Export JSON</a>}
          <button className="primary-button" disabled={busy || !current.approval_ready || !orders.length || current.status === 'approved'} onClick={onApprove}>{current.status === 'approved' ? 'Approved' : 'Approve PO'}</button></div></div>
    </section>
    {current.error && <div className="alert error" role="alert"><div><strong>PO extraction needs attention</strong><p>{current.error}</p><p>Completed page results remain available. Upload again to complete failed processing.</p></div></div>}
    {processing && <section className="processing panel" role="status"><span className="spinner"/><div><h2>Reading purchase-order pages</h2><p>Each page is saved and processed. Results update automatically.</p></div></section>}
    {!!extraction?.warnings?.length && <details className="warning-box"><summary>{extraction.warnings.length} notes to review</summary><ul>{extraction.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
    {orders.map((order, index) => <section className="panel po-contract" key={index}>
      <div className="panel-heading"><div><span className="eyebrow">CONTRACT {index + 1}</span><h2>{order.contract_number || 'Unidentified contract'}</h2></div>
        <div className="button-group">{order.source_pages?.map(page => <a className="secondary-button" key={page} target="_blank" rel="noreferrer" href={`${base}/pdf#page=${page}`}>PDF page {page}</a>)}</div></div>
      <dl className="po-facts">{fields.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{value(order[key])}</dd></div>)}</dl>
      {!!order.warnings?.length && <ul className="po-notes">{order.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}
      <div className="table-scroll"><table><thead><tr><th>Size</th><th>Quantity</th><th>Unit price</th><th>Amount</th><th>Currency</th><th>Source page</th></tr></thead>
        <tbody>{order.size_rows?.map((row, i) => <tr key={i}><td>{value(row.size)}</td><td>{value(row.quantity)}</td><td>{value(row.unit_price)}</td><td>{value(row.amount)}</td><td>{value(row.currency)}</td><td>{row.source_page ? <a href={`${base}/pdf#page=${row.source_page}`} target="_blank" rel="noreferrer">{row.source_page}</a> : '—'}</td></tr>)}</tbody></table></div>
    </section>)}
    {!processing && !orders.length && <section className="empty-result"><h2>No purchase orders to review</h2><p>Check the source PDF and page outcomes below.</p></section>}
    <details className="technical-details"><summary>Technical details · token usage and corrections</summary><div className="technical-content">
      <p>Model: {current.model || 'Unavailable'}</p><TokenUsage entries={current.request_usage || []}/>
      {extraction && <><p>{extraction.page_results?.length || 0} of {current.page_count ?? '—'} pages completed.</p>
        <ul>{extraction.page_results?.map(page => <li key={page.page_number}>Page {page.page_number}: {page.result.page_kind}</li>)}</ul>
        <button className="secondary-button" disabled={processing || busy} onClick={onToggleEditor}>{showEditor ? 'Close editor' : 'Edit PO JSON'}</button>
        {showEditor && <div className="editor"><label htmlFor="po-json">Purchase-order corrections (orders only)</label><textarea id="po-json" rows={18} spellCheck="false" value={editor} onChange={event => onEditorChange?.(event.target.value)}/><button className="primary-button" disabled={busy || processing} onClick={onSave}>Save corrections</button></div>}</>}
    </div></details>
  </>;
}
