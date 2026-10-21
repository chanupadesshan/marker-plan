import React, { useEffect, useState } from 'react';
import { poApi } from './api.js';
import PurchaseOrderWorkspace from './PurchaseOrderWorkspace.jsx';
import { useConfirm } from './useConfirm.jsx';

// Keyed by document ID in App: cleanup prevents late responses replacing a new PO.
export default function PurchaseOrderPanel({ id, refreshKey }) {
  const [current, setCurrent] = useState(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [showEditor, setShowEditor] = useState(false);
  const [editor, setEditor] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [confirm, dialog] = useConfirm();
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
  }, [id, refreshKey, reloadKey]);
  async function action(kind) {
    if (kind === 'approve' && !await confirm({ title: 'Approve this purchase order?', confirmLabel: 'Approve PO', detail: current?.filename,
      message: 'Confirm you have checked the contracts, IDs and size quantities against the original PDF.' })) return;
    setBusy(true); setError(''); setMessage('');
    try {
      if (kind === 'save') await poApi.save(id, JSON.parse(editor));
      else if (kind === 'retry') {
        const queued = await poApi.retry(id);
        setCurrent(previous => ({ ...previous, ...queued }));
        setReloadKey(value => value + 1);
        setShowEditor(false);
        setMessage('Retry queued. Completed pages will be kept.');
        return;
      }
      else await poApi.approve(id);
      setCurrent(await poApi.get(id)); setShowEditor(false);
      setMessage(kind === 'save' ? 'PO corrections saved.' : kind === 'retry' ? 'Retry queued. Completed pages will be kept.' : 'PO approved.');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <>
    {dialog}
    {error && <div className="alert error" role="alert">{error}</div>}
    {message && <div className="alert success" role="status">{message}</div>}
    {current ? <PurchaseOrderWorkspace current={current} busy={busy} showEditor={showEditor} editor={editor}
      onApprove={() => action('approve')} onSave={() => action('save')} onRetry={() => action('retry')} onEditorChange={setEditor}
      onToggleEditor={() => { setEditor(JSON.stringify({ orders: current.extraction?.orders || [] }, null, 2)); setShowEditor(!showEditor); }}/>
      : <div className="loading-workspace" role="status">Loading purchase order…</div>}
  </>;
}
