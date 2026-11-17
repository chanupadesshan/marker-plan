import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, Scissors } from 'lucide-react';
import { markerPlanApi, openFile } from './api';
import { markerMaterialRows } from './marker-materials.js';
import { quantityText } from './WovensTable.jsx';
import VerifiedNestingEditor from './VerifiedNestingEditor.jsx';
import { nestingSizes } from './nesting.js';
import { DEFAULT_PLAN_SETTINGS, LENGTH_UNITS, buildPlanRequest, capacityPreview, defaultMaterialSettings, hasPlan,
  isPlanRunning, phaseText, planFormErrors, planOutcome, plyChoices, plySourceText, solveTimeText } from './marker-plan.js';

const POLL_MS = 1000;

/** Purpose: One labelled form field with its error. Input: label, hint, error, children (the control). Output: the field. */
function Field({ label, hint, error, children }) {
  return <label className="ply-field plan-field">{label}{children}
    {hint && !error && <small>{hint}</small>}{error && <em className="field-error">{error}</em>}</label>;
}

/** Purpose: Size-count cells of a marker or lay, one per size. Input: counts. Output: table cells. */
function CountCells({ counts }) {
  return counts.map((count, index) => <td key={index} className={`plan-count${count ? '' : ' zero'}`}>{count || '—'}</td>);
}

/**
 * Purpose: Live progress of a material that is still being solved.
 * Input: entry - the material's job entry (state and live progress); timeLimit - its search time in seconds.
 * Output: a status line.
 */
function MaterialProgress({ entry, timeLimit }) {
  if (entry.state === 'queued') return <p className="plan-progress" role="status">Waiting for the previous material to finish.</p>;
  const live = entry.live;
  return <p className="plan-progress" role="status"><span className="spinner"/>
    <span><strong>{phaseText(live?.phase)}</strong>
      {live?.marker_count != null && <> · best so far {live.marker_count} markers, {live.lay_count} lays</>}
      {' '}· {(live?.elapsed_seconds ?? 0).toFixed(1)} s of up to {timeLimit} s</span></p>;
}

/**
 * Purpose: One material's finished plan: outcome and proofs, unique markers with their lays, the lay
 * sequence in cutting order, and required versus produced quantity per size.
 * Input: entry - the material's job entry; sizes - size labels in order; timeLimit - search time in seconds.
 * Output: the material's plan panel.
 */
