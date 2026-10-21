import React, { useRef, useState } from 'react';
import { FileUp, FileText, X } from 'lucide-react';

export default function POUpload() {
  const [file, setFile] = useState(null);
  const input = useRef(null);
  return <div className="po-upload">
    <input ref={input} className="visually-hidden" type="file" accept="application/pdf,.pdf"
      aria-label="Choose purchase order PDF" onChange={event => {
        const selected = event.target.files?.[0];
        if (selected) setFile(selected);
        event.target.value = '';
      }}/>
    <button type="button" className="secondary-button" onClick={() => input.current?.click()}>
      <FileUp size={16}/>{file ? 'Change PO' : 'Upload PO'}
    </button>
    {file && <div className="po-file" role="status">
      <FileText size={16}/><div><span>Selected purchase order</span><strong title={file.name}>{file.name}</strong></div>
      <button type="button" className="icon-button" aria-label="Remove selected PO" onClick={() => setFile(null)}><X size={15}/></button>
    </div>}
  </div>;
}
