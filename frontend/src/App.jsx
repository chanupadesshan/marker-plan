import React, { useEffect, useRef, useState } from 'react';
import { ScanText, ShieldCheck, AlertTriangle, Check, Lock, ReceiptText } from 'lucide-react';
import { api, poApi } from './api';
import AppShell from './AppShell.jsx';
import PurchaseOrderPanel from './PurchaseOrderPanel.jsx';
import DocumentWorkspace from './DocumentWorkspace.jsx';
import Sidebar, { ArchiveList } from './Sidebar.jsx';
import StylePurchaseOrders from './StylePurchaseOrders.jsx';
import DocumentLibrary from './DocumentLibrary.jsx';
import SavedMarkerPlans from './SavedMarkerPlans.jsx';
import { useConfirm } from './useConfirm.jsx';
import { inProgress } from './documentSearch.js';
import { enrichStyles, isApproved, linkedOrders, lockedReason, planOrders, styleSteps, techPackIds } from './po-link.js';
import { loadSelectedDocument } from './document-loading.js';
import { can } from './permissions.js';
import { initialWorkspaceTab } from './plan-navigation.js';
import { workspaceHref } from './nav.js';

/**
 * Purpose: The whole screen: the navigation; Create Marker Plan (a style is one Tech Pack with its purchase orders
 * and marker plan, worked through in three stages); and three libraries: Tech Packs, Purchase Orders and Marker Plans.
 * It owns the lists, the current selection, uploads, deletes, corrections and approvals, and refreshes statuses while extractions run.
 * Input: user - the signed-in person ({ full_name, email }); onSignOut - called by the Sign out button.
 * Output: the page.
 */
