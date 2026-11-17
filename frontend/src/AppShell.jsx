import React, { useEffect, useRef } from 'react';
import { ChartColumn, FilePlus2, FileText, Layers, LogOut, ReceiptText, Scissors, ScrollText, Users } from 'lucide-react';
import { visibleNav } from './nav.js';

const ICONS = { style: FilePlus2, techpack: FileText, po: ReceiptText, plan: Scissors, plies: Layers, usage: ChartColumn, users: Users, audit: ScrollText };

/**
 * Purpose: The frame every signed-in page shares: the dark navigation on the left, a gradient title banner on top
 * and the page's own content below it.
 * Input: props - user: the signed-in person; onSignOut: called by Sign out; active: the key of the current page
 * ('style', 'techpack', 'po', 'plan', 'plies', 'usage', 'users' or 'audit'); title: the banner heading; counts: the numbers
 * shown beside Tech Packs and Purchase Orders ({ techpack, po }); onNavigate(key): switches a view of the review screen without
 * reloading (omit it on other pages and those links simply open the address); actions: buttons shown at the right
 * of the banner; children: the page content.
 * Output: the page frame.
 */
export default function AppShell({ user, onSignOut, active, title, counts = {}, onNavigate, actions, children }) {
  const contentRef = useRef(null);
  useEffect(() => {
    const motionPreference = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (motionPreference?.matches) return;
    // Animate the existing content so navigating preserves forms and selections.
    const animation = contentRef.current?.animate?.([
      { opacity: 0.35, transform: 'translateY(6px)' },
      { opacity: 1, transform: 'translateY(0)' },
    ], { duration: 200, easing: 'cubic-bezier(.2,.65,.3,1)' });
    const stop = () => { if (motionPreference.matches) animation?.cancel(); };
    motionPreference?.addEventListener?.('change', stop);
    return () => {
      animation?.cancel();
      motionPreference?.removeEventListener?.('change', stop);
    };
  }, [active, title]);
  const sections = visibleNav(user);
  const name = user?.full_name || user?.email || 'Signed in';
  return <div className="vp-layout">
    <aside className="vp-sidebar" aria-label="Application navigation">
      <div className="vp-brand"><span className="vp-brand-mark brand-logo" aria-hidden="true"><img src="/guston-logo.png" alt=""/></span><strong>Marker Plan</strong></div>
      <nav className="vp-nav">
        {sections.map(section => <div className="vp-nav-section" key={section.label}>
          <div className="vp-nav-label">{section.label}</div>
          {section.items.map(item => {
            const Icon = ICONS[item.key];
            const body = <><span className="vp-nav-icon" aria-hidden="true"><Icon size={18}/></span><span className="vp-nav-text">{item.label}</span>
              {item.count && typeof counts[item.count] === 'number' && <span className="vp-nav-count">{counts[item.count]}</span>}</>;
            const current = active === item.key ? 'page' : undefined;
            return item.inApp && onNavigate
              ? <button type="button" key={item.key} className={`vp-nav-link ${current ? 'active' : ''}`} aria-current={current} onClick={() => onNavigate(item.key)}>{body}</button>
              : <a key={item.key} href={item.href} className={`vp-nav-link ${current ? 'active' : ''}`} aria-current={current}>{body}</a>;
          })}
        </div>)}
      </nav>
      <div className="vp-sidebar-bottom">
        <div className="vp-user">
          <span className="vp-user-avatar" aria-hidden="true">{name.charAt(0).toUpperCase()}</span>
          <span className="vp-user-meta"><strong title={name}>{name}</strong><small title={user?.email}>{user?.email}</small></span>
        </div>
        <button type="button" className="vp-signout" onClick={onSignOut}><LogOut size={16} aria-hidden="true"/> Sign out</button>
      </div>
    </aside>
    <div className="vp-frame">
      <header className="vp-banner">
        <div className="vp-header-title"><div className="vp-header-kicker">PRODUCTION WORKSPACE</div><h1>{title}</h1></div>
        {actions && <div className="vp-banner-actions">{actions}</div>}
      </header>
      <div className="vp-page-content" ref={contentRef}>{children}</div>
    </div>
  </div>;
}
