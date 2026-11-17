export const markerPlanReturnPath = '/?tab=plan';
export const savedPlanPath = id => `/marker-plans/${encodeURIComponent(id)}`;

export function savedPlanId(pathname) {
  const match = /^\/marker-plans\/([A-Za-z0-9-]+)\/?$/.exec(pathname);
  return match?.[1] || null;
}

/** The view an address asks for: 'techpack', 'po' or 'plan' (the libraries), else 'style' (Create Marker Plan). */
export function initialWorkspaceTab(search = '') {
  const tab = new URLSearchParams(search).get('tab');
  return ['techpack', 'po', 'plan'].includes(tab) ? tab : 'style';
}
