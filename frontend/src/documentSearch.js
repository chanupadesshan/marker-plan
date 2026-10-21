// Everything a user might type to find a document: file name, status and the extracted identifiers.
export function searchText(item) {
  return [item.filename, item.status?.replaceAll('_', ' '), item.style_number, item.tech_pack_number,
    ...(item.contract_numbers || []), ...(item.tech_pack_references || [])]
    .filter(Boolean).join(' ').toLowerCase();
}

// Every whitespace-separated term must match somewhere, in any order.
export function filterDocuments(items, query) {
  const terms = (query || '').toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return items;
  return items.filter(item => {
    const text = searchText(item);
    return terms.every(term => text.includes(term));
  });
}

export function inProgress(items) {
  return items.some(item => ['queued', 'processing'].includes(item.status));
}