function MaterialPlan({ entry, sizes, timeLimit }) {
  const result = entry.result;
  const outcome = result ? planOutcome(result, timeLimit) : null;
  const planned = hasPlan(result);
  return <section className="panel plan-material" aria-label={`Cutting plan for ${entry.material_code || 'material'}`}>
    <div className="panel-heading"><div>
      <span className="eyebrow">MATERIAL {entry.marker_prefix.replace('-', '')}{entry.page_number ? ` · PAGE ${entry.page_number}` : ''}</span>
      <h3>{entry.material_code || 'Unnamed material'}{entry.description && <small>{entry.description}</small>}</h3></div>
      <span className="plan-result-status">{outcome ? outcome.label : entry.state === 'queued' ? 'Queued' : 'Solving'}</span>
    </div>
    <div className="document-facts plan-facts">
      <span>Capacity {entry.capacity} sets per marker{entry.capacity_basis === 'verified_nesting' ? ' (verified combinations only)' : ' (estimated)'}</span>
      <span>Consumption {entry.consumption} {entry.unit}{entry.unit !== 'm' ? ` (${entry.consumption_m} m)` : ''}</span>
      <span>Max {entry.max_plies} plies per lay</span>
      {result && planned && <><span>{result.marker_count} unique markers{Number.isInteger(result.marker_lower_bound) ? ` (lower bound ${result.marker_lower_bound})` : ''}</span>
        <span>{result.lay_count} lays</span></>}
      {result && result.status !== 'INVALID_INPUT' && <span>Solved in {solveTimeText(result.elapsed_seconds)}</span>}
    </div>
    {!result ? <MaterialProgress entry={entry} timeLimit={timeLimit}/> : <>
      {!planned && <p className="plan-message" role="alert">{result.message || outcome.lines.join(' ')}</p>}
      <details className="plan-details"><summary>Plan details<ChevronDown size={15}/></summary>
        {result.optimization_scope === 'verified_nesting_catalogue' && <p>Optimality applies only to the supplied verified nesting combinations.</p>}
        {outcome.lines.map((line, index) => <p key={index}>{line}</p>)}
        {planned && result.one_marker_shortcut && <p className="plan-shortcut">Worked out directly, without a search: the order's
          size ratio fits on one marker, so the plan follows from the quantities. That is why it finished almost instantly.</p>}
        {result.message && result.status !== 'INVALID_INPUT' && result.status !== 'ERROR' && <p className="plan-solver-note">Solver: {result.message}</p>}
        {planned && <p>Checked by the independent validator: exact quantity for every size, capacity, ply limits, non-increasing plies and the final-lay rule.</p>}
      </details>
      {planned && <>
        <h4 className="selection-subheading">Unique markers</h4>
        <div className="table-scroll plan-table"><table><thead><tr><th>Marker</th>{sizes.map(size => <th key={size}>{size}</th>)}
          <th>Sets per marker</th>{entry.capacity_basis === 'verified_nesting' && <th>Verified length (m)</th>}<th>Lays (plies)</th><th>Total plies</th><th>Sets cut</th></tr></thead>
          <tbody>{result.markers.map(marker => <tr key={marker.id}><td><strong>{marker.id}</strong></td><CountCells counts={marker.counts}/>
            <td>{marker.sets_per_marker}</td>
            {entry.capacity_basis === 'verified_nesting' && <td>{marker.length_m || '—'}</td>}
            <td className="nowrap">{marker.lay_numbers.map(number => <div key={number}>Lay {number}: {result.lays[number - 1].plies}</div>)}</td>
            <td>{marker.total_plies}</td><td>{marker.sets_cut}</td></tr>)}</tbody></table></div>
        <details className="plan-lays">
          <summary>Lay sequence in cutting order ({result.lay_count} lays)<ChevronDown size={15}/></summary>
          <div className="table-scroll plan-table"><table><thead><tr><th>Lay</th><th>Marker</th>{sizes.map(size => <th key={size}>{size}</th>)}<th>Plies</th><th>Sets cut</th></tr></thead>
            <tbody>{result.lays.map(lay => <tr key={lay.number}><td>{lay.number}</td><td><strong>{lay.marker_id}</strong></td><CountCells counts={lay.counts}/>
              <td>{lay.plies}</td><td>{lay.sets}</td></tr>)}</tbody></table></div>
        </details>
        <h4 className="selection-subheading">Required and produced quantities</h4>
        <div className="table-scroll plan-table"><table className="plan-production"><thead><tr><th>Size</th>{result.production.map(row => <th key={row.size}>{row.size}</th>)}<th>Total</th></tr></thead>
          <tbody>
            <tr><td><strong>Required</strong></td>{result.production.map(row => <td key={row.size}>{row.required}</td>)}<td>{result.production.reduce((sum, row) => sum + row.required, 0)}</td></tr>
            <tr><td><strong>Produced</strong></td>{result.production.map(row => <td key={row.size}>{row.produced}</td>)}<td>{result.production.reduce((sum, row) => sum + row.produced, 0)}</td></tr>
            <tr><td><strong>Difference</strong></td>{result.production.map(row => <td key={row.size} className={row.difference ? 'plan-mismatch' : 'plan-exact'}>{row.difference || 'Exact'}</td>)}<td/></tr>
          </tbody></table></div>
      </>}
    </>}
  </section>;
}

/**
 * Purpose: Step 4 of the Marker Plan: cutting settings for the chosen materials, then a cutting plan per material
 * (unique marker size combinations and lays) that produces every PO size quantity exactly. Solving runs on the
 * server; this view polls for progress so the page stays usable.
 * Input: props - extraction and plyInfo (the Tech Pack), materialKeys (chosen BOM rows), orders (chosen POs),
 * value ({ settings, job, signature }) and onChange (called with an updater function), disabled.
 * Output: the cutting-plan panels.
 */
