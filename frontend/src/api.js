async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail));
  }
  return response.json();
}

export const api = {
  list: () => request('/api/documents'),
  get: (id) => request(`/api/documents/${id}`),
  upload: (file) => {
    const form = new FormData();
    form.append('file', file);
    return request('/api/documents/upload', { method: 'POST', body: form });
  },
  save: (id, data) => request(`/api/documents/${id}/extraction`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  }),
  approve: (id) => request(`/api/documents/${id}/approve`, { method: 'POST' }),
  remove: (id) => request(`/api/documents/${id}`, { method: 'DELETE' }),
};

export const poApi = {
  list: () => request('/api/purchase-orders'),
  retry: id => request(`/api/purchase-orders/${id}/retry`, { method: 'POST' }),
  get: id => request(`/api/purchase-orders/${id}`),
  upload: (file, techPackId = null) => {
    const form = new FormData();
    form.append('file', file);
    if (techPackId) form.append('tech_pack_id', techPackId);
    return request('/api/purchase-orders/upload', { method: 'POST', body: form });
  },
  save: (id, data) => request(`/api/purchase-orders/${id}/extraction`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  }),
  approve: id => request(`/api/purchase-orders/${id}/approve`, { method: 'POST' }),
  remove: id => request(`/api/purchase-orders/${id}`, { method: 'DELETE' }),
};
