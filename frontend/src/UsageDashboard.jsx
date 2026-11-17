import React, { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { usageApi } from './api.js';
import AppShell from './AppShell.jsx';
import { METRICS, RANGES, STATUS_LABELS, barHeights, formatCost, formatCount, formatPercent } from './usage.js';

/**
 * Purpose: The Usage dashboard, a separate page showing model token use, cost, daily totals and failure
 * rates for the last 7, 30 or 90 days, based on the usage stored with each extraction.
 * Input: user - the signed-in person; onSignOut - called by the Sign out button.
 * Output: the page: top bar, summary tiles, a daily chart, failures by result and step, and the documents
 * with the most failed requests.
 */
export default function UsageDashboard({ user, onSignOut }) {
  const [days, setDays] = useState(30);
  const [metric, setMetric] = useState('total_tokens');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [people, setPeople] = useState(null);
  const [peopleError, setPeopleError] = useState('');

  /** Purpose: Load the figures for the chosen range. Input: none. Output: a promise; a failure shows a message and keeps the old figures. */
  async function load() {
    try {
      setData(await usageApi.summary(days));
      setError('');
    } catch (e) { setError(e.message); }
    if (!user?.is_admin) return;
    try {
      setPeople((await usageApi.users(days)).users);
      setPeopleError('');
    } catch (e) { setPeopleError(e.message); }
  }
  useEffect(() => { load(); }, [days]);

  const totals = data?.totals;
  const bars = data ? barHeights(data.daily, metric) : [];
  const formatMetric = value => metric === 'cost_usd' ? formatCost(value, totals?.cost_estimated) : formatCount(value);
  const failedStatuses = data?.by_status.filter(item => item.status !== 'success') || [];
  const maxFailed = Math.max(1, ...failedStatuses.map(item => item.count));

  return <AppShell user={user} onSignOut={onSignOut} active="usage" title="Model usage"
    actions={<div className="vp-segmented" role="group" aria-label="Date range">
      {RANGES.map(range => <button key={range} type="button" aria-pressed={range === days} onClick={() => setDays(range)}>{range} days</button>)}
    </div>}>
    <main className="workspace plies-workspace">
      {error && <div className="alert error" role="alert"><AlertTriangle size={18}/><span>Could not load usage: {error}</span><button onClick={load}>Retry</button></div>}
      {!data && !error && <div className="loading-workspace" role="status"><span className="spinner"/> Loading usage…</div>}

      {data && <>
        <div className="usage-stats" aria-label="Summary">
          <div><strong>{formatCount(totals.documents)}</strong><span>Uploads</span></div>
          <div><strong>{formatCount(totals.total_tokens)}</strong><span>Tokens ({formatCount(totals.input_tokens)} in · {formatCount(totals.output_tokens)} out)</span></div>
          <div><strong>{formatCost(totals.cost_usd, totals.cost_estimated)}</strong><span>{totals.cost_estimated ? 'Estimated cost' : 'Cost'}</span></div>
          <div className={totals.failure_rate > 0.1 ? 'usage-warn' : undefined}><strong>{formatPercent(totals.failure_rate)}</strong><span>Failed requests ({formatCount(totals.failed_requests)} of {formatCount(totals.requests)})</span></div>
          <div><strong>{formatCount(totals.retries)}</strong><span>Retries</span></div>
          <div><strong>{formatCount(totals.failed_documents)}</strong><span>Uploads that failed</span></div>
        </div>

        <section className="panel usage-panel">
          <div className="panel-heading"><div><h2>Daily totals</h2><p>By upload date. Each bar is one day.</p></div>
            <select aria-label="Chart metric" value={metric} onChange={event => setMetric(event.target.value)}>
              {METRICS.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}
            </select></div>
          <div className="usage-bars" role="img" aria-label={`Daily ${METRICS.find(item => item.key === metric).label.toLowerCase()}`}>
            {bars.map(bar => <div key={bar.date} className="usage-bar" title={`${bar.date}: ${formatMetric(bar.value)}`}>
              <span style={{ height: `${bar.height}%` }} /></div>)}
          </div>
          <div className="usage-axis"><span>{data.daily[0].date}</span><span>{data.daily[data.daily.length - 1].date}</span></div>
        </section>

        {user?.is_admin && <section className="panel usage-panel" aria-label="Usage by user">
          <div className="panel-heading"><div><h2>Usage by user</h2><p>Tokens and cost for the uploads each person made. Visible to admins only.</p></div></div>
          {peopleError && <div className="alert error" role="alert"><AlertTriangle size={18}/><span>Could not load usage by user: {peopleError}</span><button onClick={load}>Retry</button></div>}
          {!people && !peopleError && <div className="loading-workspace" role="status"><span className="spinner"/> Loading…</div>}
          {people && (!people.length ? <p className="plies-empty">No uploads in this period.</p> :
            <div className="table-scroll"><table className="plies-table"><thead><tr><th>User</th><th>Uploads</th><th>Requests</th><th>Failed</th><th>Input tokens</th><th>Output tokens</th><th>Total tokens</th><th>Cost</th></tr></thead>
              <tbody>{people.map(person => <tr key={person.user_id || 'unassigned'}>
                <td><strong>{person.name}</strong><br/><small>{person.email}</small></td>
                <td>{formatCount(person.documents)}</td><td>{formatCount(person.requests)}</td><td>{formatCount(person.failed_requests)}</td>
                <td>{formatCount(person.input_tokens)}</td><td>{formatCount(person.output_tokens)}</td><td>{formatCount(person.total_tokens)}</td>
                <td>{formatCost(person.cost_usd, person.cost_estimated)}</td></tr>)}</tbody></table></div>)}
        </section>}

        <div className="usage-columns">
          <section className="panel usage-panel">
            <div className="panel-heading"><div><h2>Failures by result</h2><p>Requests that did not complete.</p></div></div>
            {!failedStatuses.length ? <p className="plies-empty">No failed requests in this period.</p> :
              <ul className="usage-list">{failedStatuses.map(item => <li key={item.status}>
                <span>{STATUS_LABELS[item.status] || item.status}</span>
                <span className="usage-meter"><i style={{ width: `${item.count / maxFailed * 100}%` }} /></span>
                <b>{formatCount(item.count)}</b></li>)}</ul>}
          </section>
          <section className="panel usage-panel">
            <div className="panel-heading"><div><h2>By step</h2><p>Where requests and failures happen.</p></div></div>
            {!data.by_stage.length ? <p className="plies-empty">No requests in this period.</p> :
              <div className="table-scroll"><table><thead><tr><th>Step</th><th>Requests</th><th>Failed</th><th>Tokens</th></tr></thead>
                <tbody>{data.by_stage.map(stage => <tr key={stage.stage}><td>{stage.stage}</td><td>{formatCount(stage.requests)}</td>
                  <td>{formatCount(stage.failed_requests)}</td><td>{formatCount(stage.total_tokens)}</td></tr>)}</tbody></table></div>}
          </section>
        </div>

        <section className="panel usage-panel">
          <div className="panel-heading"><div><h2>Uploads with the most failed requests</h2><p>Usage stays here after a document is deleted, marked (deleted).</p></div></div>
          {!data.worst_documents.length ? <p className="plies-empty">No uploads had failed requests in this period.</p> :
            <div className="table-scroll"><table className="plies-table"><thead><tr><th>Type</th><th>File</th><th>Status</th><th>Requests</th><th>Failed</th><th>Tokens</th></tr></thead>
              <tbody>{data.worst_documents.map(item => <tr key={`${item.kind}-${item.id}`}>
                <td>{item.kind === 'po' ? 'Purchase order' : 'Tech Pack'}</td><td><strong>{item.filename}</strong>{item.deleted && <small className="usage-deleted"> (deleted)</small>}</td><td>{item.status}</td>
                <td>{formatCount(item.requests)}</td><td>{formatCount(item.failed_requests)}</td><td>{formatCount(item.total_tokens)}</td></tr>)}</tbody></table></div>}
        </section>
        {totals.cost_usd === null && <p className="usage-note">Cost is unavailable because these extractions did not record it. New uploads record OpenRouter's charge automatically, or set LLM_PRICE_INPUT_PER_MTOK and LLM_PRICE_OUTPUT_PER_MTOK to estimate it.</p>}
      </>}
    </main>
  </AppShell>;
}
