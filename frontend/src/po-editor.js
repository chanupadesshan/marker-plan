// Only aggregate orders are editable. Page results and extraction usage remain server-owned.
export function createPoDraft(extraction) {
  return { orders: structuredClone(extraction?.orders || []) };
}

export function poPayload(draft) {
  return { orders: structuredClone(draft.orders) };
}

function wholeQuantity(value) {
  let text = String(value ?? '').trim();
  if (/^\+?\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]0+)?$/.test(text)) text = text.replace(/[ \u00a0\u202f]/g, '');
  if (!/^\+?\d+(?:[.,]0+)?$/.test(text)) return null;
  return BigInt(text.replace(/[.,]0+$/, ''));
}

function totalCandidates(value) {
  const candidates = new Set();
  const plain = wholeQuantity(value);
  if (plain !== null) candidates.add(plain);
  const text = String(value ?? '').trim();
  for (const separator of [',', '.']) {
    const pattern = separator === ',' ? /^\+?\d{1,3}(?:,\d{3})+$/ : /^\+?\d{1,3}(?:\.\d{3})+$/;
    if (pattern.test(text)) candidates.add(BigInt(text.split(separator).join('')));
  }
  return candidates;
}

export function poSizeTotal(order) {
  if (!order.size_rows?.length) return null;
  const quantities = order.size_rows.map(row => wholeQuantity(row.quantity));
  return quantities.some(quantity => quantity === null) ? null : quantities.reduce((sum, quantity) => sum + quantity, 0n).toString();
}

export function validatePoDraft(draft) {
  const errors = {};
  if (!draft.orders.length) errors.orders = 'Add at least one contract before saving.';
  draft.orders.forEach((order, oi) => {
    if (!String(order.contract_number || '').trim()) errors[`${oi}.contract_number`] = 'Enter a contract number.';
    if (!order.size_rows?.length) errors[`${oi}.size_rows`] = 'Add at least one size row.';
    (order.size_rows || []).forEach((row, ri) => {
      if (!String(row.size || '').trim()) errors[`${oi}.${ri}.size`] = 'Enter a size.';
      if (wholeQuantity(row.quantity) === null) errors[`${oi}.${ri}.quantity`] = 'Enter a whole quantity of zero or more.';
    });
    const candidates = totalCandidates(order.total_quantity);
    const sum = poSizeTotal(order);
    if (!candidates.size) errors[`${oi}.total_quantity`] = 'Enter a whole total quantity (for example, 1410 or 1,410).';
    else if (sum !== null && !candidates.has(BigInt(sum))) errors[`${oi}.total_quantity`] = `Size quantities add up to ${sum}. Check the total and size rows.`;
  });
  return errors;
}
