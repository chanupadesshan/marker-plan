// Each physical BOM row is selectable, including repeated codes on different pages.
export function materialTables(extraction) {
  return extraction?.page_tables?.length ? extraction.page_tables : [{ materials: extraction?.materials || [] }];
}

export function materialRowKey(table, tableIndex, rowIndex) {
  // Include the source content so editing/reordering a row cannot retarget a prior choice.
  return JSON.stringify([tableIndex, table.page_number ?? null, rowIndex, table.materials[rowIndex]]);
}

/** Purpose: Which section a material row belongs to. Input: row - a material. Output: 'knits' or 'wovens' (rows saved before Knits were read are Wovens). */
export const materialCategory = row => (row?.category === 'knits' ? 'knits' : 'wovens');

/** Purpose: The rows a marker plan can be built from. Input: extraction. Output: every Wovens and Knits row, each with its stable key, page and category. */
export function markerMaterialRows(extraction) {
  return materialTables(extraction).flatMap((table, tableIndex) => (table.materials || []).map((row, rowIndex) => ({
    key: materialRowKey(table, tableIndex, rowIndex), row, pageNumber: table.page_number, category: materialCategory(row),
  })));
}

export function updateMaterialSelection(rows, selectedKeys, key, checked) {
  const selected = new Set(selectedKeys);
  if (checked) selected.add(key); else selected.delete(key);
  return rows.filter(row => selected.has(row.key)).map(row => row.key);
}

export function filterMarkerMaterials(rows, query) {
  const code = String(query || '').trim().toLowerCase();
  return code ? rows.filter(entry => String(entry.row.material_code || '').toLowerCase().includes(code)) : rows;
}

export function selectVisibleMaterials(rows, selectedKeys, visibleRows) {
  const selected = new Set([...selectedKeys, ...visibleRows.map(entry => entry.key)]);
  return rows.filter(entry => selected.has(entry.key)).map(entry => entry.key);
}
