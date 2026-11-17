import React from 'react';
import { nestingErrors } from './nesting.js';

export default function VerifiedNestingEditor({ value = [], onChange, sizes, tableLength, disabled, materialLabel }) {
  function change(index, update) { onChange(value.map((marker, mi) => mi === index ? { ...marker,
    ...(['length_m','width_cm','efficiency_percent','size_rows'].some(key => key in update) ? { verified: false } : {}), ...update } : marker)); }
  const errors = nestingErrors(value, tableLength, sizes);
  return <details className="plan-details nesting-editor"><summary>Verified nesting (optional) · {materialLabel}</summary>
    <p>Enter actual marker ratios and lengths from nesting output. When supplied, only these combinations are used. Without them, capacity stays an estimate from consumption.</p>
    {value.map((marker, index) => <section className="nesting-marker" key={index}>
      <div className="po-edit-fields">{[['label','Marker name'],['length_m','Verified length (m)'],['width_cm','Width (cm, optional)'],['efficiency_percent','Efficiency (%, optional)']].map(([key,label]) =>
        <label key={key}>{label}, marker {index + 1}<input disabled={disabled} value={marker[key] ?? ''} inputMode={key === 'label' ? undefined : 'decimal'}
          onChange={event => change(index, { [key]: event.target.value })}/></label>)}</div>
      <div className="table-scroll"><table className="bom-edit-table"><thead><tr>{sizes.map(size => <th key={size}>{size}</th>)}</tr></thead>
        <tbody><tr>{sizes.map(size => {
          const quantity = (marker.size_rows || []).find(row => row.size.trim().toLowerCase() === size.trim().toLowerCase())?.quantity || 0;
          return <td key={size}><input aria-label={`${size} count, marker ${index + 1}, ${materialLabel}`} type="number" min="0" max="1000" step="1" disabled={disabled} value={quantity}
            onChange={event => change(index, { size_rows: sizes.map(name => ({ size: name, quantity: name === size ? event.target.value : (marker.size_rows || []).find(row => row.size.trim().toLowerCase() === name.trim().toLowerCase())?.quantity || 0 })) })}/></td>;
        })}</tr></tbody></table></div>
      <label className="nesting-confirm"><input type="checkbox" disabled={disabled} checked={marker.verified === true}
        onChange={event => change(index, { verified: event.target.checked })}/> I verified this size ratio and length against nesting output.</label>
      <button type="button" className="secondary-button" disabled={disabled} onClick={() => onChange(value.filter((_,mi) => mi !== index))}>Remove marker</button>
    </section>)}
    <button type="button" className="secondary-button" disabled={disabled} onClick={() => onChange([...value,
      { label: '', length_m: '', verified: false, size_rows: sizes.map(size => ({ size, quantity: 0 })) }])}>Add verified marker</button>
    {!!errors.length && <ul className="field-error">{errors.map((error,index) => <li key={index}>{error}</li>)}</ul>}
  </details>;
}
