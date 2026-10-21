// Shared labels for the dashboard headings and add/edit form fields.
export const PLY_COLUMNS = [
  { key: 'col_b', label: 'Customer' },
  { key: 'col_c', label: 'Material' },
  { key: 'col_d', label: 'Maximum plies' },
];

export const PLY_MAX_TEXT = 100;
export const PLY_PAGE_SIZE = 25;

/**
 * Purpose: Tell whether the current address is the Plies dashboard, so the app can show it instead of the review screen.
 * Input: pathname - the page's path, e.g. '/plies'.
 * Output: true for '/plies' (with or without a trailing slash), otherwise false.
 */
export function isPliesPath(pathname) {
  return /^\/plies\/?$/.test(pathname || '');
}

/**
 * Purpose: Keep only the rows that match a search. Every whitespace-separated word must match
 * the id, Customer, Material or Maximum plies, in any order.
 * Input: rows - the ply rows; query - the typed text.
 * Output: the matching rows, or the same list when the query is blank.
 */
export function filterPlies(rows, query) {
  const terms = (query || '').toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return rows;
  return rows.filter(row => {
    const text = [row.id, row.col_b, row.col_c, row.col_d].filter(value => value != null).join(' ').toLowerCase();
    return terms.every(term => text.includes(term));
  });
}

/**
 * Purpose: Check the add/edit form before sending it, with the same rules the server enforces.
 * Input: values - the form's text fields { col_b, col_c, col_d }.
 * Output: an object of messages keyed by field name; empty when everything is valid.
 */
export function validatePly(values) {
  const errors = {};
  const b = String(values.col_b ?? '').trim();
  const c = String(values.col_c ?? '').trim();
  const d = String(values.col_d ?? '').trim();
  if (!b) errors.col_b = 'Customer is required';
  else if (!/^-?\d+$/.test(b)) errors.col_b = 'Customer must be a whole number';
  if (!c) errors.col_c = 'Material is required';
  else if (c.length > PLY_MAX_TEXT) errors.col_c = `Material must be ${PLY_MAX_TEXT} characters or fewer`;
  if (d.length > PLY_MAX_TEXT) errors.col_d = `Maximum plies must be ${PLY_MAX_TEXT} characters or fewer`;
  return errors;
}

/**
 * Purpose: Turn the form's text fields into the request body the server expects.
 * Input: values - the form's text fields { col_b, col_c, col_d }.
 * Output: { col_b: a number, col_c: trimmed text, col_d: trimmed text or null when blank }.
 */
export function toPayload(values) {
  const d = String(values.col_d ?? '').trim();
  return { col_b: Number(String(values.col_b).trim()), col_c: String(values.col_c ?? '').trim(), col_d: d || null };
}

/**
 * Purpose: Cut a list into pages for the table.
 * Input: rows - the rows to show; page - the wanted page (1-based; kept within range); size - rows per page.
 * Output: { items, page, pages, from, to }: that page's rows, the page actually used, the page count, and the
 * 1-based position of the first and last row shown (0 and 0 when there are none).
 */
export function pageSlice(rows, page, size = PLY_PAGE_SIZE) {
  const pages = Math.max(1, Math.ceil(rows.length / size));
  const current = Math.min(Math.max(1, page), pages);
  const start = (current - 1) * size;
  const items = rows.slice(start, start + size);
  return { items, page: current, pages, from: items.length ? start + 1 : 0, to: start + items.length };
}
