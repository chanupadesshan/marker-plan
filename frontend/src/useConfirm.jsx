import React, { useCallback, useRef, useState } from 'react';
import ConfirmDialog from './ConfirmDialog.jsx';

/**
 * Purpose: Let a component ask the user to confirm something with an in-page dialog and wait for the answer.
 * Usage: const [confirm, dialog] = useConfirm();  if (!await confirm({ title, message })) return;  ...and render {dialog}.
 * Input: none.
 * Output: a pair [confirm, dialog]. confirm(options) opens the dialog (options: title, message, detail,
 * confirmLabel, cancelLabel, tone) and returns a promise of true (confirmed) or false (cancelled);
 * dialog is the element to render.
 */
export function useConfirm() {
  const [options, setOptions] = useState(null);
  const resolver = useRef(null);
  /**
   * Purpose: Open the dialog and wait for the answer. A still-open earlier question is answered "no".
   * Input: next - the dialog options (title, message, detail, confirmLabel, cancelLabel, tone).
   * Output: a promise of true (confirmed) or false (cancelled).
   */
  const confirm = useCallback(next => new Promise(resolve => {
    resolver.current?.(false);
    resolver.current = resolve;
    setOptions(next);
  }), []);
  /** Purpose: Close the dialog and answer the waiting question. Input: answer - true or false. Output: nothing. */
  const settle = answer => {
    resolver.current?.(answer);
    resolver.current = null;
    setOptions(null);
  };
  const dialog = <ConfirmDialog {...options} open={Boolean(options)} onConfirm={() => settle(true)} onCancel={() => settle(false)}/>;
  return [confirm, dialog];
}