export default function MarkerCuttingPlan({ extraction, plyInfo, materialKeys = [], orders = [], source = {}, value, onChange, disabled = false }) {
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const settings = value?.settings || DEFAULT_PLAN_SETTINGS;
  const entries = markerMaterialRows(extraction).filter(entry => materialKeys.includes(entry.key))
    .map(entry => ({ ...entry, plies: plyInfo?.[entry.row.material_code], plyChoices: plyChoices(plyInfo?.[entry.row.material_code]),
      settings: settings.materials?.[entry.key] || defaultMaterialSettings(entry.row, plyInfo) }));
  const errors = planFormErrors(settings, entries, nestingSizes(orders));
  const request = errors.count || !orders.length ? null : buildPlanRequest(orders, entries, settings, source);
  const signature = request ? JSON.stringify(request) : null;
  const job = value?.job;
  const running = isPlanRunning(job);
  const stale = Boolean(job) && !running && value?.signature !== signature;
  const timeLimit = Number(settings.time_limit_seconds) || 0;

  useEffect(() => {
    if (!job?.id || !running) return undefined;
    let cancelled = false, handle;
    // Wait for each answer before asking again, so slow responses never pile up.
    const poll = async () => {
      try {
        const next = await markerPlanApi.get(job.id);
        if (cancelled) return;
        onChangeRef.current(previous => previous?.job?.id === next.id ? { ...previous, job: next } : previous);
      } catch (e) {
        if (cancelled) return;
        if (/not found/i.test(e.message)) {
          setError('This cutting plan was not found in saved history. Generate the plan again.');
          onChangeRef.current(previous => previous?.job?.id === job.id ? { ...previous, job: null } : previous);
          return;
        }
        setError(`Could not refresh the cutting plan: ${e.message}. Retrying…`);
      }
      if (!cancelled) handle = setTimeout(poll, POLL_MS);
    };
    handle = setTimeout(poll, POLL_MS);
    return () => { cancelled = true; clearTimeout(handle); };
  }, [job?.id, running]);

  /** Purpose: Change order-level settings. Input: changes. Output: nothing. */
  function update(changes) {
    onChange(previous => ({ ...previous, settings: { ...DEFAULT_PLAN_SETTINGS, ...previous?.settings, ...changes } }));
  }

  /** Purpose: Change one material's settings. Input: entry - the material; changes. Output: nothing. */
  function updateMaterial(entry, changes) {
    onChange(previous => {
      const current = { ...DEFAULT_PLAN_SETTINGS, ...previous?.settings };
      return { ...previous, settings: { ...current, materials: { ...current.materials, [entry.key]: { ...entry.settings, ...changes } } } };
    });
  }

  /** Purpose: Send the plan request and keep the queued job. Input: none. Output: a promise. */
  async function generate() {
    setError(''); setStarting(true);
    try {
      const created = await markerPlanApi.create(request);
      onChange(previous => ({ ...previous, job: created, signature }));
    } catch (e) { setError(`The cutting plan could not be started: ${e.message}`); }
    finally { setStarting(false); }
  }

  const locked = disabled || running || starting;
  return <>
    <section className="panel marker-material-summary plan-settings" aria-label="Cutting plan settings">
      <div className="panel-heading"><div><span className="eyebrow">CUTTING PLAN</span><h2>Cutting settings</h2></div>
        <span>{entries.length} materials · {orders.length} purchase orders</span></div>
      <p>Each material is planned separately: marker size combinations and lay plies that cut every PO size exactly,
        using as few unique markers as the search can establish, then as few lays. Pattern nesting, marker length and
        fabric use are not calculated here; Lectra nests the pieces afterwards.</p>
      <div className="plan-form-row">
        <Field label="Usable table length (m)" hint="Capacity = table length ÷ consumption, rounded down." error={errors.form.table_length_m}>
          <input inputMode="decimal" value={settings.table_length_m} disabled={locked} aria-invalid={Boolean(errors.form.table_length_m)}
            placeholder="e.g. 8" onChange={event => update({ table_length_m: event.target.value })}/></Field>
        <Field label="Normal minimum plies" hint="Only the final lay may have fewer." error={errors.form.min_plies}>
          <input inputMode="numeric" value={settings.min_plies} disabled={locked} aria-invalid={Boolean(errors.form.min_plies)}
            onChange={event => update({ min_plies: event.target.value })}/></Field>
        <Field label="Search time per material (s)" hint="60–300 seconds." error={errors.form.time_limit_seconds}>
          <input inputMode="numeric" value={settings.time_limit_seconds} disabled={locked} aria-invalid={Boolean(errors.form.time_limit_seconds)}
            onChange={event => update({ time_limit_seconds: event.target.value })}/></Field>
      </div>
      <div className="table-scroll plan-table"><table><thead><tr><th>Material</th><th>Placement</th><th>BOM qty</th>
        <th>Consumption per garment</th><th>Max plies per lay</th><th>Capacity (sets per marker)</th></tr></thead>
        <tbody>{entries.map(entry => {
          const problems = errors.materials[entry.key] || {};
          const capacity = entry.settings.nesting_markers?.length ? Math.max(...entry.settings.nesting_markers.map(marker => marker.size_rows.reduce((sum,row) => sum + Number(row.quantity || 0), 0))) : capacityPreview(settings.table_length_m, entry.settings.consumption, entry.settings.unit);
          const source = plySourceText(entry.plies);
          // A range (or several different values) in the plies table must be chosen by the user, never guessed.
          const listed = entry.plyChoices.length > 1 && !entry.settings.custom_max_plies;
          const name = entry.row.material_code || 'material';
          return <tr key={entry.key}>
            <td><strong>{entry.row.material_code || '—'}</strong><small>{entry.row.description || ''}{entry.pageNumber ? ` · page ${entry.pageNumber}` : ''}</small></td>
            <td>{entry.row.placement || '—'}</td>
            <td className="nowrap">{quantityText(entry.row)}</td>
            <td><div className="plan-inline-inputs">
              <input aria-label={`Consumption per garment for ${entry.row.material_code || 'material'}`} inputMode="decimal" value={entry.settings.consumption}
                disabled={locked} aria-invalid={Boolean(problems.consumption)} onChange={event => updateMaterial(entry, { consumption: event.target.value })}/>
              <select aria-label={`Consumption unit for ${entry.row.material_code || 'material'}`} value={entry.settings.unit} disabled={locked}
                onChange={event => updateMaterial(entry, { unit: event.target.value })}>{LENGTH_UNITS.map(unit => <option key={unit} value={unit}>{unit}</option>)}</select>
            </div>{problems.consumption && <em className="field-error">{problems.consumption}</em>}</td>
            <td>{listed
              ? <select aria-label={`Choose maximum plies for ${name}`} value={entry.settings.max_plies} disabled={locked}
                  aria-invalid={Boolean(problems.max_plies)} onChange={event => updateMaterial(entry, event.target.value === 'other'
                    ? { custom_max_plies: true, max_plies: '' } : { max_plies: event.target.value })}>
                  <option value="">Choose…</option>
                  {entry.plyChoices.map(value => <option key={value} value={String(value)}>{value}</option>)}
                  <option value="other">Other value…</option>
                </select>
              : <input aria-label={`Maximum plies for ${name}`} inputMode="numeric" value={entry.settings.max_plies}
                  disabled={locked} aria-invalid={Boolean(problems.max_plies)} onChange={event => updateMaterial(entry, { max_plies: event.target.value })}/>}
              {problems.max_plies ? <em className="field-error">{problems.max_plies}</em>
                : <small className={listed ? 'plan-ply-range' : undefined}>{!source ? 'Not in the plies table'
                  : listed ? `Range: ${source}` : `Plies table: ${source}`}</small>}
              {entry.plyChoices.length > 1 && entry.settings.custom_max_plies && <button type="button" className="plan-link-button" disabled={locked}
                onClick={() => updateMaterial(entry, { custom_max_plies: false, max_plies: '' })}>Choose from the plies table</button>}</td>
            <td><strong>{capacity ?? '—'}</strong></td>
          </tr>;
        })}</tbody></table></div>
      {entries.map(entry => <VerifiedNestingEditor key={entry.key} materialLabel={`${entry.row.material_code || 'Material'} · ${entry.row.placement || entry.pageNumber || ''}`}
        value={entry.settings.nesting_markers || []} sizes={nestingSizes(orders)} tableLength={settings.table_length_m} disabled={locked}
        onChange={nesting_markers => updateMaterial(entry, { nesting_markers })}/>)}
      {error && <p className="plan-message" role="alert">{error} <button type="button" className="plan-link-button" onClick={() => setError('')}>Dismiss</button></p>}
      <div className="button-group plan-actions">
        <span role="status">{errors.count > errors.pendingChoices.length ? 'Complete the highlighted settings to generate a plan.'
          : errors.pendingChoices.length ? `Choose the maximum plies for ${errors.pendingChoices.length} material${errors.pendingChoices.length === 1 ? '' : 's'} with a plies range to generate a plan.`
          : `Up to ${timeLimit} s per material, about ${timeLimit * entries.length} s in total.`}</span>
        <button type="button" className="primary-button" disabled={locked || !request} onClick={generate}>
          <Scissors size={15}/>{running ? 'Generating…' : job ? 'Generate again' : 'Generate cutting plan'}</button>
      </div>
    </section>

    {job && <MarkerPlanResults job={job} stale={stale}/>}
  </>;
}

