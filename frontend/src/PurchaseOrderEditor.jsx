import React, { useRef, useState } from 'react';
import { createPoDraft, poPayload, poSizeTotal, validatePoDraft } from './po-editor.js';

const fields = [['contract_number', 'Contract number'], ['tech_pack_reference', 'Tech Pack ID'], ['model_id', 'Model ID'],
  ['quality_id', 'Quality ID'], ['color_id', 'Colour ID'], ['total_quantity', 'Total quantity']];

export default function PurchaseOrderEditor({ extraction, busy, onSave, onCancel }) {
  const [draft, setDraft] = useState(() => createPoDraft(extraction));
  const [errors, setErrors] = useState({});
  const [saveError, setSaveError] = useState('');
  const formRef = useRef(null);
  function change(update) {
    setDraft(previous => { const next = structuredClone(previous); update(next); return next; });
    setErrors({}); setSaveError('');
  }
  function error(key) { return errors[key] && <small id={`po-error-${key}`} className="bom-field-error">{errors[key]}</small>; }
  async function submit(event) {
    event.preventDefault();
    const nextErrors = validatePoDraft(draft);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) {
      // A long form hides the problem field, so take the user to the first one.
      setTimeout(() => {
        const field = formRef.current?.querySelector('[aria-invalid="true"]');
        field?.scrollIntoView({ block: 'center' });
        field?.focus({ preventScroll: true });
      }, 0);
      return;
    }
    try { await onSave(poPayload(draft)); } catch (failure) { setSaveError(failure.message || 'Unable to save changes. Please try again.'); }
  }
  return <form ref={formRef} className="bom-editor po-editor panel" onSubmit={submit}>
    <div className="panel-heading"><div><h2>Edit PO</h2><p>Check the contract details and size quantities against the source PDF. Saving will require approval again.</p></div></div>
    <fieldset disabled={busy}>
      {draft.orders.map((order, oi) => <section className="po-edit-contract" key={oi}>
        <div className="panel-heading"><h3>Contract {oi + 1}{order.contract_number ? ` · ${order.contract_number}` : ''}</h3>
          <button className="secondary-button" type="button" aria-label={`Remove contract ${oi + 1}`}
            onClick={() => change(next => { next.orders.splice(oi, 1); })}>Remove contract</button></div>
        {!!order.source_pages?.length && <p className="po-edit-source">Source PDF pages: {order.source_pages.join(', ')}</p>}
        <div className="po-edit-fields">{fields.map(([key, label]) => {
          const path = `${oi}.${key}`;
          return <div key={key}><label>{label}, contract {oi + 1}<input value={order[key] ?? ''} inputMode={key === 'total_quantity' ? 'numeric' : undefined}
            aria-invalid={Boolean(errors[path])} aria-describedby={errors[path] ? `po-error-${path}` : undefined}
            onChange={event => change(next => { next.orders[oi][key] = event.target.value; })}/></label>{error(path)}</div>;
        })}</div>
        <p className="po-size-total" role="status">Size quantity sum: <strong>{poSizeTotal(order) ?? 'Enter valid size quantities'}</strong></p>
        <div className="table-scroll" tabIndex={0} role="region" aria-label={`Editable sizes for contract ${oi + 1}`}><table className="bom-edit-table po-edit-sizes">
          <thead><tr><th>Size</th><th>Quantity</th><th>Actions</th></tr></thead>
          <tbody>{(order.size_rows || []).map((row, ri) => <tr key={ri}>
            {['size', 'quantity'].map(key => {
              const path = `${oi}.${ri}.${key}`;
              return <td key={key}><label className="sr-only" htmlFor={`po-${path}`}>{key === 'size' ? 'Size' : 'Quantity'}, contract {oi + 1}, row {ri + 1}</label>
                <input id={`po-${path}`} value={row[key] ?? ''} inputMode={key === 'quantity' ? 'numeric' : undefined}
                  aria-invalid={Boolean(errors[path])} aria-describedby={errors[path] ? `po-error-${path}` : undefined}
                  onChange={event => change(next => { next.orders[oi].size_rows[ri][key] = event.target.value; })}/>{error(path)}</td>;
            })}
            <td><button type="button" className="secondary-button" aria-label={`Remove size row ${ri + 1} from contract ${oi + 1}`}
              onClick={() => change(next => { next.orders[oi].size_rows.splice(ri, 1); })}>Remove row</button></td>
          </tr>)}</tbody>
        </table></div>
        {error(`${oi}.size_rows`)}
        <button type="button" className="secondary-button" onClick={() => change(next => {
          (next.orders[oi].size_rows ||= []).push({ size: '', quantity: '', source_page: null });
        })}>Add size row</button>
      </section>)}
      <button className="secondary-button" type="button" onClick={() => change(next => {
        next.orders.push({ contract_number: '', total_quantity: '', source_pages: [], warnings: [], size_rows: [{ size: '', quantity: '', source_page: null }] });
      })}>Add contract</button>
      <div className="bom-editor-actions">
        {Object.keys(errors).length > 0 && <p role="alert" className="bom-field-error">{errors.orders || `Cannot save yet: ${Object.values(errors)[0]}${Object.keys(errors).length > 1 ? ` (${Object.keys(errors).length} fields need attention)` : ''}`}</p>}
        {saveError && <p role="alert" className="bom-field-error">{saveError}</p>}
        <button className="primary-button" type="submit">{busy ? 'Saving…' : 'Save changes'}</button>
        <button className="secondary-button" type="button" onClick={onCancel}>Cancel</button></div>
    </fieldset>
  </form>;
}
