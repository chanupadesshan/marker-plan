import React, { useEffect, useRef } from 'react';
import { ShieldCheck, Trash2 } from 'lucide-react';

const ICONS = { primary: ShieldCheck, danger: Trash2 };

/**
 * Purpose: In-page replacement for the browser's confirm box. The safe choice (Cancel) is focused for
 * destructive actions so a stray Enter cannot delete anything; Escape and a backdrop click also cancel.
 * Input: props - open (show it or not), title, message, detail (e.g. a file name), confirmLabel,
 * cancelLabel, tone ('primary' or 'danger'), busy (disables the buttons), onConfirm, onCancel.
 * Output: the dialog element, or nothing when open is false.
 */
export default function ConfirmDialog({ open, title, message, detail, confirmLabel = 'Confirm', cancelLabel = 'Cancel',
  tone = 'primary', busy = false, onConfirm, onCancel }) {
  const card = useRef(null);
  const confirmButton = useRef(null);
  const cancelButton = useRef(null);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement;
    (tone === 'danger' ? cancelButton : confirmButton).current?.focus();
    return () => { if (previous instanceof HTMLElement) previous.focus(); };
  }, [open, tone]);
  if (!open) return null;
  const Icon = ICONS[tone] || ICONS.primary;
  /**
   * Purpose: Handle the keyboard inside the dialog: Escape cancels, Tab stays within the dialog's buttons.
   * Input: event - the keydown event.
   * Output: nothing.
   */
  function onKeyDown(event) {
    if (event.key === 'Escape') { event.stopPropagation(); onCancel?.(); return; }
    if (event.key !== 'Tab') return;
    // Keep keyboard focus inside the dialog.
    const buttons = [...card.current.querySelectorAll('button:not(:disabled)')];
    if (!buttons.length) return;
    const first = buttons[0], last = buttons[buttons.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
  return <div className="dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onCancel?.(); }}>
    <div ref={card} className={`dialog-card ${tone}`} role="alertdialog" aria-modal="true" aria-labelledby="dialog-title"
      aria-describedby="dialog-message" onKeyDown={onKeyDown}>
      <span className="dialog-icon" aria-hidden="true"><Icon size={22}/></span>
      <h2 id="dialog-title">{title}</h2>
      <p id="dialog-message">{message}</p>
      {detail && <div className="dialog-detail" title={detail}>{detail}</div>}
      <div className="dialog-actions">
        <button ref={cancelButton} type="button" className="secondary-button" disabled={busy} onClick={onCancel}>{cancelLabel}</button>
        <button ref={confirmButton} type="button" className={tone === 'danger' ? 'danger-button' : 'primary-button'} disabled={busy} onClick={onConfirm}>{confirmLabel}</button>
      </div>
    </div>
  </div>;
}
