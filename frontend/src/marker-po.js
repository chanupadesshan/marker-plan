export function changePoMode(ids, mode) {
  return mode === 'single' ? ids.slice(0, 1) : [...ids];
}

export function togglePlanPo(ids, id, checked, mode) {
  if (mode === 'single') return checked ? [id] : [];
  return checked ? [...new Set([...ids, id])] : ids.filter(value => value !== id);
}
const normalize = value => String(value ?? '').trim().toLowerCase();
const normalizeTechPack = value => normalize(value).replace(/^(?:tech\s*pack|tp)[\s:#-]*/i, '').replace(/\s+/g, '');

export function allPlanOrders(documents) {
  return documents.flatMap(document => (document.extraction?.orders || []).map((order, index) => ({
      ...order, id: JSON.stringify([document.id, index, order]),
      filename: document.filename, documentId: document.id, status: document.status,
      contract_numbers: [order.contract_number].filter(Boolean),
      tech_pack_references: [order.tech_pack_reference],
    })));
}

/** Search the Tech Pack ID printed on each PO, independently of the chosen BOM. */
export function searchPlanOrders(orders, query = '', modelId = '') {
  const reference = normalizeTechPack(query);
  return orders.filter(order => (!reference || normalizeTechPack(order.tech_pack_reference).includes(reference))
    && (!modelId || normalize(order.model_id) === normalize(modelId)));
}

export function matchingPlanOrders(documents, techPackReference, modelId = '') {
  const reference = normalizeTechPack(techPackReference);
  if (!reference) return [];
  return allPlanOrders(documents).filter(order => normalizeTechPack(order.tech_pack_reference) === reference
    && (!modelId || normalize(order.model_id) === normalize(modelId)));
}

