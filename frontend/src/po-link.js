/** Purpose: How a Tech Pack, its purchase orders and its marker plans fit together as one style. */

/**
 * Purpose: Tell whether a Tech Pack's extraction has been approved, which opens the purchase-order stage.
 * Input: techPack - a Tech Pack list entry.
 * Output: true when its status is approved.
 */
export const isApproved = techPack => techPack?.status === 'approved';

/**
 * Purpose: The purchase orders submitted for one Tech Pack.
 * Input: purchaseOrders - the PO list entries; techPackId - the Tech Pack's id.
 * Output: the entries linked to it, in the same order.
 */
export const linkedOrders = (purchaseOrders, techPackId) => (purchaseOrders || []).filter(order => order.tech_pack_id === techPackId);

/**
 * Purpose: The purchase orders a marker plan can use for a style: approved ones whose IDs do not contradict the Tech Pack
 * (an approved PO has already passed the style-number check).
 * Input: orders - the style's linked PO list entries, each with a status and an id_check.
 * Output: the approved entries that are not a mismatch, in the same order.
 */
export const planOrders = orders => (orders || []).filter(order => order.status === 'approved' && order.id_check !== 'mismatch');

/**
 * Purpose: Add what the style list shows and searches to each Tech Pack: how many POs it has and their contract numbers.
 * Input: techPacks and purchaseOrders - the two lists.
 * Output: the Tech Packs, each with po_count, approved_po_count and contract_numbers.
 */
export function enrichStyles(techPacks, purchaseOrders) {
  return (techPacks || []).map(item => {
    const orders = linkedOrders(purchaseOrders, item.id);
    return { ...item, po_count: orders.length, approved_po_count: orders.filter(order => order.status === 'approved').length,
      contract_numbers: orders.flatMap(order => order.contract_numbers || []) };
  });
}

/**
 * Purpose: The three stages of a style and where each stands.
 * Input: techPack - the Tech Pack list entry; orders - its linked POs.
 * Output: [{ key, label, state }] for 'techpack', 'po' and 'plan'. state is 'complete', 'current' or 'locked'
 * (the PO stage opens when the Tech Pack is approved; the marker plan when the Tech Pack and a PO are approved).
 */
export function styleSteps(techPack, orders) {
  const approved = isApproved(techPack);
  const planOpen = approved && planOrders(orders).length > 0;
  return [
    { key: 'techpack', label: 'Tech Pack', state: approved ? 'complete' : 'current' },
    { key: 'po', label: 'Purchase order', state: !approved ? 'locked' : planOpen ? 'complete' : 'current' },
    { key: 'plan', label: 'Marker plan', state: planOpen ? 'current' : 'locked' },
  ];
}

/**
 * Purpose: Why a locked stage is locked, in words the user can act on.
 * Input: key - 'po' or 'plan'; techPack - the Tech Pack list entry.
 * Output: the sentence.
 */
export function lockedReason(key, techPack) {
  if (key === 'po') return 'Approve the Tech Pack extraction first. Then you can submit its purchase order.';
  return isApproved(techPack) ? 'Approve at least one matching purchase order to create a marker plan.'
    : 'Approve the Tech Pack and its purchase order first.';
}

/**
 * Purpose: The Quality IDs of a Tech Pack (the second number of a BOM title such as '1459 - 1845 - BOM'). One Tech Pack can hold several, one per BOM.
 * Input: item - a Tech Pack list entry or its extraction (design_numbers, or the older single design_number).
 * Output: the Quality IDs as a list (empty when none was read).
 */
export function designIds(item) {
  if (item?.design_numbers?.length) return item.design_numbers;
  return item?.design_number ? [item.design_number] : [];
}

/**
 * Purpose: Name a Tech Pack's IDs for display, e.g. 'Style 1459 · Quality ID 1845' or 'Style 1459 · Quality IDs 1845, 1146'.
 * Input: item - a Tech Pack list entry or its extraction.
 * Output: the text, or '' when neither ID is known.
 */
export function techPackIds(item) {
  const designs = designIds(item);
  return [item?.style_number && `Style ${item.style_number}`, designs.length && `Quality ID${designs.length > 1 ? 's' : ''} ${designs.join(', ')}`].filter(Boolean).join(' · ');
}

/** The headings a style's purchase orders are listed under, by how their IDs compare with the Tech Pack (the PO's id_check). */
export const PO_GROUPS = [
  { key: 'match', title: 'Matching purchase orders', note: 'Model ID and Quality ID match this Tech Pack.' },
  { key: 'no_design', title: 'Style matches, no Quality ID on the PO', note: 'The Model ID matches the style number, but the PO shows no Quality ID. Check it against the Tech Pack before approving.' },
  { key: 'mismatch', title: 'Does not match this Tech Pack', note: 'A Model ID or Quality ID differs. These cannot be approved.' },
  { key: 'unchecked', title: 'Not checked yet', note: 'Still being read, or no style number or Model ID to compare.' },
];

/**
 * Purpose: Sort a style's purchase orders under their headings.
 * Input: orders - the style's linked PO list entries, each with an id_check.
 * Output: the non-empty groups, in heading order, each { key, title, note, items }.
 */
export function groupOrders(orders) {
  return PO_GROUPS.map(group => ({ ...group, items: (orders || []).filter(order => (order.id_check || 'unchecked') === group.key) }))
    .filter(group => group.items.length);
}

/** Purpose: Short words for a PO's id_check in lists. Input: check - 'match', 'no_design', 'mismatch' or 'unchecked'. Output: the text, or '' for unchecked. */
export const checkLabel = check => ({ match: 'IDs match', no_design: 'No Quality ID on PO', mismatch: 'IDs differ' })[check] || '';
