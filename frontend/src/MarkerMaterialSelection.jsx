import React, { useEffect, useState } from 'react';
import WovensTable from './WovensTable.jsx';
import { markerMaterialRows, updateMaterialSelection, filterMarkerMaterials, selectVisibleMaterials } from './marker-materials.js';

// Each section (Wovens, then Knits) is its own table; a section with no rows to show draws nothing.
const CATEGORIES = ['wovens', 'knits'];

/** Material choices belong to the current session, never to the extracted BOM. */
export default function MarkerMaterialSelection({ extraction, plyInfo, selectedKeys = [], onChange, disabled = false }) {
  const [query, setQuery] = useState('');
  const [editing, setEditing] = useState(selectedKeys.length === 0);
  const [draftKeys, setDraftKeys] = useState(selectedKeys);
  const rows = markerMaterialRows(extraction);
  const visibleRows = filterMarkerMaterials(rows, query);
  const selected = new Set(selectedKeys);
  const chosen = rows.filter(entry => selected.has(entry.key));
  const draft = rows.filter(entry => draftKeys.includes(entry.key));
  const confirmed = !editing;
  useEffect(() => {
    const validKeys = markerMaterialRows(extraction).filter(entry => selectedKeys.includes(entry.key)).map(entry => entry.key);
    if (validKeys.length !== selectedKeys.length) onChange(validKeys);
  }, [extraction, selectedKeys, onChange]);

  return <>
    {!confirmed && <><section className="panel marker-material-controls" aria-label="Choose marker plan materials">
      <div><span className="eyebrow">MARKER PLAN</span><h2>Choose materials</h2>
        <p>Select the Wovens and Knits material rows to use for this marker plan. Choices are kept during this session.</p></div>
      <div className="marker-material-search">
        <label htmlFor="marker-material-search">Search by material code</label>
        <input id="marker-material-search" type="search" aria-label="Search materials by code" placeholder="e.g. R1371 or 1371"
          value={query} onChange={event => setQuery(event.target.value)}/>
        <span role="status">{visibleRows.length} of {rows.length} material rows</span>
      </div>
      <div className="button-group"><strong role="status">{draft.length} selected</strong>
        <button className="secondary-button" type="button" disabled={disabled || !visibleRows.length}
          onClick={() => setDraftKeys(selectVisibleMaterials(rows, draftKeys, visibleRows))}>{query.trim() ? 'Select matches' : 'Select all'}</button>
        <button className="secondary-button" type="button" disabled={disabled || !draft.length} onClick={() => setDraftKeys([])}>Clear selection</button></div>
    </section>
    {visibleRows.length ? CATEGORIES.map(category => <WovensTable key={category} category={category} extraction={extraction} plyInfo={plyInfo} selection={{ selectedKeys: new Set(draft.map(entry => entry.key)),
      visibleKeys: new Set(visibleRows.map(entry => entry.key)), disabled,
      onToggle: (key, checked) => setDraftKeys(updateMaterialSelection(rows, draftKeys, key, checked)) }}/>)
      : <section className="panel marker-no-matches" role="status"><p>No materials match this code.</p><button type="button" className="secondary-button" onClick={() => setQuery('')}>Clear search</button></section>}
    <div className="button-group selection-actions">
      <button type="button" className="primary-button" disabled={disabled || (!draft.length && !selectedKeys.length)}
        onClick={() => { onChange(draft.map(entry => entry.key)); setEditing(false); }}>OK</button>
    </div></>}
    <section className="panel marker-material-summary" aria-label="Selected marker plan materials">
      <div className="panel-heading"><div><span className="eyebrow">FOR THIS TECH PACK</span><h2>Selected materials</h2></div><span>{chosen.length} selected</span>
        {confirmed && <button type="button" className="secondary-button" disabled={disabled} onClick={() => { setDraftKeys(chosen.map(entry => entry.key)); setQuery(''); setEditing(true); }}>Edit selection</button>}</div>
      {confirmed && <p role="status">Material selection confirmed.</p>}
      {chosen.length ? CATEGORIES.map(category => <WovensTable key={category} category={category} extraction={extraction} plyInfo={plyInfo}
        visibleKeys={new Set(chosen.map(entry => entry.key))}/>)
        : <p className="marker-selection-empty">No materials selected. Tick the rows above to choose materials for the marker plan.</p>}
    </section>
  </>;
}
