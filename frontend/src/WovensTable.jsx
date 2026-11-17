import React from 'react';
import { materialTables, materialRowKey, materialCategory } from './marker-materials.js';

/**
 * Purpose: Format a material's quantity with its unit, without repeating a unit already in the text.
 * Input: row - a material with quantity and unit.
 * Output: text such as '0.95 m', or '—' when there is no quantity.
 */
export function quantityText(row) {
  const value = String(row.quantity ?? '').trim();
  const unit = (row.unit || '').trim();
  if (!value) return '—';
  return unit && !value.toLowerCase().endsWith(unit.toLowerCase()) ? `${value} ${unit}` : value;
}

/**
 * Purpose: Show a material's maximum ply from the plies table, with a note of where it came from.
 * Input: props - info: { max_ply, matches: [{ id, col_c, col_d }] } for this material, or nothing when the
 * plies table has no related row.
 * Output: the maximum (with the related range or the number of entries underneath) or '—' when unknown.
 * Hovering shows every related plies row.
 */
function MaxPly({ info }) {
  if (!info) return <span title="No related row in the plies table">—</span>;
  const title = `From the plies table: ${info.matches.map(match => `#${match.id} ${match.col_c} → ${match.col_d || 'no value'}`).join('; ')}`;
  if (info.max_ply == null) return <span title={title}>—</span>;
  const note = info.matches.length > 1 ? `${info.matches.length} entries`
    : info.matches[0].col_d !== String(info.max_ply) ? info.matches[0].col_d : '';
  return <span title={title}><strong>{info.max_ply}</strong>{note && <small>{note}</small>}</span>;
}

/**
 * Purpose: Show the materials of one PDF page, one row per material and one column per colorway,
 * with each material's maximum ply from the plies table.
 * Input: props - table: { page_number, materials, colorway_headers }; plyInfo: the related plies rows and
 * maximum ply per material code (see MaxPly); category: 'wovens' or 'knits' to show only that section's rows
 * (all rows when omitted).
 * Output: a panel with the material table, or nothing when the page has no row to show.
 */
function PageTable({ table, tableIndex, plyInfo, selection, visibleKeys, category }) {
  const allRows = table.materials || [];
  const shownKeys = visibleKeys || selection?.visibleKeys;
  // Keep source indexes: filtering must not move a checkbox to a different material.
  const entries = allRows.map((row, index) => ({ row, index })).filter(({ row, index }) =>
    (!category || materialCategory(row) === category) && (!shownKeys || shownKeys.has(materialRowKey(table, tableIndex, index))));
  if ((shownKeys || category) && !entries.length) return null;
  const label = (category || 'wovens').toUpperCase();
  const rows = entries.map(entry => entry.row);
  const headers = new Map();
  for (const header of table.colorway_headers || []) {
    headers.set(header.code || '', header);
  }
  for (const row of rows) for (const variant of row.colorways || []) {
    const key = variant.code || '';
    if (!headers.has(key)) headers.set(key, { code: variant.code, name: variant.name });
  }
  return <section className="panel wovens-panel">
    <div className="panel-heading"><div className="table-title"><span className="page-label">{table.page_number ? `PAGE ${table.page_number}` : label}</span>
      <h3>Material breakdown</h3></div><span className="row-count">{rows.length} material rows</span></div>
    <div className="table-scroll" role="region" aria-label={`${label.charAt(0)}${label.slice(1).toLowerCase()} table${table.page_number ? ` page ${table.page_number}` : ''}`} tabIndex={0}><table className="wovens-table">
      <thead><tr>{selection && <th className="marker-select-cell">Use</th>}<th>Material code / Dev No</th><th>Description</th><th>Composition</th><th>Placement type / Placement</th><th>Qty</th><th>Max ply</th>
        {[...headers].map(([key, header]) => <th key={key} className="colorway-heading">
          {header.code || 'Unassigned colorway'}{header.name && <small>{header.name}</small>}
        </th>)}
      </tr></thead>
      <tbody>{entries.map(({ row, index }) => {
        const rowKey = selection ? materialRowKey(table, tableIndex, index) : null;
        return <tr key={index} className={selection?.selectedKeys.has(rowKey) ? 'marker-material-selected' : undefined}>
          {selection && <td className="marker-select-cell"><input type="checkbox" disabled={selection.disabled}
            aria-label={`Select ${row.material_code || 'material'}, ${table.page_number ? `page ${table.page_number}, ` : ''}row ${index + 1}`}
            checked={selection.selectedKeys.has(rowKey)} onChange={event => selection.onToggle(rowKey, event.target.checked)}/></td>}
          <td><strong>{row.material_code || '—'}</strong>{row.developer_code && <div>{row.developer_code}</div>}</td>
          <td>{row.description || '—'}</td><td>{row.composition || '—'}</td>
          <td>{row.placement_type && <div className="placement-reference">{row.placement_type}</div>}{row.placement || '—'}</td>
          <td className="nowrap">{quantityText(row)}</td>
          <td className="nowrap max-ply"><MaxPly info={plyInfo?.[row.material_code]}/></td>
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

/**
 * Purpose: Show a Tech Pack's extraction as one table per page.
 * Input: props - extraction: the extraction object (page_tables, or materials for older results);
 * plyInfo: the maximum ply and related plies rows per material code (from the server; optional);
 * category: 'wovens' or 'knits' to show only that section (both when omitted).
 * Output: one PageTable for each page that has rows to show.
 */
export default function WovensTable({ extraction, plyInfo, selection, visibleKeys, category }) {
  // Older results remain readable until they are reprocessed into page tables.
  const tables = materialTables(extraction);
  return <>{tables.map((table, index) => <PageTable key={`${table.page_number}-${index}`} table={table} tableIndex={index} plyInfo={plyInfo} selection={selection} visibleKeys={visibleKeys} category={category} />)}</>;
}
