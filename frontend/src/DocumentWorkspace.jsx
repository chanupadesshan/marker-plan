import React from 'react';
import { FileText, ExternalLink, Download, Check, AlertTriangle, ChevronDown, CodeXml, SlidersHorizontal, ScanText } from 'lucide-react';
import WovensTable from './WovensTable.jsx';
import TokenUsage from './TokenUsage.jsx';

/**
 * Purpose: Show a Tech Pack for review: its status, the extracted Wovens table, warnings, an Approve BOM
 * button, and technical details with token usage and a JSON editor.
 * Input: props - current: the Tech Pack object; busy: an action is running; showEditor and editor: the JSON
 * editor state; onApprove, onToggleEditor, onEditorChange, onSave: callbacks for the buttons.
 * Output: the Tech Pack review view.
 */
export default function DocumentWorkspace({ current, busy = false, showEditor = false, editor = '',
  onApprove, onToggleEditor, onEditorChange, onSave }) {
  const extraction = current.extraction;
  const processing = ['queued', 'processing'].includes(current.status);
  const hasRows = Boolean(extraction?.materials?.length || extraction?.page_tables?.some(table => table.materials?.length));
  const pages = current.selected_pages || [];
  const colorways = new Set((extraction?.materials || []).flatMap(row => (row.colorways || []).map(v => v.code).filter(Boolean)));
  const approvalDisabled = busy || current.status === 'approved' || current.status === 'failed' || processing || !hasRows;
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
          <span>{current.page_count ?? '—'} PDF pages</span><span>{pages.length} Wovens pages</span>
          {extraction?.style_number && <span>Style {extraction.style_number}</span>}
        </div>
        <div className="button-group">
          <a className="secondary-button" target="_blank" rel="noreferrer" href={`/api/documents/${current.id}/pdf`}><ExternalLink size={15}/> View PDF</a>
          {hasRows && <a className="secondary-button" href={`/api/documents/${current.id}/json`}><Download size={15}/> Export JSON</a>}
          <button className="primary-button" disabled={approvalDisabled} onClick={onApprove}><Check size={16}/>{current.status === 'approved' ? 'Approved' : 'Approve BOM'}</button>
        </div>
      </div>
    </section>

    {current.error && <div className="alert error" role="alert"><AlertTriangle size={19}/>
      <div><strong>Extraction needs attention</strong><p>No new result has been approved. Open the details below to see the error.</p>
        <details className="error-details"><summary>View error details</summary><p>{current.error}</p></details>
      </div>
    </div>}

    {processing ? <section className="processing panel" role="status"><span className="spinner"/>
      <div><h2>{current.status === 'queued' ? 'Your Tech Pack is in the queue' : 'Reading your Wovens BOM'}</h2>
        <p>Finding material tables and reading the colorway columns. This view updates automatically.</p></div>
    </section> : hasRows ? <>
      <div className="results-heading"><div><span className="eyebrow">EXTRACTED MATERIALS</span><h2>Wovens BOM</h2></div>
        <div className="result-counts"><span>{extraction.materials?.length || '—'} materials</span><span>{colorways.size} colorways</span></div>
      </div>
      {!!extraction.warnings?.length && <details className="warning-box">
        <summary><AlertTriangle size={16}/>{extraction.warnings.length} extraction {extraction.warnings.length === 1 ? 'note' : 'notes'} to review<ChevronDown size={15}/></summary>
        <ul>{extraction.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
      </details>}
      <WovensTable extraction={extraction} plyInfo={current.ply_info}/>
      <p className="review-reminder"><Check size={14}/> Check material values against the source PDF before approval.</p>
    </> : <section className="empty-result">
      <span className="empty-icon"><ScanText size={29}/></span><h2>No material rows to review</h2>
      <p>{current.status === 'failed' ? 'Extraction could not be completed. Check the error and request details, then upload the PDF again.' : 'No Wovens rows were returned. Check the source PDF and the extraction details below.'}</p>
      <a className="secondary-button" target="_blank" rel="noreferrer" href={`/api/documents/${current.id}/pdf`}><ExternalLink size={15}/> Check source PDF</a>
    </section>}

    <details className="technical-details">
      <summary><SlidersHorizontal size={17}/><div><strong>Technical details</strong><span>Token usage, model information and JSON corrections</span></div><ChevronDown size={17}/></summary>
      <div className="technical-content">
        <dl className="technical-metadata"><div><dt>Extraction model</dt><dd>{current.model || 'Unavailable'}</dd></div>
          <div><dt>Detected Wovens pages</dt><dd>{pages.join(', ') || 'None'}</dd></div>
          <div><dt>Tech Pack number</dt><dd>{extraction?.tech_pack_number || 'Unavailable'}</dd></div></dl>
        <TokenUsage entries={current.request_usage || []}/>
        {extraction && <section className="json-tools"><div><h3>Review extracted JSON</h3><p>Edit the page tables to correct a result against its source.</p></div>
          <div className="button-group"><a className="secondary-button" href={`/api/documents/${current.id}/json`}><Download size={15}/> Download JSON</a>
            <button className="secondary-button" onClick={onToggleEditor}><CodeXml size={15}/>{showEditor ? 'Close editor' : 'Edit JSON'}</button></div>
          {showEditor && <div className="editor"><label htmlFor="extraction-json">Extracted JSON</label>
            <textarea id="extraction-json" spellCheck="false" rows={18} value={editor} onChange={event => onEditorChange?.(event.target.value)}/>
            <button className="primary-button" disabled={busy} onClick={onSave}><Check size={15}/> Save corrections</button>
          </div>}
        </section>}
      </div>
    </details>
  </>;
}
