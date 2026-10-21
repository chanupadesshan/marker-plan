import React, { useRef, useState } from 'react';
import { FileText, FileUp, Link2, ScanText, X } from 'lucide-react';

/**
 * Purpose: One file picker (Tech Pack or PO) with the chosen file's name and a remove button.
 * Input: props - title, label, inputLabel: texts; file: the chosen File or null; onChoose(file) and onRemove():
 * callbacks; disabled: block changes.
 * Output: the picker element.
 */
function FileSlot({ title, label, file, onChoose, onRemove, disabled, inputLabel }) {
  const input = useRef(null);
  return <div className={`upload-slot ${file ? 'has-file' : ''}`}>
    <div className="upload-slot-heading"><strong>{title}</strong><span>PDF</span></div>
    <input ref={input} className="visually-hidden" type="file" accept="application/pdf,.pdf" aria-label={inputLabel}
      disabled={disabled} onChange={event => {
        const selected = event.target.files?.[0];
        if (selected) onChoose(selected);
        event.target.value = '';
      }}/>
    <button type="button" className="upload-slot-picker" disabled={disabled} onClick={() => input.current?.click()}>
      {file ? <FileText size={23}/> : <FileUp size={23}/>}
      <span><strong title={file?.name}>{file ? file.name : label}</strong><small>{file ? 'Click to change file' : 'Choose a PDF from your computer'}</small></span>
    </button>
    {file && <button type="button" className="remove-file icon-button" disabled={disabled} aria-label={`Remove ${title}`} onClick={onRemove}><X size={15}/></button>}
  </div>;
}

/**
 * Purpose: The old combined upload panel for a Tech Pack and a related PO. (No longer used by the app;
 * the sidebar has an upload on each tab. Kept in case the combined panel is wanted again.)
 * Input: props - busy: an upload is running; onUpload({ techPack, po }): called with the chosen files.
 * Output: the panel with two pickers and an Extract button.
 */
export default function DocumentUpload({ busy = false, onUpload }) {
  const [techPack, setTechPack] = useState(null);
  const [po, setPO] = useState(null);
  return <section className="document-upload panel" aria-label="Tech Pack and related purchase order">
    <div className="upload-panel-heading"><div><span className="eyebrow">DOCUMENT SET</span><h2>Tech Pack & related PO</h2>
      <p>Select a Tech Pack, a purchase order, or both to extract and review.</p></div><Link2 size={20}/></div>
    <div className="upload-pair">
      <FileSlot title="Tech Pack" label="Upload Tech Pack" inputLabel="Choose Tech Pack PDF" file={techPack} disabled={busy}
        onChoose={setTechPack} onRemove={() => setTechPack(null)}/>
      <FileSlot title="Related PO" label="Upload PO" inputLabel="Choose purchase order PDF" file={po} disabled={busy}
        onChoose={setPO} onRemove={() => setPO(null)}/>
    </div>
    <div className="upload-panel-footer"><p>{po && techPack ? 'Both documents will be saved and processed separately.' : po ? 'Extract purchase-order contracts and size quantities.' : 'Add the related PO when available.'}</p>
      <button type="button" className="primary-button" disabled={(!techPack && !po) || busy} onClick={() => onUpload?.({techPack, po})}><ScanText size={16}/>{busy ? 'Uploading…' : techPack && po ? 'Extract documents' : po ? 'Extract PO' : 'Extract Wovens'}</button>
    </div>
  </section>;
}
