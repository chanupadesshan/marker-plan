import React, { useEffect, useState } from 'react';
import { markerPlanApi } from './api.js';
import { useConfirm } from './useConfirm.jsx';
import { savedPlanPath } from './plan-navigation.js';
import VerifiedNestingEditor from './VerifiedNestingEditor.jsx';
import { nestingErrors, nestingPayload, nestingSizes } from './nesting.js';

export function DeleteSavedPlan({ plan, onDeleted }) {
  const [confirm, dialog] = useConfirm();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const active = ['queued', 'running'].includes(plan.status);
  async function remove() {
    if (!await confirm({ tone: 'danger', title: 'Delete this saved plan?', confirmLabel: 'Delete plan',
      detail: plan.order_labels?.filter(Boolean).join(', '),
      message: 'This permanently removes this saved generation and its Excel download. The Tech Pack, purchase orders and other saved plans are kept.' })) return;
    setBusy(true); setError('');
    try { await markerPlanApi.remove(plan.id); onDeleted?.(); }
    catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  return <>{dialog}<button type="button" className="secondary-button" disabled={busy || active} onClick={remove}>
    {busy ? 'Deleting…' : 'Delete'}</button>{error && <span role="alert" className="field-error">{error}</span>}</>;
}

export function RerunSavedPlan({ id, onCancel }) {
  const [payload, setPayload] = useState(null);
  const [notes, setNotes] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setPayload(null); setError('');
    markerPlanApi.rerunSettings(id).then(data => {
      if (cancelled) return;
      // Plans saved before the 60-second minimum may carry a shorter search time; raise it so the plan can be run again.
      const raised = Number(data.request.time_limit_seconds) < 60;
      setPayload(raised ? { ...data.request, time_limit_seconds: 60 } : data.request);
      setNotes([...(data.notes || []), ...(raised ? ['The search time was raised to 60 seconds, the minimum.'] : [])]);
    }).catch(failure => { if (!cancelled) setError(failure.message); });
    return () => { cancelled = true; };
  }, [id, revision]);
  function change(key, value) { setPayload(previous => ({ ...previous, [key]: value })); setError(''); }
  async function submit(event) {
    event.preventDefault();
    const nestingProblems = payload.materials.flatMap(material => nestingErrors(material.nesting_markers || [], payload.table_length_m, nestingSizes(payload.orders)));
    if (nestingProblems.length) { setError(nestingProblems.join(' ')); return; }
    if (payload.materials.some(material => Number(material.max_plies) < Number(payload.min_plies))) {
      setError('Minimum plies must not exceed any material’s maximum plies.'); return;
    }
    setBusy(true); setError('');
    try {
      const request = { ...payload, min_plies: Number(payload.min_plies), time_limit_seconds: Number(payload.time_limit_seconds),
        materials: payload.materials.map(material => ({ ...material, max_plies: Number(material.max_plies), nesting_markers: nestingPayload(material.nesting_markers || []) })) };
      const next = await markerPlanApi.create(request);
      window.location.assign(savedPlanPath(next.id));
    } catch (failure) { setError(failure.message); setBusy(false); }
  }
  return <section className="panel bom-editor" aria-label="Run saved plan again"><h2>Run again</h2>
    <p>Review the current ply limits below. This creates a new saved plan using the original PO quantities and material consumptions. The previous plan is kept.</p>
    {notes.map((note, index) => <p className="plan-message" key={index}>{note}</p>)}
    {error && <p role="alert" className="field-error">{error}</p>}
    {!payload ? <><p role="status">{error ? 'Settings could not be loaded.' : 'Loading current ply limits…'}</p>
      {error && <button className="secondary-button" onClick={() => setRevision(value => value + 1)}>Try again</button>}
      <button className="secondary-button" onClick={onCancel}>Cancel</button></> : <form onSubmit={submit}><fieldset disabled={busy}>
      <div className="po-edit-fields">{[['table_length_m', 'Table length (m)', '0.001', '1000', 'any'],
        ['min_plies', 'Minimum plies', '1', '1000000', '1'], ['time_limit_seconds', 'Search time per material (seconds)', '60', '300', 'any']].map(([key, label, min, max, step]) =>
        <label key={key}>{label}<input type="number" required min={min} max={max} step={step} value={payload[key]}
          onChange={event => change(key, event.target.value)}/></label>)}</div>
      <div className="table-scroll"><table className="bom-edit-table"><thead><tr><th>Material</th><th>Placement</th><th>Consumption</th><th>Maximum plies</th></tr></thead>
        <tbody>{payload.materials.map((material, index) => <tr key={index}><td>{material.material_code}</td><td>{material.placement || '—'}</td>
          <td>{material.consumption} {material.unit}</td><td><label className="sr-only" htmlFor={`rerun-ply-${index}`}>Maximum plies for material {index + 1}</label>
            <input id={`rerun-ply-${index}`} type="number" min="1" max="1000000" step="1" required value={material.max_plies} onChange={event => {
              setPayload(previous => ({ ...previous, materials: previous.materials.map((row, ri) => ri === index ? { ...row, max_plies: event.target.value } : row) }));
              setError('');
            }}/></td></tr>)}</tbody></table></div>
      {payload.materials.map((material,index) => <VerifiedNestingEditor key={index} materialLabel={`${material.material_code || 'Material'} · ${material.placement || index+1}`}
        value={material.nesting_markers || []} sizes={nestingSizes(payload.orders)} tableLength={payload.table_length_m} disabled={busy}
        onChange={nesting_markers => setPayload(previous => ({ ...previous, materials: previous.materials.map((row,ri) => ri === index ? { ...row, nesting_markers } : row) }))}/>)}
      <div className="bom-editor-actions"><button className="primary-button" type="submit">{busy ? 'Starting…' : 'Generate new plan'}</button>
        <button className="secondary-button" type="button" onClick={onCancel}>Cancel</button></div>
    </fieldset></form>}
  </section>;
}
