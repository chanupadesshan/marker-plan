import React, { useRef, useState } from 'react';
import { bomTables, createBomDraft, bomPayload, validateBomDraft } from './bom-editor.js';
import { designIds } from './po-link.js';

const fields = [['material_code', 'Material code'], ['developer_code', 'Developer code'], ['description', 'Description'],
  ['composition', 'Composition'], ['placement_type', 'Placement type'], ['placement', 'Placement'], ['quantity', 'Quantity'], ['unit', 'Unit']];
const colorFields = [['code', 'Garment colour code'], ['name', 'Garment colour name'], ['material_color_code', 'Material colour code'],
  ['material_color_name', 'Material colour name'], ['fabric_reference', 'Fabric reference']];

export default function BomEditor({ extraction, busy, onSave, onCancel }) {
  const [draft, setDraft] = useState(() => createBomDraft(extraction));
  const [errors, setErrors] = useState({});
  const [saveError, setSaveError] = useState('');
  const [expandedColours, setExpandedColours] = useState({});
  const formRef = useRef(null);
  function change(update) {
    setDraft(previous => { const next = structuredClone(previous); update(next); return next; });
    setErrors({}); setSaveError('');
  }
  function tableAt(next, index) { return bomTables(next)[index]; }
  function rowChange(ti, ri, field, value) { change(next => { tableAt(next, ti).materials[ri][field] = value; }); }
  async function submit(event) {
    event.preventDefault();
    const nextErrors = validateBomDraft(draft);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) {
      // A <ong form hides the problem field, so take the user to the first one.
      setTimeout(() => {
        const field = formRef.current?.querySelector('[aria-invalid="true"]');
        field?.scrollIntoView({ block: 'center' });
        field?.focus({ preventScroll: true });
      }, 0);
      return;
    }
    try { await onSave(bomPayload(draft, extraction)); } catch (error) { setSaveError(error.message || 'Unable to save changes. Please try again.'); }
  }
  return <form ref={formRef} className="bom-editor panel" onSubmit={submit}>
    <div className="panel-heading"><div><h2>Edit BOM</h2><p>Check your changes against the source PDF. Saving will require approval again.</p></div></div>
    <fieldset disabled={busy}>
      <div className="bom-document-fields">{[['style_number', 'Style number'], ['tech_pack_number', 'Tech pack number']].map(([key, label]) =>
        <label key={key}>{label}<input value={draft[key] || ''} onChange={event => change(next => { next[key] = event.target.value; })}/></label>)}
        <label>Quality IDs (comma separated)<input defaultValue={designIds(draft).join(', ')} onChange={event => change(next => {
          next.design_numbers = event.target.value.split(/[\s,]+/).filter(Boolean);
          next.design_number = next.design_numbers.length === 1 ? next.design_numbers[0] : null;
        })}/></label></div>
      {bomTables(draft).map((table, ti) => <section className="bom-edit-page" key={ti}>
        <h3>{table.page_number ? `Page ${table.page_number}` : 'Materials'}</h3>
        <div className="table-scroll" tabIndex={0} role="region" aria-label={`Editable materials ${ti + 1}`}><table className="bom-edit-table">
          <thead><tr><th>Section</th>{fields.map(([key, label]) => <th key={key}>{label}</th>)}<th>Colours</th><th>Actions</th></tr></thead>
          <tbody>{(table.materials || []).map((row, ri) => <React.Fragment key={ri}><tr>
            <td><label className="sr-only" htmlFor={`bom-${ti}.${ri}.category`}>Section, table {ti + 1}, row {ri + 1}</label>
              <select id={`bom-${ti}.${ri}.category`} value={row.category === 'knits' ? 'knits' : 'wovens'} onChange={e => rowChange(ti, ri, 'category', e.target.value)}>
                <option value="wovens">Wovens</option><option value="knits">Knits</option></select></td>
            {fields.map(([key, label]) => {
              const errorKey = `${ti}.${ri}.${key}`;
              return <td key={key}><label className="sr-only" htmlFor={`bom-${errorKey}`}>{label}, table {ti + 1}, row {ri + 1}</label>
                {['description', 'composition', 'placement', 'placement_type'].includes(key)
                  ? <textarea id={`bom-${errorKey}`} rows={2} className="bom-two-line-input" value={row[key] ?? ''}
                    aria-invalid={Boolean(errors[errorKey])} aria-describedby={errors[errorKey] ? `error-${errorKey}` : undefined}
                    onChange={e => rowChange(ti, ri, key, e.target.value)}/>
                  : <input id={`bom-${errorKey}`} value={row[key] ?? ''} inputMode={key === 'quantity' ? 'decimal' : undefined}
                    aria-invalid={Boolean(errors[errorKey])} aria-describedby={errors[errorKey] ? `error-${errorKey}` : undefined}
                    title={row[key] == null ? '' : String(row[key])}
                    onChange={e => rowChange(ti, ri, key, e.target.value)}/>}
                {errors[errorKey] && <small className="bom-field-error" id={`error-${errorKey}`}>{errors[errorKey]}</small>}</td>;
            })}
            <td className="bom-colour-cell"><button type="button" className="bom-colour-toggle" aria-expanded={Boolean(expandedColours[`${ti}.${ri}`])}
              aria-controls={`bom-colours-${ti}-${ri}`} onClick={() => setExpandedColours(previous => ({ ...previous, [`${ti}.${ri}`]: !previous[`${ti}.${ri}`] }))}>
              <span>{row.colorways?.length || 0} colours</span><span>{expandedColours[`${ti}.${ri}`] ? 'Close colours ↑' : 'Edit colours ↓'}</span>
            </button></td>
            <td><button type="button" className="secondary-button" aria-label={`Remove material row ${ri + 1} from table ${ti + 1}`}
              onClick={() => { setExpandedColours({}); change(next => { tableAt(next, ti).materials.splice(ri, 1); }); }}>Remove row</button></td>
          </tr><tr className="bom-colour-expanded-row" hidden={!expandedColours[`${ti}.${ri}`]}><td colSpan={11}>
            <section id={`bom-colours-${ti}-${ri}`} className="bom-colour-panel" aria-label={`Colours for ${row.material_code || `material ${ri + 1}`}`}>
              <div className="bom-colour-panel-heading"><div><h4>Colours · {row.material_code || `Material ${ri + 1}`}</h4><p>Garment and material colour details for this row.</p></div>
                <button type="button" className="secondary-button" onClick={() => change(next => {
                  const material = tableAt(next, ti).materials[ri]; material.colorways = [...(material.colorways || []), {}];
                })}>Add colour</button></div>
              <div className="bom-colour-grid">{(row.colorways || []).map((variant, vi) => <div className="bom-colour" key={vi}>
                <div className="bom-colour-card-heading"><strong>Colour {vi + 1}</strong><button type="button" className="bom-colour-remove"
                  aria-label={`Remove colour ${vi + 1} from material ${ri + 1}`} onClick={() => change(next => { tableAt(next, ti).materials[ri].colorways.splice(vi, 1); })}>Remove colour</button></div>
                <div className="bom-colour-fields">{colorFields.map(([key, label]) => <label key={key}>{label}<input value={variant[key] || ''}
                  onChange={event => change(next => { tableAt(next, ti).materials[ri].colorways[vi][key] = event.target.value; })}/></label>)}</div>
              </div>)}</div>
              {!row.colorways?.length && <p className="bom-colour-empty">No colours yet. Add a colour to enter its details.</p>}
            </section>
          </td></tr></React.Fragment>)}</tbody>
        </table></div>
        <button type="button" className="secondary-button" onClick={() => change(next => {
          const target = tableAt(next, ti);
          target.materials.push({ category: 'wovens', material_code: '', quantity: '', unit: '', source_pages: target.page_number ? [target.page_number] : [],
            colorways: (target.colorway_headers || []).map(header => ({ ...header })) });
        })}>Add row</button>
      </section>)}
      <div className="bom-editor-actions">
        {Object.keys(errors).length > 0 && <p role="alert" className="bom-field-error">{errors.materials || `Cannot save yet: ${Object.values(errors)[0]}${Object.keys(errors).length > 1 ? ` (${Object.keys(errors).length} fields need attention)` : ''}`}</p>}
        {saveError && <p role="alert" className="bom-field-error">{saveError}</p>}
        <button className="primary-button" type="submit">{busy ? 'Saving…' : 'Save changes'}</button>
        <button type="button" className="secondary-button" onClick={onCancel}>Cancel</button></div>
    </fieldset>
  </form>;
}
