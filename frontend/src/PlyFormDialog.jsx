import React, { useEffect, useRef, useState } from 'react';
import { PLY_COLUMNS, PLY_MAX_TEXT, validatePly } from './plies.js';

/**
 * Purpose: A dialog with the three fields for adding a ply row or editing an existing one. It checks the
 * values before saving (Customer a whole number, Material required) and shows a server error if saving fails.
 * Input: props - mode: 'add' or 'edit'; initial: the row being edited (or nothing when adding); busy: a save is
 * running; error: a message from a failed save; onSave(values): called with { col_b, col_c, col_d } as typed;
 * onCancel(): called to close without saving.
 * Output: the dialog element. Mount it only while it should be open, so each opening starts with fresh fields.
 */
export default function PlyFormDialog({ mode, initial, busy = false, error = '', onSave, onCancel }) {
  const [values, setValues] = useState({
    col_b: initial?.col_b ?? '', col_c: initial?.col_c ?? '', col_d: initial?.col_d ?? '' });
  const [errors, setErrors] = useState({});
  const first = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    first.current?.focus();
    return () => { if (previous instanceof HTMLElement) previous.focus(); };
  }, []);

  /**
   * Purpose: Check the fields and, if they are valid, hand them to the parent to save.
   * Input: event - the form's submit event.
   * Output: nothing.
   */
  function submit(event) {
    event.preventDefault();
    const found = validatePly(values);
    setErrors(found);
    if (!Object.keys(found).length) onSave(values);
  }

  return <div className="dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onCancel(); }}
    onKeyDown={event => { if (event.key === 'Escape' && !busy) onCancel(); }}>
    <form className="dialog-card form" role="dialog" aria-modal="true" aria-labelledby="ply-form-title" onSubmit={submit} noValidate>
      <h2 id="ply-form-title">{mode === 'edit' ? `Edit ply #${initial?.id}` : 'Add a ply'}</h2>
      {PLY_COLUMNS.map((column, index) => <label className="ply-field" key={column.key}>
        <span>{column.label}{column.key === 'col_d' && <small> (optional)</small>}</span>
        <input ref={index === 0 ? first : undefined} name={column.key} value={values[column.key]} disabled={busy}
          inputMode={column.key === 'col_b' ? 'numeric' : undefined} maxLength={column.key === 'col_b' ? 12 : PLY_MAX_TEXT + 20}
          aria-invalid={errors[column.key] ? 'true' : undefined} aria-describedby={errors[column.key] ? `err-${column.key}` : undefined}
          onChange={event => setValues(previous => ({ ...previous, [column.key]: event.target.value }))}/>
        {errors[column.key] && <em className="field-error" id={`err-${column.key}`}>{errors[column.key]}</em>}
      </label>)}
      {error && <div className="alert error" role="alert"><span>{error}</span></div>}
      <div className="dialog-actions">
        <button type="button" className="secondary-button" disabled={busy} onClick={onCancel}>Cancel</button>
        <button type="submit" className="primary-button" disabled={busy}>{busy ? 'Saving…' : mode === 'edit' ? 'Save changes' : 'Add ply'}</button>
      </div>
    </form>
  </div>;
}