/** Shared read-only results for a new generation or a reopened database snapshot. */
export function MarkerPlanResults({ job, stale = false }) {
  const running = isPlanRunning(job);
  const finished = job && !running ? job.summary : null;
  const solvingNumber = Math.min(job.materials.filter(entry => entry.result).length + 1, job.materials.length);
  const download = !running && finished?.complete && job.saved && !stale;
  return <section className="plan-results" aria-label="Cutting plan results">
      <div className="results-heading"><div><span className="eyebrow">CUTTING PLAN</span><h2>Markers and lays</h2></div>
        <div className="result-counts"><span>{job.total_quantity} garments</span><span>{job.sizes.length} sizes</span><span>{job.materials.length} materials</span></div></div>
      <div className="saved-plan-actions">
        {job.saved && !running && <span className="plan-result-status">Saved to database</span>}
        {download && <a className="primary-button" href={`/api/marker-plans/${job.id}/excel`}
          onClick={event => openFile(event, `/api/marker-plans/${job.id}/excel`, `marker-plan-${job.id}.xlsx`)}>Download Excel</a>}
      </div>
      {job.persistence_error && <p className="plan-message" role="alert">{job.persistence_error}</p>}
      {stale && <p className="plan-message" role="status">The settings or selections have changed since this plan was generated. Generate it again to use them.</p>}
      {running ? <div className="plan-message plan-running" role="status"><span className="spinner"/>
        <span>Solving material {solvingNumber} of {job.materials.length}. You can keep working; results appear here as each material finishes.</span></div>
        : finished && (finished.complete
          ? <p className="plan-message" role="status">Every material has a validated plan: {finished.marker_count} unique markers and {finished.lay_count} lays in total across materials.</p>
          : <p className="plan-message" role="alert">{finished.failed} of {job.materials.length} materials have no plan. Check the messages below; the other materials' plans are still valid.</p>)}
      {!!job.warnings?.length && <details className="plan-details">
        <summary>{job.warnings.length} note{job.warnings.length === 1 ? '' : 's'} about the PO quantities<ChevronDown size={15}/></summary>
        <ul>{job.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
      {job.materials.map(entry => <MaterialPlan key={entry.number} entry={entry} sizes={job.sizes} timeLimit={job.settings.time_limit_seconds}/>)}
      <p className="plan-message">Quantities and ply rules are checked in software. Confirm consumption, ply limits and nesting with the cutting team.</p>
    </section>;
}
