import React, { useEffect, useState } from 'react';
import { changePoMode, togglePlanPo, allPlanOrders, searchPlanOrders } from './marker-po.js';
import { poApi } from './api';
const EMPTY_DOCUMENTS = [];

/** Preserve every printed size row, including repeated sizes and zero quantities. */
export function PoSizeCells({ order }) {
  const rows = order.size_rows || [];
  return <><td className="po-size-values">{rows.length ? rows.map((row, index) => <div key={index}>{row.size ?? '—'}</div>) : '—'}</td>
    <td className="po-size-values">{rows.length ? rows.map((row, index) => <div key={index}>{row.quantity ?? '—'}</div>) : '—'}</td></>;
}

/** PO choices are saved per Tech Pack in the current workspace session. */
export default function MarkerPoSelection({ purchaseOrders = EMPTY_DOCUMENTS, techPackReference, value, onChange, disabled = false }) {
  const [editing, setEditing] = useState(!value);
  const [mode, setMode] = useState(value?.mode || '');
  const [ids, setIds] = useState(value?.ids || []);
  const [query, setQuery] = useState('');
  const [modelId, setModelId] = useState(value?.modelId || '');
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError('');
    // Full extractions contain individual contracts; document summaries do not.
    Promise.allSettled(purchaseOrders.map(po => poApi.get(po.id))).then(results => {
      if (cancelled) return;
      setDocuments(results.filter(result => result.status === 'fulfilled').map(result => result.value));
      if (results.some(result => result.status === 'rejected')) setError('Some PO documents could not be loaded. Their purchase orders are unavailable.');
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [purchaseOrders]);
  const orders = allPlanOrders(documents);
  const models = [...new Set(orders.map(po => po.model_id).filter(Boolean))];
  const available = new Set(orders.map(po => po.id));
  const validIds = ids.filter(id => available.has(id));
  const saved = orders.filter(po => value?.ids.includes(po.id));
  const visible = searchPlanOrders(orders, query, modelId);
  return <section className="panel marker-material-summary marker-po-panel" aria-label="Marker plan purchase orders">
    <div className="panel-heading"><div><span className="eyebrow">FOR THIS TECH PACK</span><h2>Purchase orders</h2></div>
      {!editing && <button type="button" className="secondary-button" disabled={disabled}
        onClick={() => { setMode(value.mode); setModelId(value.modelId || ''); setIds(saved.map(po => po.id)); setQuery(''); setEditing(true); }}>Edit selection</button>}
    </div>
    <p>These are the approved purchase orders submitted for this Tech Pack, whose Model ID matches its style number.</p>
    {loading && <p role="status">Loading individual purchase orders…</p>}
    {error && <p role="alert">{error}</p>}
    {editing && <>
      <fieldset className="po-mode-options" disabled={disabled}><legend>Individual PO or multiple POs?</legend>
        {[['single', 'Individual PO'], ['multiple', 'Multiple POs']].map(([key, label]) => <label key={key}>
          <input type="radio" name="marker-po-mode" value={key} checked={mode === key}
            onChange={() => { setMode(key); setIds(changePoMode(validIds, key)); }}/>{label}
        </label>)}
      </fieldset>
      {mode && <>
        <p>{mode === 'single' ? 'Select one purchase order.' : 'Select one or more purchase orders.'} Choices are kept during this session.</p>
        <label className="plan-style-select">Model ID
          <select aria-label="Select PO Model ID" value={modelId} disabled={disabled || loading}
            onChange={event => setModelId(event.target.value)}>
            <option value="">All models (optional filter)</option>
            {models.map(model => <option key={model} value={model}>{model}</option>)}
          </select>
        </label>
        <div className="marker-material-search"><label htmlFor="marker-po-search">Search PO Tech Pack ID</label>
          <input id="marker-po-search" type="search" value={query} placeholder="e.g. 16404"
            onChange={event => setQuery(event.target.value)}/></div>
        <div className="table-scroll"><table><thead><tr><th>Use</th><th>Contract no.</th><th>Tech Pack ID</th><th>Model ID</th><th>Quality ID</th><th>Color ID</th><th>Total quantity</th><th>Size</th><th>Quantity</th></tr></thead>
          <tbody>{visible.map(po => <tr key={po.id}><td><input type={mode === 'single' ? 'radio' : 'checkbox'} name="marker-po-choice"
            aria-label={`Select contract ${po.contract_number || 'unknown'}, Tech Pack ${po.tech_pack_reference}, ${po.filename}`} checked={validIds.includes(po.id)} disabled={disabled || loading}
            onChange={event => setIds(togglePlanPo(validIds, po.id, event.target.checked, mode))}/></td>
            <td>{po.contract_number || '—'}</td><td>{po.tech_pack_reference}</td><td>{po.model_id || '—'}</td><td>{po.quality_id || '—'}</td>
            <td>{po.color_id || '—'}</td><td>{po.total_quantity || '—'}</td><PoSizeCells order={po}/></tr>)}</tbody></table></div>
        {!loading && !visible.length && <p role="status">{!orders.length ? 'No approved purchase order is available for this Tech Pack.' : 'No POs match the entered Tech Pack ID and optional Model ID filter.'}</p>}
        <div className="button-group"><span role="status">{validIds.length} selected</span>
          <button type="button" className="primary-button" disabled={disabled || loading || !validIds.length}
            onClick={() => {
              const chosen = changePoMode(validIds, mode);
              // Keep the chosen orders themselves so the cutting plan uses exactly what was confirmed.
              onChange({ mode, modelId, ids: chosen, orders: orders.filter(po => chosen.includes(po.id)) });
              setEditing(false);
            }}>OK</button></div>
      </>}
    </>}
    <h3 className="selection-subheading">Selected purchase orders</h3>
    {saved.length ? <><p>{value.mode === 'single' ? 'Individual PO' : 'Multiple POs'} · {saved.length} selected</p>
      <div className="table-scroll"><table><thead><tr><th>Contract no.</th><th>Tech Pack ID</th><th>Model ID</th><th>Quality ID</th><th>Color ID</th><th>Total quantity</th><th>Size</th><th>Quantity</th></tr></thead>
        <tbody>{saved.map(po => <tr key={po.id}><td><strong>{po.contract_number || '—'}</strong></td><td>{po.tech_pack_reference}</td>
          <td>{po.model_id || '—'}</td><td>{po.quality_id || '—'}</td><td>{po.color_id || '—'}</td><td>{po.total_quantity || '—'}</td><PoSizeCells order={po}/></tr>)}</tbody></table></div></>
      : <p>No purchase orders selected.</p>}
  </section>;
}