export default function App({ user, onSignOut }) {
  const [selectedId, setSelectedId] = useState(null);
  const [poId, setPoId] = useState(null);
  // 'techpack', 'po' or 'plan': the stage of the open style that is on screen.
  const [stage, setStage] = useState('techpack');
  const [tab, setTab] = useState(() => initialWorkspaceTab(typeof window === 'undefined' ? '' : window.location.search));
  const [browsingDocuments, setBrowsingDocuments] = useState(() => typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('view') === 'documents');
  const libraryEntry = useRef(false);
  useEffect(() => {
    const restore = () => {
      setTab(initialWorkspaceTab(window.location.search));
      setBrowsingDocuments(new URLSearchParams(window.location.search).get('view') === 'documents');
    };
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, []);
  const [planMaterialsByDocument, setPlanMaterialsByDocument] = useState({});
  const [planPosByDocument, setPlanPosByDocument] = useState({});
  // Cutting settings and the latest cutting-plan job per Tech Pack, kept while the app is open.
  const [planCuttingByDocument, setPlanCuttingByDocument] = useState({});
  const [techPacks, setTechPacks] = useState([]);
  const [purchaseOrders, setPurchaseOrders] = useState([]);
  const selectedIdRef = useRef(null);
  const [documentData, setDocumentData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [confirm, dialog] = useConfirm();

  /** Purpose: Make a Tech Pack (a style) the selected one. Input: id. Output: nothing (updates the selection and its ref). */
  function selectDocument(id) {
    selectedIdRef.current = id;
    setSelectedId(id);
  }

  /**
   * Purpose: Reload the selected Tech Pack from the server, ignoring the answer if the user has selected another since.
   * Input: id - the Tech Pack to reload.
   * Output: a promise of the loaded row.
   */
  async function refreshDocument(id) {
    return loadSelectedDocument(id, () => selectedIdRef.current, row => {
      setDocumentData(row);
    });
  }

  useEffect(() => {
    if (!selectedId) return;
    setError('');
    let cancelled = false;
    setDocumentData(null);
    setLoading(true);
    api.get(selectedId).then(row => {
      if (cancelled || selectedIdRef.current !== selectedId) return;
      setDocumentData(row);
    }).catch(e => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [selectedId]);
  useEffect(() => {
    if (!selectedId || !['queued', 'processing'].includes(documentData?.status)) return;
    const handle = setInterval(async () => {
      try {
        await refreshDocument(selectedId);
      } catch (e) { if (selectedIdRef.current === selectedId) setError(e.message); }
    }, 3000);
    return () => clearInterval(handle);
  }, [selectedId, documentData?.status]);

  /**
   * Purpose: Reload the Tech Pack and PO lists for the sidebar. A failed refresh keeps the previous
   * list, so it never hides a working document view.
   * Input: none.
   * Output: a promise that finishes when both lists have been tried.
   */
  async function refreshLists() {
    const [packs, orders] = await Promise.allSettled([api.list(), poApi.list()]);
    if (packs.status === 'fulfilled') setTechPacks(packs.value);
    if (orders.status === 'fulfilled') setPurchaseOrders(orders.value);
  }

  /**
   * Purpose: Open a style at one of its stages.
   * Input: id - the Tech Pack's id; nextStage - 'techpack', 'po' or 'plan'.
   * Output: nothing.
   */
  function openStyle(id, nextStage = 'techpack') {
    setPoId(null);
    setStage(nextStage);
    if (selectedIdRef.current !== id) { setDocumentData(null); selectDocument(id); }
  }

  // Switching tabs also picks up documents uploaded outside this browser session.
  useEffect(() => { refreshLists(); }, [tab]);
  // Statuses in the sidebar follow extraction progress without a manual refresh.
  const listBusy = inProgress(techPacks) || inProgress(purchaseOrders);
  useEffect(() => {
    if (!listBusy) return;
    const handle = setInterval(refreshLists, 4000);
    return () => clearInterval(handle);
  }, [listBusy]);

  /**
   * Purpose: Open a document the user clicked in the sidebar. The Tech Packs and Purchase Orders libraries stay on their
   * own tab; in Create Marker Plan it opens that style.
   * Input: kind - 'techpack' or 'po'; id - the document's id.
   * Output: nothing.
   */
  function onSelect(kind, id) {
    setError(''); setMessage('');
    if (kind === 'po') setPoId(id);
    else openStyle(id, 'techpack');
  }

  /**
   * Purpose: Delete a document after the user confirms in a dialog, then remove it from the lists and clear it from view.
   * Input: kind - 'techpack' or 'po'; item - the list entry to delete.
   * Output: a promise that finishes when the delete is done or cancelled; failures show an error message.
   */
  async function onDelete(kind, item) {
    const isPo = kind === 'po';
    const kept = isPo ? 0 : linkedOrders(purchaseOrders, item.id).length;
    if (!await confirm({ tone: 'danger', title: `Delete this ${isPo ? 'purchase order' : 'Tech Pack'}?`, confirmLabel: 'Delete', detail: item.filename,
      message: `${item.status === 'approved' ? 'It has already been approved. ' : ''}This permanently removes the PDF, ${isPo
        ? 'the extracted contracts and size quantities, and the page images.'
        : `the extracted Wovens and Knits data, and the page images. ${kept ? `Its ${kept} purchase ${kept === 1 ? 'order stays' : 'orders stay'} in the Purchase Orders tab without a Tech Pack.` : 'Purchase orders submitted for it are kept.'}`} This can't be undone.` })) return;
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
          setSelectedId(null); setDocumentData(null);
        }
      }
      setMessage(`${item.filename} was deleted.`);
    } catch (e) { setError(`Delete failed: ${e.message}`); }
    finally { setBusy(false); refreshLists(); }
  }

  /**
   * Purpose: Upload a Tech Pack from the sidebar, start its style and refresh the lists.
   * Input: kind - 'techpack'; file - the chosen PDF.
   * Output: a promise of true when accepted, or false when rejected (so the sidebar keeps the chosen file).
   */
  async function onUpload(kind, file) {
    setBusy(true); setError(''); setMessage('');
    try {
      const row = await api.upload(file);
      setDocumentData(null); selectDocument(row.id);
      setPoId(null); setStage('techpack'); setTab('style');
      setMessage('Upload saved. Extraction queued.');
      refreshLists();
      return true;
    } catch (e) {
      setError(`Tech Pack: ${e.message}`);
      return false;
    } finally { setBusy(false); }
  }

  /**
   * Purpose: Upload a purchase order for the open style; the server checks that the Tech Pack has finished.
   * Input: file - the chosen PDF.
   * Output: a promise of true when accepted, or false when rejected.
   */
  async function onUploadPo(file) {
    setBusy(true); setError(''); setMessage('');
    try {
      const row = await poApi.upload(file, selectedIdRef.current);
      setPoId(row.id);
      setMessage('Upload saved. Extraction queued.');
      refreshLists();
      return true;
    } catch (e) {
      setError(`PO: ${e.message}`);
      return false;
    } finally { setBusy(false); }
  }

  async function saveBomChanges(payload) {
    const id = selectedId;
    setBusy(true); setMessage(''); setError('');
    try {
      await api.save(id, payload);
      await refreshDocument(id);
      await refreshLists();
      if (selectedIdRef.current === id) setMessage('Changes saved. Review the corrected BOM, then approve it.');
    } finally { setBusy(false); }
  }

  /**
   * Purpose: Approve the selected Tech Pack's extraction after the user confirms they checked it against the PDF.
   * Input: none (uses the selected Tech Pack).
   * Output: a promise that finishes when approved or cancelled; failures show an error message.
   */
  async function onApprove() {
    if (!await confirm({ title: 'Approve this BOM?', confirmLabel: 'Approve',
      message: 'Confirm you have checked the Wovens and Knits values against the original PDF.', detail: current?.filename })) return;
    setBusy(true); setMessage(''); setError('');
    try {
      await api.approve(selectedId);
      await refreshDocument(selectedId);
      await refreshLists();
      if (selectedIdRef.current !== selectedId) return;
      // In Create Marker Plan the next step is the purchase order, which opens now that the Tech Pack is approved.
      if (tab === 'style') { setStage('po'); setMessage('Tech Pack approved. Now submit its purchase order.'); }
      else setMessage('Extraction approved.');
    } catch (e) { if (selectedIdRef.current === selectedId) setError(e.message); }
    finally { setBusy(false); }
  }

  const current = documentData;
  const inStyle = tab === 'style';
  const styles = enrichStyles(techPacks, purchaseOrders);
  const listed = techPacks.find(item => item.id === selectedId);
  const orders = linkedOrders(purchaseOrders, selectedId);
  const steps = styleSteps(listed || current, orders);
  const stageOpen = steps.find(step => step.key === stage)?.state !== 'locked';
  const activePoId = orders.some(order => order.id === poId) ? poId : orders[0]?.id;
  // Each PO in the library says which style it belongs to.
  const libraryOrders = purchaseOrders.map(order => {
    const parent = techPacks.find(item => item.id === order.tech_pack_id);
    return { ...order, linked_to: parent ? (techPackIds(parent) || parent.filename) : 'No Tech Pack' };
  });
  const openPo = purchaseOrders.find(order => order.id === poId);
  const owner = techPacks.find(item => item.id === openPo?.tech_pack_id);
  const ids = techPackIds(current?.extraction);
  const TITLES = { style: 'Create Marker Plan', techpack: 'Tech Packs', po: 'Purchase Orders', plan: 'Marker Plans' };
  const heading = tab === 'plan' ? 'Saved marker plans' : tab === 'po' ? 'Purchase order review' : tab === 'techpack' ? 'Tech Pack review'
    : current ? (ids || current.filename) : 'Start with a Tech Pack';
  /** Purpose: Switch between the four views from the left navigation, keeping the address in step. Input: key - 'style', 'techpack', 'po' or 'plan'. Output: nothing. */
  function goTab(key) {
    setBrowsingDocuments(false);
    setTab(key);
    if (typeof window !== 'undefined') window.history.replaceState(null, '', workspaceHref(key));
  }
  /** Purpose: Open a library's full list on its own page. Input: kind - 'techpack' or 'po'. Output: nothing. */
  function browseDocuments(kind) {
    setTab(kind);
    setBrowsingDocuments(true);
    libraryEntry.current = true;
    window.history.pushState(null, '', `/?tab=${kind}&view=documents`);
    window.scrollTo(0, 0);
  }
  function backToWorkspace() {
    if (libraryEntry.current) {
      libraryEntry.current = false;
      window.history.back();
    } else goTab(tab);
  }
  /** Purpose: Carry on with the open Tech Pack in Create Marker Plan: at its purchase order once extraction is done, else at the Tech Pack. Input: none. Output: nothing. */
  function continueStyle() {
    openStyle(selectedId, isApproved(listed || current) ? 'po' : 'techpack');
    goTab('style');
  }
  /** Purpose: Open a purchase order's style in Create Marker Plan, at the PO stage with that PO open. Input: none. Output: nothing. */
  function openOwnerStyle() {
    openStyle(owner.id, 'po');
    setPoId(openPo.id);
    goTab('style');
  }
  const libraryKind = tab === 'po' ? 'po' : 'techpack';
  const planProps = current ? { selectedKeys: planMaterialsByDocument[current.id] || [],
    purchaseOrders: planOrders(orders), poSelection: planPosByDocument[current.id],
    onPoChange: value => setPlanPosByDocument(previous => ({ ...previous, [current.id]: value })),
    plan: planCuttingByDocument[current.id],
    onPlanChange: update => setPlanCuttingByDocument(previous => ({ ...previous, [current.id]: update(previous[current.id]) })),
    onChange: keys => setPlanMaterialsByDocument(previous => ({ ...previous, [current.id]: keys })) } : undefined;
  const techPackView = marker => loading ? <div className="loading-workspace" role="status"><span className="spinner"/> Loading your Tech Pack…</div> : current &&
    <DocumentWorkspace key={`${current.id}:${marker ? 'plan' : 'review'}`} current={current} busy={busy} onApprove={onApprove}
      canEdit={can(user, 'techpacks', 'edit')} onSaveData={saveBomChanges} markerSelection={marker ? planProps : undefined}/>;
  /** Purpose: The welcome card of a view with nothing open. Input: Icon, eyebrow, title, text and an optional list of short step labels. Output: the card. */
  const welcome = (Icon, eyebrow, title, text, labels) => <section className="welcome">
    <div className="document-illustration" aria-hidden="true"><span className="paper-back"/><span className="paper-front"><Icon size={40}/><i/><i/><i/></span><span className="paper-check"><Check size={18}/></span></div>
    <span className="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{text}</p>
    {labels && <div className="welcome-steps">{labels.map((label, index) => <span key={label}><b>{`0${index + 1}`}</b> {label}</span>)}</div>}
  </section>;
  return <>
    {dialog}
    <AppShell user={user} onSignOut={onSignOut} active={tab} title={browsingDocuments ? (libraryKind === 'po' ? 'All purchase orders' : 'All Tech Packs') : TITLES[tab]} onNavigate={goTab}
      counts={{ techpack: techPacks.length, po: purchaseOrders.length }}>
      {browsingDocuments && <DocumentLibrary key={libraryKind} kind={libraryKind} items={libraryKind === 'po' ? libraryOrders : styles}
        selectedId={libraryKind === 'po' ? poId : selectedId} busy={busy} error={error} message={message}
        onBack={backToWorkspace} onDelete={onDelete} onSelect={(kind, id) => { onSelect(kind, id); goTab(tab); }}/>}
      <div hidden={browsingDocuments}>
      {inStyle && <Sidebar busy={busy || loading} canUpload={can(user, 'techpacks', 'edit')} onUpload={onUpload}/>}
      {tab === 'techpack' && <ArchiveList kind="techpack" items={styles} selectedId={selectedId} busy={busy || loading}
        onSelect={onSelect} onDelete={onDelete} onBrowse={browseDocuments}/>}
      {tab === 'po' && <ArchiveList kind="po" items={libraryOrders} selectedId={poId} busy={busy}
        onSelect={onSelect} onDelete={onDelete} onBrowse={browseDocuments}/>}
      <main className="workspace">
        <div className="workspace-heading"><div className="workspace-heading-copy">
          <div><div className="breadcrumb">Workspace <span>/</span> {TITLES[tab]}{inStyle && current && <><span>/</span>{current.filename}</>}</div><h2>{heading}</h2></div>
        </div></div>
        {error &&<div className="alert error" role="alert"><AlertTriangle size={18}/><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}>Dismiss</button></div>}
        {message && <div className="alert success" role="status"><Check size={18}/><span>{message}</span><button aria-label="Dismiss message" onClick={() => setMessage('')}>Dismiss</button></div>}

        {tab === 'plan' && <SavedMarkerPlans canEdit={can(user, 'marker_plan', 'edit')} refreshKey={`${planCuttingByDocument[selectedId]?.job?.id || ''}:${planCuttingByDocument[selectedId]?.job?.status || ''}`}/>}

        {tab === 'techpack' && (selectedId ? <>
          {can(user, 'techpacks') && <div className="po-link-note"><span>{orders.length ? `${orders.length} purchase ${orders.length === 1 ? 'order' : 'orders'} submitted for this Tech Pack.` : 'No purchase order submitted for this Tech Pack yet.'}</span>
            <button type="button" className="secondary-button" onClick={continueStyle}>Continue in Create Marker Plan</button></div>}
          {techPackView(false)}</>
          : welcome(ScanText, 'TECH PACKS', 'Choose a Tech Pack to review.', 'Every Tech Pack you have uploaded is listed above. Open one to check, edit, approve or download it. New Tech Packs are added in Create Marker Plan.'))}

        {tab === 'po' && (poId ? <>
          <div className="po-link-note">{owner
            ? <><span>Tech Pack: <b>{owner.filename}</b>{techPackIds(owner) ? ` · ${techPackIds(owner)}` : ''}</span>
              {can(user, 'techpacks') && <button type="button" className="secondary-button" onClick={openOwnerStyle}>Open in Create Marker Plan</button>}</>
            : <span>This purchase order is not linked to a Tech Pack.</span>}</div>
          <PurchaseOrderPanel key={poId} id={poId} canEdit={can(user, 'purchase_orders', 'edit')} onChanged={refreshLists}/>
        </> : welcome(ReceiptText, 'PURCHASE ORDERS', 'Choose a purchase order to review.', 'Every purchase order is listed above with the Tech Pack it belongs to. New purchase orders are submitted inside a style in Create Marker Plan.'))}

        {inStyle && selectedId && <>
          <ol className="marker-workflow style-steps" aria-label="Style stages">
            {steps.map((step, index) => <li key={step.key} className={step.state === 'complete' ? 'complete' : stage === step.key && step.state !== 'locked' ? 'current' : ''}>
              <span>{step.state === 'locked' ? <Lock size={13}/> : index + 1}</span>
              <button type="button" className="step-link" disabled={step.state === 'locked'} aria-current={stage === step.key ? 'step' : undefined}
                title={step.state === 'locked' ? lockedReason(step.key, listed || current) : undefined} onClick={() => setStage(step.key)}>{step.label}</button></li>)}
          </ol>
          {!stageOpen && <p className="side-hint style-lock" role="status"><Lock size={14}/> {lockedReason(stage, listed || current)}</p>}
          {stage === 'po' && stageOpen && (can(user, 'purchase_orders') ? <>
            <StylePurchaseOrders techPack={{ ...(listed || {}), ...current?.extraction, status: (listed || current)?.status }} orders={orders} selectedId={activePoId} busy={busy}
              canUpload={can(user, 'purchase_orders', 'edit')} canDelete={can(user, 'purchase_orders', 'edit')}
              onSelect={setPoId} onUpload={onUploadPo} onDelete={item => onDelete('po', item)}/>
            {activePoId && <PurchaseOrderPanel key={activePoId} id={activePoId} refreshKey={current?.status}
              canEdit={can(user, 'purchase_orders', 'edit')} onChanged={refreshLists}/>}
          </> : <section className="welcome"><p>You don't have access to purchase orders. Ask an administrator.</p></section>)}
          {stage !== 'po' && stageOpen && (stage === 'plan' && !can(user, 'marker_plan')
            ? <section className="welcome"><p>You don't have access to marker plans. Ask an administrator.</p></section>
            : techPackView(stage === 'plan'))}
        </>}
        {inStyle && !selectedId && welcome(ScanText, 'FROM TECH PACK TO MARKER PLAN', 'Start with a Tech Pack.',
          'Upload a Tech Pack above. Then submit its purchase order and create the marker plan, all in the same place. To carry on with a saved Tech Pack, open it in the Tech Packs tab and choose Continue.',
          ['Upload Tech Pack', 'Submit its PO', 'Approve both', 'Marker plan'])}
        <footer className="workspace-footer"><ShieldCheck size={13}/> Human review keeps your material data accurate.</footer>
      </main>
      </div>
    </AppShell>
  </>;
}