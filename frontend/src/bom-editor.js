// Drafts retain extraction metadata; page tables remain the server's source of truth.
export function createBomDraft(extraction) {
  const draft = structuredClone(extraction);
  if (!draft.page_tables?.length) draft.materials ||= [];
  return draft;
}

export function bomTables(draft) {
  return draft.page_tables?.length ? draft.page_tables : [{ materials: draft.materials || [] }];
}

export function bomPayload(draft, original = draft) {
  const payload = structuredClone(draft);
  if (payload.page_tables?.length) {
    delete payload.materials;
    for (const [index, table] of payload.page_tables.entries()) {
      const headers = new Map();
      for (const row of table.materials || []) for (const variant of row.colorways || []) {
        const key = variant.code || '';
        if (!headers.has(key)) headers.set(key, { code: variant.code ?? null, name: variant.name ?? null });
      }
      // Printed headings with no assigned variant still belong to the source table.
      // Only headings that previously had variants can be removed by row/colour edits.
      const originalTable = original.page_tables?.[index];
      const assigned = new Set((originalTable?.materials || []).flatMap(row => (row.colorways || []).map(variant => variant.code || '')));
      for (const header of table.colorway_headers || []) {
        const key = header.code || '';
        if (!assigned.has(key) && !headers.has(key)) headers.set(key, header);
      }
      table.colorway_headers = [...headers.values()];
    }
  }
  return payload;
}

export function validateBomDraft(draft) {
  const errors = {};
  const tables = bomTables(draft);
  if (!tables.some(table => table.materials?.length)) errors.materials = 'Add at least one material before saving.';
  tables.forEach((table, ti) => (table.materials || []).forEach((row, ri) => {
    const key = `${ti}.${ri}`;
    if (!String(row.material_code || '').trim()) errors[`${key}.material_code`] = 'Enter a material code.';
    const quantity = String(row.quantity ?? '').trim();
    if (!/^\d+(?:[.,]\d+)?$/.test(quantity) || Number(quantity.replace(',', '.')) <= 0) {
      errors[`${key}.quantity`] = 'Enter a quantity greater than zero (for example, 0.32).';
    }
    if (!String(row.unit || '').trim()) errors[`${key}.unit`] = 'Enter a unit, such as m or pcs.';
  }));
  return errors;
}
