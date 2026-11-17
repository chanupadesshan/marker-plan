import React, { useEffect, useState } from 'react';
import { markerPlanApi, openFile } from './api';
import { savedPlanPath } from './plan-navigation.js';
import { DeleteSavedPlan } from './SavedPlanControls.jsx';

const PAGE_SIZE = 50;
const dateLabel = value => value ? new Date(value).toLocaleString() : '—';

/** Saved history is available without reselecting BOM rows or purchase orders. */
export default function SavedMarkerPlans({ refreshKey, canEdit = false }) {
  const [plans, setPlans] = useState([]);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const active = plans.some(plan => ['queued', 'running'].includes(plan.status));
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    markerPlanApi.list(PAGE_SIZE, offset).then(rows => {
      if (!cancelled) { setPlans(rows); setError(''); }
    }).catch(e => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [offset, revision, refreshKey]);
  useEffect(() => {
    if (!active) return undefined;
    const handle = setTimeout(() => setRevision(value => value + 1), 3000);
    return () => clearTimeout(handle);
  }, [active, plans]);
  return <section className="saved-plans" aria-label="Saved marker plans">
    <div className="panel">
      <div className="panel-heading"><div><span className="eyebrow">PLAN HISTORY</span><h2>Saved plans</h2></div>
        <button type="button" className="secondary-button" aria-label="Refresh saved plans" disabled={loading}
          onClick={() => setRevision(value => value + 1)}>Refresh</button></div>
      <p>Each generation is saved separately. Open a previous plan or download its Excel workbook.</p>
      {error && <p className="field-error" role="alert">{error}</p>}
      {loading && <p role="status">Loading saved plans…</p>}
      {!!plans.length && <div className="table-scroll"><table><thead><tr><th>Generated</th><th>PO contracts</th><th>Tech Pack</th><th>Garments</th><th>Materials</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>{plans.map(plan => {
          const ready = plan.status === 'complete' && plan.summary?.complete && plan.saved;
          return <tr key={plan.id}>
            <td className="nowrap">{dateLabel(plan.created_at)}</td><td>{plan.order_labels?.filter(Boolean).join(', ') || '—'}</td>
            <td>{plan.tech_pack_filename || 'Selected BOM'}</td><td>{plan.total_quantity}</td><td>{plan.material_count}</td>
            <td>{plan.status === 'complete' ? ready ? 'Ready' : 'Incomplete' : plan.status}</td>
            <td><SavedPlanActions plan={plan} canEdit={canEdit} onDeleted={() => {
              if (plans.length === 1 && offset > 0) setOffset(value => Math.max(0, value - PAGE_SIZE));
              else setRevision(value => value + 1);
            }}/></td>
          </tr>;
        })}</tbody></table></div>}
      {!loading && !plans.length && !error && <p>No saved plans yet. Create one from a style's Marker plan stage once its Tech Pack and purchase order are approved.</p>}
      <div className="button-group saved-plan-paging">
        <button type="button" className="secondary-button" disabled={loading || offset === 0} onClick={() => setOffset(value => Math.max(0, value - PAGE_SIZE))}>Previous</button>
        <span>Page {offset / PAGE_SIZE + 1}</span>
        <button type="button" className="secondary-button" disabled={loading || plans.length < PAGE_SIZE} onClick={() => setOffset(value => value + PAGE_SIZE)}>Next</button>
      </div>
    </div>
  </section>;
}

/** Open uses normal page navigation so refresh and browser history work naturally. */
export function SavedPlanActions({ plan, canEdit = false, onDeleted }) {
  const ready = plan.status === 'complete' && plan.summary?.complete && plan.saved;
  return <div className="button-group"><a className="secondary-button" href={savedPlanPath(plan.id)}>Open</a>
    {canEdit && <>{['queued', 'running'].includes(plan.status) ? <button className="secondary-button" disabled>Run again</button>
      : <a className="secondary-button" href={`${savedPlanPath(plan.id)}?rerun=1`}>Run again</a>}
      <DeleteSavedPlan plan={plan} onDeleted={onDeleted}/></>}
    {ready && <a className="secondary-button" href={`/api/marker-plans/${plan.id}/excel`}
      onClick={event => openFile(event, `/api/marker-plans/${plan.id}/excel`, `marker-plan-${plan.id}.xlsx`)}>Download Excel</a>}
  </div>;
}
