const normalized = value => String(value || '').trim().replace(/\s+/g, ' ').toLowerCase();
export function nestingSizes(orders) {
  const sizes = new Map();
  for (const row of orders.flatMap(order => order.size_rows || [])) if (normalized(row.size) && !sizes.has(normalized(row.size))) sizes.set(normalized(row.size), String(row.size).trim());
  return [...sizes.values()];
}
export function nestingErrors(markers = [], length, sizes = []) {
  const errors = [], known = new Set(sizes.map(normalized));
  markers.forEach((marker, index) => {
    const prefix = `Marker ${index + 1}: `;
    const numericLength = Number(marker.length_m);
    if (!Number.isFinite(numericLength) || numericLength <= 0 || numericLength > Number(length)) errors.push(prefix + 'enter a verified length that fits the table.');
    const counts = (marker.size_rows || []).map(row => Number(row.quantity));
    if (!counts.length || counts.some(count => !Number.isInteger(count) || count < 0) || counts.reduce((a,b) => a+b,0) < 1 || counts.reduce((a,b) => a+b,0) > 1000) errors.push(prefix + 'enter whole size counts totalling 1 to 1000 sets.');
    if ((marker.size_rows || []).some(row => !known.has(normalized(row.size)))) errors.push(prefix + 'sizes must match the selected POs.');
    if (marker.width_cm != null && String(marker.width_cm).trim() !== '' && !(Number(marker.width_cm) > 0 && Number(marker.width_cm) <= 10000)) errors.push(prefix + 'enter a valid width.');
    if (marker.efficiency_percent != null && String(marker.efficiency_percent).trim() !== '' && !(Number(marker.efficiency_percent) >= 0 && Number(marker.efficiency_percent) <= 100)) errors.push(prefix + 'efficiency must be between 0 and 100.');
    if (marker.verified !== true) errors.push(prefix + 'confirm that the ratio and length are verified against nesting output.');
  });
  return errors;
}
export function nestingPayload(markers = []) {
  return markers.map(marker => ({ label: marker.label || null, length_m: String(marker.length_m),
    width_cm: String(marker.width_cm ?? '').trim() || null, efficiency_percent: String(marker.efficiency_percent ?? '').trim() || null,
    verified: marker.verified === true,
    size_rows: marker.size_rows.filter(row => Number(row.quantity) > 0).map(row => ({ size: row.size, quantity: Number(row.quantity) })) }));
}
