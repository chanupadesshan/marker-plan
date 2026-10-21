import React from 'react';

const number = value => typeof value === 'number' ? value.toLocaleString() : 'Unavailable';
const statusText = {
  success: 'Completed', token_limit: 'Token limit reached', empty_result: 'No material rows returned',
  request_error: 'Request failed', invalid_response: 'Invalid response', content_filter: 'Content filtered', error: 'Provider error',
};

export default function TokenUsage({ entries = [] }) {
  const knownTotals = entries.filter(entry => typeof entry.total_tokens === 'number');
  return <section className="panel">
    <div className="panel-heading"><div><h2>Token usage</h2>
      {!entries.length ? <p>Token usage was not recorded for this extraction. New uploads will show request counts here.</p> :
        <p>{entries.length} requests · Reported total: {knownTotals.length ? number(knownTotals.reduce((sum, entry) => sum + entry.total_tokens, 0)) : 'Unavailable'}
          {knownTotals.length < entries.length && ' (some counts unavailable)'}. Output allowance applies to each request.</p>}
    </div></div>
    {entries.length > 0 && <div className="table-scroll"><table>
      <thead><tr><th>PDF page</th><th>Step</th><th>Attempt</th><th>Input tokens</th><th>Output tokens</th><th>Total tokens</th><th>Output allowance</th><th>Completion reason</th><th>Result</th></tr></thead>
      <tbody>{entries.map((entry, index) => <tr key={index}>
        <td>{entry.page ?? '—'}</td><td>{entry.stage || '—'}</td><td>{entry.attempt ?? '—'}</td>
        <td>{number(entry.input_tokens)}</td><td>{number(entry.output_tokens)}</td><td>{number(entry.total_tokens)}</td>
        <td>{number(entry.output_limit)}</td><td>{entry.finish_reason || 'Unavailable'}</td>
        <td>{statusText[entry.status] || 'Unavailable'}</td>
      </tr>)}</tbody>
    </table></div>}
  </section>;
}
