import React, { useEffect, useRef, useState } from 'react';
import { ScanText, ShieldCheck, AlertTriangle, Check, ReceiptText, Search } from 'lucide-react';
import { api, poApi } from './api';
import PurchaseOrderPanel from './PurchaseOrderPanel.jsx';
import DocumentWorkspace from './DocumentWorkspace.jsx';
import Sidebar from './Sidebar.jsx';
import { useConfirm } from './useConfirm.jsx';
import { inProgress } from './documentSearch.js';
import { loadSelectedDocument } from './document-loading.js';

function editableExtraction(extraction) {
  if (!extraction.page_tables?.length) return extraction;
  const { materials, ...editable } = extraction;
  return editable;
}

export default function App() {
  const [selectedId, setSelectedId] = useState(null);
  const [poId, setPoId] = useState(null);
  const [tab, setTab] = useState('techpack');
  // The Marker Plan tab shows either document type; this is the type of the last one opened.
  const [lastKind, setLastKind] = useState('techpack');
  const [planPicked, setPlanPicked] = useState(false);
  const [techPacks, setTechPacks] = useState([]);
  const [purchaseOrders, setPurchaseOrders] = useState([]);
  const selectedIdRef = useRef(null);
  const [documentData, setDocumentData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [showEditor, setShowEditor] = useState(false);
  const [editor, setEditor] = useState('');
  const [confirm, dialog] = useConfirm();

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

  // A failed list refresh keeps the previous list; it must not hide a working document view.
  async function refreshLists() {
    const [packs, orders] = await Promise.allSettled([api.list(), poApi.list()]);
    if (packs.status === 'fulfilled') setTechPacks(packs.value);
    if (orders.status === 'fulfilled') setPurchaseOrders(orders.value);
  }

  useEffect(() => { refreshLists(); }, []);
  // Statuses in the sidebar follow extraction progress without a manual refresh.
  const listBusy = inProgress(techPacks) || inProgress(purchaseOrders);
  useEffect(() => {
    if (!listBusy) return;
    const handle = setInterval(refreshLists, 4000);
    return () => clearInterval(handle);
  }, [listBusy]);

  function onSelect(kind, id) {
    setError(''); setMessage('');
    setLastKind(kind);
    // Picking a search result keeps the user on Marker Plan so the results stay in view.
    if (tab === 'plan') setPlanPicked(true); else setTab(kind);
    if (kind === 'po') setPoId(id); else selectDocument(id);
  }

  async function onDelete(kind, item) {
    const isPo = kind === 'po';
    if (!await confirm({ tone: 'danger', title: `Delete this ${isPo ? 'purchase order' : 'Tech Pack'}?`, confirmLabel: 'Delete', detail: item.filename,
      message: `${item.status === 'approved' ? 'It has already been approved. ' : ''}This permanently removes the PDF, ${isPo
        ? 'the extracted contracts and size quantities, and the page images.'
        : 'the extracted Wovens data, and the page images. Purchase orders uploaded with it are kept.'} This can't be undone.` })) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await (isPo ? poApi : api).remove(item.id);
      if (isPo) {
        setPurchaseOrders(list => list.filter(entry => entry.id !== item.id));
        setPoId(previous => previous === item.id ? null : previous);
      } else {
        setTechPacks(list => list.filter(entry => entry.id !== item.id));
        if (selectedIdRef.current === item.id) {
          selectedIdRef.current = null;
          setSelectedId(null); setDocumentData(null); setEditor(''); setShowEditor(false);
        }
      }
      setMessage(`${item.filename} was deleted.`);
    } catch (e) { setError(`Delete failed: ${e.message}`); }
    finally { setBusy(false); refreshLists(); }
  }

  // Returns false when the upload was rejected, so the sidebar keeps the chosen file.
  async function onUpload(kind, file) {
    setBusy(true); setError(''); setMessage('');
    try {
      if (kind === 'po') {
        const row = await poApi.upload(file);
        setPoId(row.id);
      } else {
        const row = await api.upload(file);
        setDocumentData(null); selectDocument(row.id);
      }
      setTab(kind); setLastKind(kind);
      setMessage('Upload saved. Extraction queued.');
      refreshLists();
      return true;
    } catch (e) {
      setError(`${kind === 'po' ? 'PO' : 'Tech Pack'}: ${e.message}`);
      return false;
    } finally { setBusy(false); }
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
    if (!await confirm({ title: 'Approve this Wovens BOM?', confirmLabel: 'Approve',
      message: 'Confirm you have checked the Wovens values against the original PDF.', detail: current?.filename })) return;
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
  const inPlan = tab === 'plan';
  const viewKind = inPlan ? lastKind : tab;
  const isPO = viewKind === 'po';
  // Until something is picked from the Marker Plan search, show its own welcome instead of a stale document.
  const planWelcome = inPlan && !planPicked;
  // Only the document on screen is highlighted in the shared Marker Plan results.
  const highlighted = !inPlan ? { techpack: selectedId, po: poId }
    : { techpack: planPicked && !isPO ? selectedId : null, po: planPicked && isPO ? poId : null };
  const heading = planWelcome ? 'Search your documents' : isPO ? 'Purchase order review' : 'Wovens data review';
  return <div className="app-shell">
    {dialog}
    <header className="app-topbar">
      <div className="brand project-brand"><img src="/guston-logo.png" alt="Marker Plan logo" className="brand-logo" /><strong className="project-name">Marker Plan</strong></div>
      <div className="topbar-right"><span className="topbar-tag">{planWelcome ? 'Marker Plan search' : isPO ? 'Purchase order review' : 'Tech Pack review'}</span><span className="workspace-avatar" aria-hidden="true">M</span></div>
    </header>
    <div className="main-grid">
      <Sidebar tab={tab} onTabChange={setTab} techPacks={techPacks} purchaseOrders={purchaseOrders}
        selected={highlighted} busy={busy || loading} onSelect={onSelect} onUpload={onUpload} onDelete={onDelete}/>
      <main className="workspace">
        <div className="workspace-heading"><div className="workspace-heading-copy">
          <div><div className="breadcrumb">Workspace <span>/</span> {inPlan ? 'Marker Plan' : isPO ? 'Purchase orders' : 'Wovens'}{inPlan && !planWelcome && <><span>/</span>{isPO ? 'Purchase orders' : 'Tech Packs'}</>}</div><h1>{heading}</h1></div>
        </div></div>
        {error &&<div className="alert error" role="alert"><AlertTriangle size={18}/><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}>Dismiss</button></div>}
        {message && <div className="alert success" role="status"><Check size={18}/><span>{message}</span><button aria-label="Dismiss message" onClick={() => setMessage('')}>Dismiss</button></div>}
        {planWelcome && <section className="welcome">
          <div className="document-illustration" aria-hidden="true"><span className="paper-back"/><span className="paper-front"><Search size={40}/><i/><i/><i/></span><span className="paper-check"><Check size={18}/></span></div>
          <span className="eyebrow">MARKER PLAN</span><h2>Find any Tech Pack or purchase order.</h2>
          <p>Use the search box in the sidebar, then pick a result to review it here.</p>
          <div className="welcome-steps"><span><b>01</b> Search</span><span><b>02</b> Pick a result</span><span><b>03</b> Review & approve</span></div>
        </section>}
        <div hidden={planWelcome || !isPO}>{poId ? <PurchaseOrderPanel key={poId} id={poId} refreshKey={current?.status}/> :
          <section className="welcome">
            <div className="document-illustration" aria-hidden="true"><span className="paper-back"/><span className="paper-front"><ReceiptText size={40}/><i/><i/><i/></span><span className="paper-check"><Check size={18}/></span></div>
            <span className="eyebrow">FROM PURCHASE ORDER TO SIZE TABLE</span><h2>Your contracts, ready to review.</h2>
            <p>Upload a purchase order in the sidebar, or pick an extracted one from the list.</p>
            <div className="welcome-steps"><span><b>01</b> Upload PDF</span><span><b>02</b> Extract PO</span><span><b>03</b> Review & approve</span></div>
          </section>}</div>
        <div hidden={planWelcome || isPO}>{loading ? <div className="loading-workspace" role="status"><span className="spinner"/> Loading your Tech Pack…</div> : current ?
          <DocumentWorkspace key={current.id} current={current} busy={busy} showEditor={showEditor} editor={editor} onApprove={onApprove}
            onToggleEditor={() => { setShowEditor(!showEditor); setEditor(JSON.stringify(editableExtraction(current.extraction), null, 2)); }} onEditorChange={setEditor} onSave={onSave}/> :
          <section className="welcome">
            <div className="document-illustration" aria-hidden="true"><span className="paper-back"/><span className="paper-front"><ScanText size={40}/><i/><i/><i/></span><span className="paper-check"><Check size={18}/></span></div>
            <span className="eyebrow">FROM TECH PACK TO MATERIAL TABLE</span><h2>Your Wovens, ready to review.</h2>
            <p>Upload a Tech Pack in the sidebar, or pick an extracted one from the list.</p>
            <div className="welcome-steps"><span><b>01</b> Upload PDF</span><span><b>02</b> Extract Wovens</span><span><b>03</b> Review & approve</span></div>
          </section>}</div>
        <footer className="workspace-footer"><ShieldCheck size={13}/> Human review keeps your material data accurate.</footer>
      </main>
    </div>
  </div>;
}
