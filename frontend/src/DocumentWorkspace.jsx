import React, { useState } from 'react';
import { FileText, ExternalLink, Download, Check, AlertTriangle, ChevronDown, SlidersHorizontal, ScanText } from 'lucide-react';
import { openFile } from './api.js';
import WovensTable from './WovensTable.jsx';
import BomEditor from './BomEditor.jsx';
import TechPackProgress from './TechPackProgress.jsx';
import TokenUsage from './TokenUsage.jsx';
import MarkerMaterialSelection from './MarkerMaterialSelection.jsx';
import MarkerPoSelection from './MarkerPoSelection.jsx';
import MarkerCuttingPlan from './MarkerCuttingPlan.jsx';
import { selectedPlanOrders } from './marker-plan.js';
import { materialCategory, materialTables } from './marker-materials.js';
import { designIds } from './po-link.js';

/** Review extracted materials and allow permitted users to correct them before approval. */
export default function DocumentWorkspace({ current, busy = false, onApprove, onSaveData, canEdit = false, markerSelection }) {
  const [editing, setEditing] = useState(false);
  const extraction = current.extraction;
  const processing = ['queued', 'processing'].includes(current.status);
  const hasRows = Boolean(extraction?.materials?.length || extraction?.page_tables?.some(table => table.materials?.length));
  const pages = current.selected_pages || [];
  const colorways = new Set((extraction?.materials || []).flatMap(row => (row.colorways || []).map(v => v.code).filter(Boolean)));
  // How many rows each section has; a section with none gets no card (a Tech Pack with only Wovens looks as before).
  const sectionCounts = { wovens: 0, knits: 0 };
  for (const table of materialTables(extraction)) for (const row of table.materials || []) sectionCounts[materialCategory(row)] += 1;
  const sections = [['wovens', sectionCounts.wovens], ['knits', sectionCounts.knits]].filter(([category, count]) => count || (category === 'wovens' && !sectionCounts.knits));
  const approvalDisabled = !canEdit || editing || busy || current.status === 'approved' || current.status === 'failed' || processing || !hasRows;
  return <>
    <section className="document-overview">
      <div className="document-title-row">
        <span className="document-symbol"><FileText size={21}/></span>
        <div className="document-title"><span className="eyebrow">SELECTED TECH PACK</span>
          <h2 title={current.filename}>{current.filename}</h2>
        </div>
        <span className={`status ${current.status}`}>{(current.status || '').replaceAll('_', ' ')}</span>
      </div>
      <div className="document-toolbar">
        <div className="document-facts">
          <span>{current.page_count ?? '—'} PDF pages</span><span>{pages.length} BOM pages</span>
          {extraction?.style_number && <span>Style {extraction.style_number}</span>}
          {!!designIds(extraction).length && <span>{designIds(extraction).length > 1 ? 'Quality IDs' : 'Quality ID'} {designIds(extraction).join(', ')}</span>}
          <span>Tech Pack ID {extraction?.tech_pack_number || '—'}</span>
        </div>
        <div className="button-group">
          <a className="secondary-button" target="_blank" rel="noreferrer" href={`/api/documents/${current.id}/pdf`} onClick={e => openFile(e, `/api/documents/${current.id}/pdf`)}><ExternalLink size={15}/> View PDF</a>
          {canEdit && extraction && !markerSelection && !processing && current.status !== 'failed' && !editing && <button className="secondary-button" disabled={busy} onClick={() => setEditing(true)}>Edit BOM</button>}
          <button className="primary-button" disabled={approvalDisabled} onClick={onApprove}><Check size={16}/>{current.status === 'approved' ? 'Approved' : 'Approve BOM'}</button>
        </div>
      </div>
    </section>

    {current.error && <div className="alert error" role="alert"><AlertTriangle size={19}/>
      <div><strong>Extraction needs attention</strong><p>No new result has been approved. Open the details below to see the error.</p>
        <details className="error-details"><summary>View error details</summary><p>{current.error}</p></details>
      </div>
    </div>}

    {editing ? <BomEditor extraction={extraction} busy={busy} onCancel={() => setEditing(false)}
      onSave={async payload => { await onSaveData(payload); setEditing(false); }}/>
      : processing ? <TechPackProgress current={current}/> : hasRows ? <>
      {/* The marker plan step offers both sections in one selection; the review screen shows a card for each section that has rows. */}
      {(markerSelection ? [['marker', sectionCounts.wovens + sectionCounts.knits]] : sections).map(([category, count], position) => <React.Fragment key={category}>
        <div className="results-heading"><div><span className="eyebrow">EXTRACTED MATERIALS</span><h2>{category === 'knits' ? 'Knits BOM' : category === 'marker' ? 'Wovens and Knits BOM' : 'Wovens BOM'}</h2></div>
          <div className="result-counts"><span>{count} materials</span>{position === 0 && <span>{colorways.size} colorways</span>}</div>
        </div>
        {position === 0 && !!extraction.warnings?.length && <details className="warning-box">
          <summary><AlertTriangle size={16}/>{extraction.warnings.length} extraction {extraction.warnings.length === 1 ? 'note' : 'notes'} to review<ChevronDown size={15}/></summary>
          <ul>{extraction.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
        </details>}
        {!markerSelection && <WovensTable extraction={extraction} plyInfo={current.ply_info} category={category}/>}
      </React.Fragment>)}
      {markerSelection && <MarkerMaterialSelection extraction={extraction} plyInfo={current.ply_info}
        selectedKeys={markerSelection.selectedKeys} onChange={markerSelection.onChange}
        disabled={busy || processing || current.status === 'failed'}/>}
      {!!markerSelection?.selectedKeys.length && <MarkerPoSelection purchaseOrders={markerSelection.purchaseOrders}
        techPackReference={extraction.tech_pack_number}
        value={markerSelection.poSelection} onChange={markerSelection.onPoChange}
        disabled={busy || processing || current.status === 'failed'}/>}
      {!!markerSelection?.selectedKeys.length && !!markerSelection.poSelection?.ids?.length && markerSelection.onPlanChange &&
        <MarkerCuttingPlan extraction={extraction} plyInfo={current.ply_info} materialKeys={markerSelection.selectedKeys}
          source={{ id: current.id, filename: current.filename, style_number: extraction.style_number, tech_pack_number: extraction.tech_pack_number }}
          orders={selectedPlanOrders(markerSelection.poSelection)} value={markerSelection.plan} onChange={markerSelection.onPlanChange}
          disabled={busy || processing || current.status === 'failed'}/>}
      <p className="review-reminder"><Check size={14}/> Check material values against the source PDF before approval.</p>
    </> : <section className="empty-result">
      <span className="empty-icon"><ScanText size={29}/></span><h2>No material rows to review</h2>
      <p>{current.status === 'failed' ? 'Extraction could not be completed. Check the error and request details, then upload the PDF again.' : 'No Wovens or Knits rows were returned. Check the source PDF and the extraction details below.'}</p>
      <a className="secondary-button" target="_blank" rel="noreferrer" href={`/api/documents/${current.id}/pdf`} onClick={e => openFile(e, `/api/documents/${current.id}/pdf`)}><ExternalLink size={15}/> Check source PDF</a>
    </section>}

    <details className="technical-details">
      <summary><SlidersHorizontal size={17}/><div><strong>Technical details</strong><span>Token usage, model information and data download</span></div><ChevronDown size={17}/></summary>
      <div className="technical-content">
        <dl className="technical-metadata"><div><dt>Extraction model</dt><dd>{current.model || 'Unavailable'}</dd></div>
          <div><dt>Detected BOM pages</dt><dd>{pages.join(', ') || 'None'}</dd></div>
          <div><dt>Tech Pack number</dt><dd>{extraction?.tech_pack_number || 'Unavailable'}</dd></div></dl>
        <TokenUsage entries={current.request_usage || []}/>
        {extraction && <section className="json-tools"><div><h3>Download extracted data</h3><p>Use Edit BOM above to correct the extracted values.</p></div>
          <div className="button-group"><a className="secondary-button" href={`/api/documents/${current.id}/json`} onClick={e => openFile(e, `/api/documents/${current.id}/json`, `wovens-${current.id}.json`)}><Download size={15}/> Download JSON</a>
            </div>
        </section>}
      </div>
    </details>
  </>;
}
