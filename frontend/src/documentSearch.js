/**
 * Purpose: Collect everything a user might type to find a document: file name, status and extracted identifiers.
 * Input: item - a Tech Pack or PO list entry.
 * Output: one lowercase string to search in.
 */
export function searchText(item) {
  return [item.filename, item.status?.replaceAll('_', ' '), item.style_number, item.design_number, ...(item.design_numbers || []), item.tech_pack_number,
    item.linked_to, ...(item.contract_numbers || []), ...(item.tech_pack_references || [])]
    .filter(Boolean).join(' ').toLowerCase();
}

/**
 * Purpose: Keep only the documents that match a search. Every whitespace-separated word must match somewhere, in any order.
 * Input: items - a list of Tech Pack or PO entries; query - the typed text.
 * Output: the matching items, or the same list when the query is blank.
 */
export function filterDocuments(items, query) {
  const terms = (query || '').toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return items;
  return items.filter(item => {
    const text = searchText(item);
    return terms.every(term => text.includes(term));
  });
}

/** Newest uploads first; missing dates sort last and the source list stays unchanged. */
export function latestDocuments(items, limit = 5) {
  const timestamp = item => Date.parse(item.created_at) || 0;
  return [...items].sort((a, b) => timestamp(b) - timestamp(a)).slice(0, limit);
}

/**
 * Purpose: Tell whether any document is still being extracted, so the lists keep refreshing.
 * Input: items - a list of Tech Pack or PO entries.
 * Output: true when any is queued or processing.
 */
export function inProgress(items) {
  return items.some(item => ['queued', 'processing'].includes(item.status));
}

/** Keep every Tech Pack selectable, including BOM-only PDFs without a printed TP number. */
export function filterTechPacks(items, query) {
  const normalize = value => String(value ?? '').trim().toLowerCase()
    .replace(/^(?:tech\s*pack|tp)[\s:#-]*/i, '').replace(/\s+/g, '');
  const term = normalize(query);
  return items.filter(item => !term || normalize(item.tech_pack_number).includes(term)
    || normalize(item.filename).includes(term));
}
