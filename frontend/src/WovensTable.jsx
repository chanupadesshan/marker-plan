import React from 'react';

function quantityText(row) {
  const value = String(row.quantity ?? '').trim();
  const unit = (row.unit || '').trim();
  if (!value) return '—';
  return unit && !value.toLowerCase().endsWith(unit.toLowerCase()) ? `${value} ${unit}` : value;
}

function PageTable({ table }) {
  const rows = table.materials || [];
  const headers = new Map();
  for (const header of table.colorway_headers || []) {
    headers.set(header.code || '', header);
  }
  for (const row of rows) for (const variant of row.colorways || []) {
    const key = variant.code || '';
    if (!headers.has(key)) headers.set(key, { code: variant.code, name: variant.name });
  }
  return <section className="panel wovens-panel">
    <div className="panel-heading"><div className="table-title"><span className="page-label">{table.page_number ? `PAGE ${table.page_number}` : 'WOVENS'}</span>
      <h3>Material breakdown</h3></div><span className="row-count">{rows.length} material rows</span></div>
    <div className="table-scroll" role="region" aria-label={`Wovens table${table.page_number ? ` page ${table.page_number}` : ''}`} tabIndex={0}><table className="wovens-table">
      <thead><tr><th>Material code</th><th>Description</th><th>Composition</th><th>Placement type / Placement</th><th>Qty</th>
        {[...headers].map(([key, header]) => <th key={key} className="colorway-heading">
          {header.code || 'Unassigned colorway'}{header.name && <small>{header.name}</small>}
        </th>)}
      </tr></thead>
      <tbody>{rows.map((row, index) => {
        const references = [...new Set((row.colorways || []).map(v => v.fabric_reference).filter(Boolean))];
        return <tr key={index}>
          <td><strong>{row.material_code || '—'}</strong></td>
          <td>{row.description || '—'}</td><td>{row.composition || '—'}</td>
          <td>{references.length > 0 && <div className="placement-reference">{references.join(' / ')}</div>}{row.placement || '—'}</td>
          <td className="nowrap">{quantityText(row)}</td>
          {[...headers.keys()].map(key => <td key={key} className="colorway-cell">
            {(row.colorways || []).filter(v => (v.code || '') === key).map((variant, i) =>
              <div key={i}><strong>{variant.material_color_code || '—'}</strong><small>{variant.material_color_name || ''}</small></div>)}
            {!(row.colorways || []).some(v => (v.code || '') === key) && '—'}
          </td>)}
        </tr>;
      })}</tbody>
    </table></div>
  </section>;
}

export default function WovensTable({ extraction }) {
  // Older results remain readable until they are reprocessed into page tables.
  const tables = extraction.page_tables?.length ? extraction.page_tables : [{ materials: extraction.materials || [] }];
  return <>{tables.map((table, index) => <PageTable key={`${table.page_number}-${index}`} table={table} />)}</>;
}
