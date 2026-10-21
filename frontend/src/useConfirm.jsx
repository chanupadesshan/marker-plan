import React, { useCallback, useRef, useState } from 'react';
import ConfirmDialog from './ConfirmDialog.jsx';

// const [confirm, dialog] = useConfirm();  if (!await confirm({ title, message })) return;  ...render {dialog}
export function useConfirm() {
  const [options, setOptions] = useState(null);
  const resolver = useRef(null);
  const confirm = useCallback(next => new Promise(resolve => {
    resolver.current?.(false);
    resolver.current = resolve;
    setOptions(next);
  }), []);
  const settle = answer => {
    resolver.current?.(answer);
    resolver.current = null;
    setOptions(null);
  };
  const dialog = <ConfirmDialog {...options} open={Boolean(options)} onConfirm={() => settle(true)} onCancel={() => settle(false)}/>;
  return [confirm, dialog];
}
