/**
 * Purpose: Tell whether a signed-in user may use a feature, so the screens can hide links they could not open.
 * (The server enforces this too; this only keeps the screens tidy.)
 * Input: user - the signed-in user ({ is_admin, permissions }); feature - 'techpacks', 'purchase_orders',
 * 'marker_plan', 'plies' or 'usage'; level - 'view' (default) or 'edit'.
 * Output: true when allowed. Admins may do everything; 'edit' includes 'view'.
 */
export function can(user, feature, level = 'view') {
  if (!user) return false;
  if (user.is_admin) return true;
  const have = user.permissions?.[feature];
  return have === 'edit' || (have === 'view' && level === 'view');
}

/** Purpose: The path of the Users admin page. Input: none. Output: '/admin/users'. */
export const ADMIN_PATH = '/admin/users';

/** Purpose: Tell whether a URL path is the Users admin page. Input: path - window.location.pathname. Output: true or false. */
export const isAdminPath = path => path.replace(/\/+$/, '') === ADMIN_PATH;
