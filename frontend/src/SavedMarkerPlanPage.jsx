import React, { useEffect, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { markerPlanApi } from './api.js';
import AppShell from './AppShell.jsx';
import { MarkerPlanResults } from './MarkerCuttingPlan.jsx';
import { markerPlanReturnPath } from './plan-navigation.js';
import { can } from './permissions.js';
import { DeleteSavedPlan, RerunSavedPlan } from './SavedPlanControls.jsx';

/** Open a saved snapshot independently of the material selection and history workspace. */
export default function SavedMarkerPlanPage({ id, user, onSignOut }) {
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [rerun, setRerun] = useState(() => typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('rerun') === '1');
  const canEdit = can(user, 'marker_plan', 'edit');
  useEffect(() => {
    let cancelled = false, timer;
    setJob(null); setError(''); setLoading(true);
    async function load() {
      try {
        const next = await markerPlanApi.get(id);
        if (cancelled) return;
        setJob(next); setError(''); setLoading(false);
        if (['queued', 'running'].includes(next.status)) timer = setTimeout(load, 3000);
      } catch (failure) {
        if (!cancelled) { setError(failure.message); setLoading(false); }
      }
    }
    load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [id, revision]);
  return <AppShell user={user} onSignOut={onSignOut} active="plan" title="Saved marker plan">
    <main className="workspace saved-plan-page-content">
      <a className="secondary-button saved-plan-back" href={markerPlanReturnPath}><ArrowLeft size={16}/>Back to Marker Plan</a>
      <div className="workspace-heading"><div><div className="breadcrumb">Marker Plan <span>/</span> Saved plan</div>
        <h2>{job?.order_labels?.filter(Boolean).join(', ') || 'Saved marker plan'}</h2>
        {job?.created_at && <p>Generated {new Date(job.created_at).toLocaleString()}</p>}</div></div>
      {loading && <p role="status"><span className="spinner"/> Loading saved plan…</p>}
      {error && <section className="panel saved-plan-load-error" role="alert"><p>Could not load the saved plan: {error}</p>
        <button type="button" className="secondary-button" onClick={() => setRevision(value => value + 1)}>Try again</button></section>}
      {job && canEdit && <div className="button-group saved-plan-management">
        {!rerun && <button className="secondary-button" disabled={['queued', 'running'].includes(job.status)} onClick={() => setRerun(true)}>Run again</button>}
        <DeleteSavedPlan plan={job} onDeleted={() => window.location.assign(markerPlanReturnPath)}/>
      </div>}
      {job && canEdit && rerun && <RerunSavedPlan id={id} onCancel={() => {
        setRerun(false); window.history.replaceState(null, '', window.location.pathname);
      }}/>}
      {job && <MarkerPlanResults job={job}/>}
    </main>
  </AppShell>;
}
