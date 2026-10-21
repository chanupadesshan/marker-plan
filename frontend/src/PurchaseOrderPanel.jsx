import React, { useEffect, useState } from 'react';
import { poApi } from './api.js';
import PurchaseOrderWorkspace from './PurchaseOrderWorkspace.jsx';

// Keyed by document ID in App: cleanup prevents late responses replacing a new PO.
export default function PurchaseOrderPanel({ id, refreshKey }) {
  const [current, setCurrent] = useState(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [showEditor, setShowEditor] = useState(false);
  const [editor, setEditor] = useState('');
  useEffect(() => {
    let cancelled = false;
    let timer;
    async function load() {
      try {
        const row = await poApi.get(id);
        if (cancelled) return;
        setCurrent(row); setError('');
        if (['queued', 'processing'].includes(row.status)) timer = setTimeout(load, 3000);
      } catch (e) {
        if (!cancelled) { setError(e.message); timer = setTimeout(load, 5000); }
      }
    }
    load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [id, refreshKey]);
  async function action(kind) {
    if (kind === 'approve' && !window.confirm('Have you checked the PO values against the original PDF?')) return;
    setBusy(true); setError(''); setMessage('');
    try {
      if (kind === 'save') await poApi.save(id, JSON.parse(editor));
      else await poApi.approve(id);
      setCurrent(await poApi.get(id)); setShowEditor(false);
      setMessage(kind === 'save' ? 'PO corrections saved.' : 'PO approved.');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <>
    {error && <div className="alert error" role="alert">{error}</div>}
    {message && <div className="alert success" role="status">{message}</div>}
    {current ? <PurchaseOrderWorkspace current={current} busy={busy} showEditor={showEditor} editor={editor}
      onApprove={() => action('approve')} onSave={() => action('save')} onEditorChange={setEditor}
      onToggleEditor={() => { setEditor(JSON.stringify({ orders: current.extraction?.orders || [] }, null, 2)); setShowEditor(!showEditor); }}/>
      : <div className="loading-workspace" role="status">Loading purchase order…</div>}
  </>;
}
