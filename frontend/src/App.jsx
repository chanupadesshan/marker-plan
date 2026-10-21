import React, { useEffect, useRef, useState } from 'react';
import { FileUp, ScanText, ShieldCheck, AlertTriangle, Check, Layers3, ArrowRight } from 'lucide-react';
import { api, poApi } from './api';
import { uploadDocuments, selectedPOAfterUpload } from './uploadDocuments.js';
import PurchaseOrderPanel from './PurchaseOrderPanel.jsx';
import DocumentWorkspace from './DocumentWorkspace.jsx';
import DocumentUpload from './DocumentUpload.jsx';
import { loadSelectedDocument } from './document-loading.js';

function editableExtraction(extraction) {
  if (!extraction.page_tables?.length) return extraction;
  const { materials, ...editable } = extraction;
  return editable;
}

export default function App() {
  const [selectedId, setSelectedId] = useState(null);
  const [poId, setPoId] = useState(null);
  const [view, setView] = useState('bom');
  const selectedIdRef = useRef(null);
  const [documentData, setDocumentData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [showEditor, setShowEditor] = useState(false);
  const [editor, setEditor] = useState('');

  function selectDocument(id) {
    selectedIdRef.current = id;
    setSelectedId(id);
  }

  async function refreshDocument(id, updateEditor = false) {
    return loadSelectedDocument(id, () => selectedIdRef.current, row => {
      setDocumentData(row);
      if (updateEditor) setEditor(row.extraction ? JSON.stringify(editableExtraction(row.extraction), null, 2) : '');
    });
  }

  useEffect(() => {
    if (!selectedId) return;
    setError('');
    setShowEditor(false);
    let cancelled = false;
    setDocumentData(null);
    setLoading(true);
    api.get(selectedId).then(row => {
      if (cancelled || selectedIdRef.current !== selectedId) return;
      setDocumentData(row);
      setEditor(row.extraction ? JSON.stringify(editableExtraction(row.extraction), null, 2) : '');
    }).catch(e => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [selectedId]);
  useEffect(() => {
    if (!selectedId || !['queued', 'processing'].includes(documentData?.status)) return;
    const handle = setInterval(async () => {
      try {
        await refreshDocument(selectedId, !showEditor);
      } catch (e) { if (selectedIdRef.current === selectedId) setError(e.message); }
    }, 3000);
    return () => clearInterval(handle);
  }, [selectedId, documentData?.status, showEditor]);

  async function onUpload(files) {
    if (!files.techPack && !files.po) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await uploadDocuments(files, { techPack: api, po: poApi });
      if (result.techPackResult?.value) {
        setDocumentData(null); selectDocument(result.techPackResult.value.id);
      }
      setPoId(previous => selectedPOAfterUpload(previous, result.poResult));
      setView(result.poResult?.value ? 'po' : 'bom');
      setError([result.techPackResult?.error && `Tech Pack: ${result.techPackResult.error}`,
        result.poResult?.error && `PO: ${result.poResult.error}`].filter(Boolean).join(' · '));
      setMessage(result.warning || (result.techPackResult?.value || result.poResult?.value ? 'Upload saved. Extraction queued.' : ''));
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function onSave() {
    setBusy(true); setMessage(''); setError('');
    try {
      const parsed = JSON.parse(editor);
      await api.save(selectedId, parsed);
      await refreshDocument(selectedId, true);
      if (selectedIdRef.current !== selectedId) return;
      setMessage('Your corrections have been saved.');
      setShowEditor(false);
    } catch (e) { if (selectedIdRef.current === selectedId) setError(e.message); }
    finally { setBusy(false); }
  }

  async function onApprove() {
    if (!window.confirm('Have you checked the Wovens values against the original PDF?')) return;
    setBusy(true); setMessage(''); setError('');
    try {
      await api.approve(selectedId);
      await refreshDocument(selectedId);
      if (selectedIdRef.current !== selectedId) return;
      setMessage('Extraction approved.');
    } catch (e) { if (selectedIdRef.current === selectedId) setError(e.message); }
    finally { setBusy(false); }
  }

  const current = documentData;
  return <div className="app-shell sidebar-hidden">
    <header className="app-topbar">
      <div className="brand project-brand"><img src="/guston-logo.png" alt="Marker Plan logo" className="brand-logo" /><strong className="project-name">Marker Plan</strong></div>
      <div className="topbar-right"><span className="topbar-tag">Tech Pack review</span><span className="workspace-avatar" aria-hidden="true">M</span></div>
    </header>
    <div className="main-grid">
      <main className="workspace">
        <div className="workspace-heading"><div className="workspace-heading-copy">
          <div><div className="breadcrumb">Workspace <span>/</span> Wovens</div><h1>Wovens data review</h1></div>
        </div></div>
        <DocumentUpload busy={busy || loading} onUpload={onUpload}/>
        {(selectedId || poId) && <nav className="result-tabs" aria-label="Document results">
          {selectedId && <button className={view === 'bom' ? 'active' : ''} onClick={() => setView('bom')}>Wovens BOM {current?.status ? `· ${current.status.replaceAll('_', ' ')}` : ''}</button>}
          {poId && <button className={view === 'po' ? 'active' : ''} onClick={() => setView('po')}>Purchase orders</button>}
        </nav>}
        {error && <div className="alert error" role="alert"><AlertTriangle size={18}/><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}>Dismiss</button></div>}
        {message && <div className="alert success" role="status"><Check size={18}/><span>{message}</span><button aria-label="Dismiss message" onClick={() => setMessage('')}>Dismiss</button></div>}
        {poId && <div hidden={view !== 'po'}><PurchaseOrderPanel key={poId} id={poId} refreshKey={current?.status}/></div>}
        <div hidden={view !== 'bom'}>{loading ? <div className="loading-workspace" role="status"><span className="spinner"/> Loading your Tech Pack…</div> : current ?
          <DocumentWorkspace key={current.id} current={current} busy={busy} showEditor={showEditor} editor={editor} onApprove={onApprove}
            onToggleEditor={() => { setShowEditor(!showEditor); setEditor(JSON.stringify(editableExtraction(current.extraction), null, 2)); }} onEditorChange={setEditor} onSave={onSave}/> :
          <section className="welcome">
            <div className="document-illustration" aria-hidden="true"><span className="paper-back"/><span className="paper-front"><ScanText size={40}/><i/><i/><i/></span><span className="paper-check"><Check size={18}/></span></div>
            <span className="eyebrow">FROM TECH PACK TO MATERIAL TABLE</span><h2>Your Wovens, ready to review.</h2>
            <p>Choose a Tech Pack, a purchase order, or both above to start your review.</p>
            <div className="welcome-steps"><span><b>01</b> Upload PDF</span><span><b>02</b> Extract Wovens</span><span><b>03</b> Review & approve</span></div>
          </section>}</div>
        <footer className="workspace-footer"><ShieldCheck size={13}/> Human review keeps your material data accurate.</footer>
      </main>
    </div>
  </div>;
}
