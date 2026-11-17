// Helpers for the Usage dashboard page.

export const RANGES = [7, 30, 90];
export const METRICS = [
  { key: 'total_tokens', label: 'Tokens' },
  { key: 'cost_usd', label: 'Cost' },
  { key: 'requests', label: 'Requests' },
  { key: 'failed_requests', label: 'Failed requests' },
];
export const STATUS_LABELS = {
  success: 'Completed', token_limit: 'Token limit reached', empty_result: 'No rows returned',
  malformed_generation: 'Invalid or repetitive output', request_error: 'Request failed',
  invalid_response: 'Invalid response', content_filter: 'Content filtered', error: 'Provider error', unknown: 'Unknown',
};

/**
 * Purpose: Tell whether the current address is the Usage dashboard.
 * Input: pathname - the page's path, e.g. '/usage'.
 * Output: true for '/usage' (with or without a trailing slash), otherwise false.
 */
export function isUsagePath(pathname) {
  return /^\/usage\/?$/.test(pathname || '');
}

/** Purpose: Format a count. Input: value - a number or missing. Output: the number with separators, or '—'. */
export const formatCount = value => typeof value === 'number' ? value.toLocaleString('en-US') : '—';

/**
 * Purpose: Format a USD cost. Input: value - dollars or null; estimated - true when it came from a price list.
 * Output: e.g. '$1.23' or '~$1.23' for an estimate, or 'Unavailable' when there is no cost.
 */
export function formatCost(value, estimated = false) {
  if (typeof value !== 'number') return 'Unavailable';
  return `${estimated ? '~' : ''}$${value.toFixed(value >= 1 ? 2 : 4)}`;
}

/** Purpose: Format a 0-1 share. Input: value - a fraction or null. Output: e.g. '12.5%', or '—' when there were no requests. */
export const formatPercent = value => typeof value === 'number' ? `${(value * 100).toFixed(value > 0 && value < 0.1 ? 1 : 0)}%` : '—';

/**
 * Purpose: Size the daily bars. Input: daily - the daily rows; key - the metric to chart.
 * Output: one { date, value, height } per day, where height is a 0-100 percentage of the busiest day
 * (a day with a value never rounds below 2 so it stays visible).
 */
export function barHeights(daily, key) {
  const values = daily.map(day => (typeof day[key] === 'number' ? day[key] : 0));
  const max = Math.max(0, ...values);
  return daily.map((day, index) => ({
    date: day.date, value: day[key],
    height: !max || !values[index] ? 0 : Math.max(2, Math.round(values[index] / max * 100)),
  }));
}
