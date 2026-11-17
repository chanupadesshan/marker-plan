// Helpers for the Activity log page (admins only).

export const AUDIT_PATH = '/admin/audit';
export const PAGE_SIZE = 25;

export const ACTION_LABELS = {
  'techpack.edit': 'Edited Tech Pack', 'techpack.approve': 'Approved Tech Pack',
  'po.edit': 'Edited purchase order', 'po.approve': 'Approved purchase order',
  'marker_plan.create': 'Generated marker plan', 'marker_plan.delete': 'Deleted marker plan',
  'marker_plan.download': 'Downloaded marker plan Excel',
};
const STATUS_LABELS = { needs_review: 'Needs review', approved: 'Approved', failed: 'Failed', queued: 'Queued', processing: 'Processing' };

/** Purpose: Tell whether a URL path is the Activity log page. Input: path - window.location.pathname. Output: true or false. */
export const isAuditPath = path => (path || '').replace(/\/+$/, '') === AUDIT_PATH;

/** Purpose: Name an action in plain words. Input: action - e.g. 'po.edit'. Output: e.g. 'Edited purchase order', or the raw text if unknown. */
export const actionLabel = action => ACTION_LABELS[action] || action;

/** Purpose: Name a status in plain words. Input: status - e.g. 'needs_review'. Output: e.g. 'Needs review', or the raw text if unknown. */
export const statusLabel = status => STATUS_LABELS[status] || status || 'Unknown';

/**
 * Purpose: Format when something happened in the viewer's own time zone.
 * Input: iso - an ISO date-time text, or missing.
 * Output: e.g. 'Nov 2, 2026, 10:01 AM', or '—' when missing or invalid.
 */
export function formatWhen(iso) {
  const date = new Date(iso);
  if (!iso || Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' });
}

/**
 * Purpose: The facts recorded about a marker plan, as label/value pairs for the details view.
 * Input: details - the entry's details for a 'marker_plan.*' action.
 * Output: a list of [label, text] pairs, leaving out anything not recorded (Tech Pack, purchase orders, garments,
 * table length, minimum plies, time limit, materials with consumption and ply limit, and the result when finished).
 */
export function planFacts(details = {}) {
  const facts = [];
  const add = (label, value) => { if (value !== null && value !== undefined && value !== '' && !(Array.isArray(value) && !value.length)) facts.push([label, String(value)]); };
  add('Tech Pack', details.tech_pack_filename);
  add('Purchase orders', (details.orders || []).join(', '));
  add('Garments', details.total_quantity);
  add('Table length', details.table_length_m ? `${details.table_length_m} m` : '');
  add('Minimum plies', details.min_plies);
  add('Time limit', details.time_limit_seconds ? `${details.time_limit_seconds} s per material` : '');
  add('Materials', (details.materials || []).map(item => `${item.material_code || 'Material'} (${item.consumption} ${item.unit}, max ${item.max_plies} plies)`).join('; '));
  const result = details.summary;
  if (result) add('Result', result.complete ? `Complete: ${result.marker_count} markers, ${result.lay_count} lays` : `${result.failed} material${result.failed === 1 ? '' : 's'} not planned`);
  return facts;
}

/**
 * Purpose: The materials of a marker plan entry, one record each, for the details table.
 * Input: details - the entry's details.
 * Output: [{ code, consumption, maxPlies }] with the consumption as text such as '1.65 m' (empty when there are none).
 */
export function planMaterials(details = {}) {
  return (details.materials || []).map(item => ({ code: item.material_code || 'Material',
    consumption: [item.consumption, item.unit].filter(value => value !== null && value !== undefined && value !== '').join(' '),
    maxPlies: item.max_plies ?? '' }));
}

/**
 * Purpose: Tell whether an entry has details worth expanding.
 * Input: entry - an audit entry from the server.
 * Output: true for a marker plan with facts, or an edit that lists changes.
 */
export function hasDetails(entry) {
  return entry.target_type === 'marker_plan' ? planFacts(entry.details).length > 0 : Boolean(entry.details?.changes?.length);
}

/**
 * Purpose: One short line about what an entry did, for the table.
 * Input: entry - an audit entry from the server.
 * Output: for an edit '3 changes (Approved → Needs review)' (or 'No changes to the data'); for an approval 'Needs review → Approved';
 * for a marker plan action '2 materials, 800 garments'.
 */
export function summarizeEntry(entry) {
  const details = entry.details || {};
  if (entry.target_type === 'marker_plan') {
    const count = details.materials?.length || 0;
    const parts = [count ? `${count} material${count === 1 ? '' : 's'}` : '', details.total_quantity != null ? `${details.total_quantity} garments` : ''].filter(Boolean);
    return parts.join(', ') || 'Marker plan';
  }
  const moved = details.previous_status && details.new_status && details.previous_status !== details.new_status
    ? `${statusLabel(details.previous_status)} → ${statusLabel(details.new_status)}` : '';
  if (entry.action.endsWith('.approve')) return moved || 'Approved';
  const count = (details.changes?.length || 0) + (details.more_changes || 0);
  const what = count ? `${count}${details.more_changes ? '+' : ''} change${count === 1 ? '' : 's'}` : 'No changes to the data';
  return moved ? `${what} (${moved})` : what;
}

/** Purpose: Show a stored before/after value. Input: value - text, number, boolean or null. Output: text, or '(empty)' when blank. */
export const showValue = value => value === null || value === undefined || value === '' ? '(empty)' : String(value);

/**
 * Purpose: Build the query string for the log request.
 * Input: filters - { page (0-based), action, search }.
 * Output: e.g. 'limit=25&offset=50&action=po.edit&search=359' with empty filters left out.
 */
export function auditQuery({ page = 0, action = '', search = '' } = {}) {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) });
  if (action) params.set('action', action);
  if (search.trim()) params.set('search', search.trim());
  return params.toString();
}
