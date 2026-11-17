const TOKEN_KEY = 'auth_token';

// The login token, kept in this browser so a refresh does not sign the person out.
export const authToken = {
  /** Purpose: Read the saved token. Input: none. Output: the token, or null when signed out or storage is unavailable. */
  get: () => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  /** Purpose: Save the token after signing in. Input: token. Output: nothing. */
  set: token => { try { localStorage.setItem(TOKEN_KEY, token); } catch { /* private mode: stays signed in until reload */ } },
  /** Purpose: Forget the token (sign out). Input: none. Output: nothing. */
  clear: () => { try { localStorage.removeItem(TOKEN_KEY); } catch { /* nothing stored */ } },
};

/** Purpose: Add the saved token to a request's headers. Input: options - fetch options. Output: options with the Authorization header. */
function withAuth(options = {}) {
  const token = authToken.get();
  return token ? { ...options, headers: { ...options.headers, Authorization: `Bearer ${token}` } } : options;
}

/**
 * Purpose: Handle a rejected token: forget it and tell the app to show the sign-in page.
 * Input: none. Output: nothing.
 */
function expireSession() {
  authToken.clear();
  window.dispatchEvent(new Event('auth-expired'));
}

/**
 * Purpose: Send a request to the backend and return its JSON answer.
 * Input: url - the API path; options - fetch options (method, headers, body).
 * Output: a promise of the parsed JSON. Rejects with an Error carrying the server's message when the status is not OK.
 * A 401 on any page request (not the sign-in forms) also signs the person out.
 */
async function request(url, options = {}) {
  const response = await fetch(url, withAuth(options));
  if (response.status === 401 && !url.startsWith('/api/auth/login') && !url.startsWith('/api/auth/register')) expireSession();
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    // Validation errors arrive as a list of { msg }; show their messages instead of raw JSON.
    const detail = Array.isArray(error.detail) && error.detail.every(item => item?.msg)
      ? error.detail.map(item => item.msg).join('; ') : error.detail;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return response.json();
}

// User-management endpoints (admins only). Each method returns a promise of the server's JSON.
export const adminApi = {
  /** Purpose: List the permissions an admin can grant. Input: none. Output: { features: [{ key, label }], levels }. */
  features: () => request('/api/admin/features'),
  /** Purpose: List every user. Input: none. Output: an array of users with role, active state and permissions. */
  list: () => request('/api/admin/users'),
  /** Purpose: Create a user. Input: data - { email, full_name, password, is_admin, permissions }. Output: the new user. */
  create: data => request('/api/admin/users', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  }),
  /** Purpose: Change a user. Input: id; data - { full_name, is_admin, is_active, permissions, password? }. Output: the updated user. */
  update: (id, data) => request(`/api/admin/users/${id}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  }),
  /** Purpose: Permanently delete a user. Input: id. Output: { ok: true }. */
  remove: id => request(`/api/admin/users/${id}`, { method: 'DELETE' }),
};

/**
 * Purpose: Open or download a protected file (a PDF or JSON export). A plain link cannot carry the login token,
 * so the file is fetched with it and shown from a temporary blob address.
 * Input: event - the click (its default navigation is cancelled); url - the file's API path; download - a file name to
 * save it as, or omit to open it in a new tab.
 * Output: a promise that finishes when the file is opened; a failure is reported with an alert.
 */
export async function openFile(event, url, download = null) {
  event.preventDefault();
  // Opened before the await so the browser's pop-up blocker still treats it as the click's own window.
  const tab = download ? null : window.open('', '_blank');
  try {
    // A '#page=3' part is for the PDF viewer, not the server, so it is put back on the blob address.
    const [path, fragment] = url.split('#');
    const response = await fetch(path, withAuth());
    if (response.status === 401) expireSession();
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || response.statusText);
    const address = URL.createObjectURL(await response.blob());
    if (tab) tab.location.href = fragment ? `${address}#${fragment}` : address;
    else {
      const link = Object.assign(document.createElement('a'), { href: address, download });
      link.click();
    }
    setTimeout(() => URL.revokeObjectURL(address), 60000);
  } catch (e) {
    tab?.close();
    window.alert(`Could not open the file: ${e.message}`);
  }
}

// Sign-in endpoints. Each method returns a promise of { token, user } (me returns { user }).
export const authApi = {
  /** Purpose: Sign in. Input: data - { email, password }. Output: { token, user }. */
  login: data => request('/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  }),
  /** Purpose: Check the saved token and load who it belongs to. Input: none. Output: { user }. */
  me: () => request('/api/auth/me'),
};

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

// Activity log endpoint (admins only).
export const auditApi = {
  /** Purpose: Load a page of the activity log, newest first. Input: query - the text from auditQuery(). Output: { total, items, actions }. */
  list: query => request(`/api/audit?${query}`),
};

// Usage dashboard endpoint.
export const usageApi = {
  /** Purpose: Load token use, cost, daily totals and failure rates. Input: days - how many days to cover. Output: the summary object. */
  summary: days => request(`/api/usage/summary?days=${days}`),
  /** Purpose: Load each person's token use and cost (admins only). Input: days - how many days to cover. Output: { days, users: [...] }. */
  users: days => request(`/api/usage/users?days=${days}`),
};

// Cutting-plan endpoints. Each method returns a promise of the server's JSON.
export const markerPlanApi = {
  remove: id => request(`/api/marker-plans/${id}`, { method: 'DELETE' }),
  rerunSettings: id => request(`/api/marker-plans/${id}/rerun-settings`),
  /** Saved generations, newest first. */
  list: (limit = 50, offset = 0) => request(`/api/marker-plans?limit=${limit}&offset=${offset}`),
  /** Purpose: Start a cutting plan for the chosen POs and materials. Input: data - the plan request. Output: the queued job. */
  create: data => request('/api/marker-plans', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  }),
  /** Purpose: Read a cutting-plan job's progress and results. Input: id. Output: the job. */
  get: id => request(`/api/marker-plans/${id}`),
};

// Purchase-order endpoints. Each method returns a promise of the server's JSON.
export const poApi = {
  /** Purpose: List recent purchase orders. Input: none. Output: an array of PO summaries with contract numbers. */
  list: () => request('/api/purchase-orders'),
  /** Purpose: Retry a failed PO from its unfinished pages. Input: id. Output: the PO's summary. */
  retry: id => request(`/api/purchase-orders/${id}/retry`, { method: 'POST' }),
  /** Purpose: Extract the pages that were skipped because their IDs did not fit the Tech Pack. Input: id. Output: the queued PO summary. */
  extractSkipped: id => request(`/api/purchase-orders/${id}/extract-skipped`, { method: 'POST' }),
  /** Purpose: Load one PO with its extraction. Input: id. Output: the PO object. */
  get: id => request(`/api/purchase-orders/${id}`),
  /** Purpose: Upload a PO PDF and queue extraction. Input: file - a PDF File; techPackId - optional Tech Pack to link. Output: the new PO's summary. */
  upload: (file, techPackId) => {
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
