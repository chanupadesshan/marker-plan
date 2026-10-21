/**
 * Purpose: Send a request to the backend and return its JSON answer.
 * Input: url - the API path; options - fetch options (method, headers, body).
 * Output: a promise of the parsed JSON. Rejects with an Error carrying the server's message when the status is not OK.
 */
async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    // Validation errors arrive as a list of { msg }; show their messages instead of raw JSON.
    const detail = Array.isArray(error.detail) && error.detail.every(item => item?.msg)
      ? error.detail.map(item => item.msg).join('; ') : error.detail;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return response.json();
}

// Tech Pack endpoints. Each method returns a promise of the server's JSON.
export const api = {
  /** Purpose: List recent Tech Packs. Input: none. Output: an array of Tech Pack summaries. */
  list: () => request('/api/documents'),
  /** Purpose: Load one Tech Pack with its extraction. Input: id. Output: the Tech Pack object. */
  get: (id) => request(`/api/documents/${id}`),
  /** Purpose: Upload a Tech Pack PDF and queue extraction. Input: file - a PDF File. Output: the new Tech Pack's summary. */
  upload: (file) => {
    const form = new FormData();
    form.append('file', file);
    return request('/api/documents/upload', { method: 'POST', body: form });
  },
  /** Purpose: Save corrected extraction data. Input: id; data - the corrected extraction object. Output: { ok, status }. */
  save: (id, data) => request(`/api/documents/${id}/extraction`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  }),
  /** Purpose: Mark an extraction as checked and approved. Input: id. Output: { ok, status }. */
  approve: (id) => request(`/api/documents/${id}/approve`, { method: 'POST' }),
  /** Purpose: Permanently delete a Tech Pack with its extraction and files. Input: id. Output: { ok: true }. */
  remove: (id) => request(`/api/documents/${id}`, { method: 'DELETE' }),
};

// Plies dashboard endpoints. Each method returns a promise of the server's JSON.
export const pliesApi = {
  /** Purpose: List every ply row. Input: none. Output: an array of { id, col_b, col_c, col_d }. */
  list: () => request('/api/plies'),
  /** Purpose: Add a ply row. Input: data - { col_b, col_c, col_d }. Output: the created row with its id. */
  create: data => request('/api/plies', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  }),
  /** Purpose: Replace a ply row's values. Input: id; data - { col_b, col_c, col_d }. Output: the updated row. */
  update: (id, data) => request(`/api/plies/${id}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  }),
  /** Purpose: Permanently delete a ply row. Input: id. Output: { ok: true }. */
  remove: id => request(`/api/plies/${id}`, { method: 'DELETE' }),
};

// Purchase-order endpoints. Each method returns a promise of the server's JSON.
export const poApi = {
  /** Purpose: List recent purchase orders. Input: none. Output: an array of PO summaries with contract numbers. */
  list: () => request('/api/purchase-orders'),
  /** Purpose: Retry a failed PO from its unfinished pages. Input: id. Output: the PO's summary. */
  retry: id => request(`/api/purchase-orders/${id}/retry`, { method: 'POST' }),
  /** Purpose: Load one PO with its extraction. Input: id. Output: the PO object. */
  get: id => request(`/api/purchase-orders/${id}`),
  /** Purpose: Upload a PO PDF and queue extraction. Input: file - a PDF File; techPackId - optional Tech Pack to link. Output: the new PO's summary. */
  upload: (file, techPackId = null) => {
    const form = new FormData();
    form.append('file', file);
    if (techPackId) form.append('tech_pack_id', techPackId);
    return request('/api/purchase-orders/upload', { method: 'POST', body: form });
  },
  /** Purpose: Save corrected orders. Input: id; data - { orders: [...] }. Output: { ok, status }. */
  save: (id, data) => request(`/api/purchase-orders/${id}/extraction`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  }),
  /** Purpose: Mark a PO as checked and approved. Input: id. Output: { ok, status }. */
  approve: id => request(`/api/purchase-orders/${id}/approve`, { method: 'POST' }),
  /** Purpose: Permanently delete a PO with its extraction and files. Input: id. Output: { ok: true }. */
  remove: id => request(`/api/purchase-orders/${id}`, { method: 'DELETE' }),
};
