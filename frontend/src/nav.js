// The left navigation: which links exist, who sees them and where they go.
import { can } from './permissions.js';

/**
 * The navigation, grouped. `feature` is the permission needed to see the link, `admin` limits it to admins,
 * and `inApp` marks the three views that live inside the review screen (so they switch without reloading it).
 */
export const NAV_SECTIONS = [
  { label: 'Workflow', items: [
    { key: 'style', label: 'Create Marker Plan', feature: 'techpacks', inApp: true },
  ] },
  { label: 'Library', items: [
    { key: 'techpack', label: 'Tech Packs', feature: 'techpacks', inApp: true, count: 'techpack' },
    { key: 'po', label: 'Purchase Orders', feature: 'purchase_orders', inApp: true, count: 'po' },
    { key: 'plan', label: 'Marker Plans', feature: 'marker_plan', inApp: true },
  ] },
  { label: 'System management', items: [
    { key: 'plies', label: 'Plies', feature: 'plies', href: '/plies' },
    { key: 'usage', label: 'Usage', feature: 'usage', href: '/usage' },
    { key: 'users', label: 'Users and permissions', admin: true, href: '/admin/users' },
    { key: 'audit', label: 'Activity log', admin: true, href: '/admin/audit' },
  ] },
];

/**
 * Purpose: The address of a view of the review screen.
 * Input: key - 'style' (Create Marker Plan), 'techpack', 'po' or 'plan'.
 * Output: '/' for Create Marker Plan, otherwise '/?tab=' and the key.
 */
export const workspaceHref = key => (key === 'style' ? '/' : `/?tab=${key}`);

const REVIEW_FEATURE = { style: 'techpacks', techpack: 'techpacks', po: 'purchase_orders', plan: 'marker_plan' };

/**
 * Purpose: Decide whether a person may open the page they asked for. Mirrors the left navigation, so no one is
 * shown a page the menu would have hidden.
 * Input: user - the signed-in user; request - { page, tab }: page is 'review' (the main screen, with tab 'style',
 * 'techpack', 'po' or 'plan'), 'saved-plan', 'plies', 'usage', 'users' or 'audit'.
 * Output: true when allowed. Users and Activity log are for admins; everything else needs view permission on its feature.
 */
export function canOpen(user, { page, tab = 'style' }) {
  if (!user) return false;
  if (page === 'users' || page === 'audit') return Boolean(user.is_admin);
  if (page === 'review') return can(user, REVIEW_FEATURE[tab]);
  return can(user, page === 'saved-plan' ? 'marker_plan' : page);
}

/**
 * Purpose: The page a person is sent to when they sign in without a specific page, or when the one they asked for is closed to them.
 * Input: user - the signed-in user.
 * Output: the address of the first page in the navigation they may use (Tech Pack, Purchase Order, Marker Plan, Plies, Usage),
 * or null when they may use none.
 */
export function landingHref(user) {
  return visibleNav(user).flatMap(section => section.items)[0]?.href ?? null;
}

/**
 * Purpose: Work out the navigation one person should see.
 * Input: user - the signed-in user ({ is_admin, permissions }) or nothing.
 * Output: the sections with only the links they may use (admin-only links for admins, the rest by view permission),
 * each with its address filled in; sections left empty are dropped.
 */
export function visibleNav(user) {
  return NAV_SECTIONS.map(section => ({ ...section, items: section.items
    .filter(item => (item.admin ? Boolean(user?.is_admin) : can(user, item.feature)))
    .map(item => ({ ...item, href: item.href || workspaceHref(item.key) })) }))
    .filter(section => section.items.length);
}
