import React, { useEffect, useState } from 'react';
import { poApi } from './api.js';
import PurchaseOrderWorkspace from './PurchaseOrderWorkspace.jsx';
import { useConfirm } from './useConfirm.jsx';

/**
 * Purpose: Load one purchase order and handle its actions (approve, save corrections, retry), polling
 * while it is still being extracted. Keyed by document id in App, so a late response cannot replace a newer PO.
 * Input: props - id: the PO to show; refreshKey: a value whose change triggers a reload.
 * Output: the PO review screen, or a loading message.
 */
export default function PurchaseOrderPanel({ id, refreshKey, canEdit = false, onChanged }) {
  const [current, setCurrent] = useState(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [confirm, dialog] = useConfirm();
  useEffect(() => {
    let cancelled = false;
    let timer;
    /** Purpose: Fetch the PO and schedule another check while it is queued or processing (or after an error). Input: none. Output: nothing. */
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
  /**
   * Purpose: Run a PO action. Approving first asks the user to confirm in a dialog.
   * Input: kind - 'approve', 'retry' (continue a failed extraction) or 'extractSkipped' (read the pages skipped as not matching the Tech Pack).
   * Output: a promise that finishes when done; the result or error is shown on screen.
   */
  async function action(kind) {
    if (kind === 'approve' && !await confirm({ title: 'Approve this purchase order?', confirmLabel: 'Approve PO', detail: current?.filename,
      message: 'Confirm you have checked the contracts, IDs and size quantities against the original PDF.' })) return;
    setBusy(true); setError(''); setMessage('');
    try {
      if (kind === 'retry' || kind === 'extractSkipped') {
        const queued = await (kind === 'retry' ? poApi.retry(id) : poApi.extractSkipped(id));
        setCurrent(previous => ({ ...previous, ...queued, progress: null }));
        setReloadKey(value => value + 1);
        onChanged?.();
        setMessage(kind === 'retry' ? 'Retry queued. Completed pages will be kept.' : 'Extracting the skipped pages. Pages already read are kept.');
        return;
      }
      else await poApi.approve(id);
      setCurrent(await poApi.get(id));
      onChanged?.();
      setMessage('PO approved.');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function savePoChanges(payload) {
    setBusy(true); setError(''); setMessage('');
    try {
      await poApi.save(id, payload);
      setCurrent(await poApi.get(id));
      onChanged?.();
      setMessage('Changes saved. Review the corrected purchase order, then approve it.');
    } finally { setBusy(false); }
  }
  return <>
    {dialog}
    {error && <div className="alert error" role="alert">{error}</div>}
    {message && <div className="alert success" role="status">{message}</div>}
    {current ? <PurchaseOrderWorkspace current={current} busy={busy} canEdit={canEdit}
      onApprove={() => action('approve')} onSaveData={savePoChanges} onRetry={() => action('retry')} onExtractSkipped={() => action('extractSkipped')}/>
      : <div className="loading-workspace" role="status">Loading purchase order…</div>}
  </>;
}
