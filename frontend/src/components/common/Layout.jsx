/*
 * components/common/Layout.jsx - Sidebar, top bar and footer.
 * The sidebar shows only the logged-in role's menu. Pages render in <Outlet />.
 */
import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  Activity, LayoutDashboard, FlaskConical, UsersRound, CalendarDays, ClipboardList,
  ShieldCheck, LogOut, Menu, X, ChevronRight,
} from 'lucide-react';
import { useAuth } from './AuthContext';
import DailyQuote from './DailyQuote';

const MENUS = {
  COORDINATOR: [
    ['Dashboard', '/coordinator/dashboard', LayoutDashboard],
    ['Studies', '/coordinator/studies', FlaskConical],
    ['Participants', '/coordinator/participants', UsersRound],
    ['Visit schedule', '/coordinator/visits', CalendarDays],
    ['Follow-ups', '/coordinator/follow-ups', ClipboardList],
  ],
  REVIEWER: [['Review queue', '/reviewer/queue', ClipboardList]],
};

const initials = text =>
  String(text || '').split(/\s+/).filter(Boolean).map(word => word[0]).join('').slice(0, 2).toUpperCase();

export function Footer() {
  return (
    <footer className="safety-footer">
      <ShieldCheck size={14} />
      <span>Synthetic data only. AI output is a draft and never a clinical decision.</span>
      <span className="footer-project">EY Capstone Project</span>
    </footer>
  );
}

export default function Layout() {
  const { user, signOut } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  const menu = MENUS[user.role] || [];
  const current = menu.find(([, url]) => pathname.startsWith(url));
  const label = user.display_label || user.staff_code;

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? 'open' : ''}`} aria-label="Main navigation">
        <NavLink to={user.home_path} className="brand">
          <span className="brand-mark"><Activity size={23} /></span>
          <div>Clinical Research<span>FOLLOW-UP PORTAL</span></div>
        </NavLink>
        <div className="workspace-label">
          WORKSPACE
          <button className="btn btn-ghost btn-icon mobile-menu" aria-label="Close navigation" onClick={() => setMenuOpen(false)}>
            <X size={16} />
          </button>
        </div>
        <nav>
          {menu.map(([text, url, Icon]) => (
            <NavLink key={url} to={url} onClick={() => setMenuOpen(false)} className={({ isActive }) => `nav-item ${isActive || pathname.startsWith(url) ? 'active' : ''}`}>
              <Icon size={19} /><span>{text}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="environment">
            <span className="environment-dot" />Study environment
            <span className="environment-sub">Fictional staff. Synthetic records.</span>
          </div>
          <div className="sidebar-info">
            <ShieldCheck size={20} />
            <div>Research with responsibility<p>Source-led. Human-reviewed.</p></div>
          </div>
          <div className="sidebar-signature">
            <span className="ey-logo">EY<span /></span><span>CAPSTONE PROJECT</span><span>v1.0</span>
          </div>
        </div>
      </aside>
      {menuOpen && <div className="nav-overlay" onClick={() => setMenuOpen(false)} />}

      <div className="main-shell">
        <header className="topbar">
          <button className="btn btn-ghost btn-icon mobile-menu" aria-label="Open navigation" onClick={() => setMenuOpen(true)}>
            <Menu size={18} />
          </button>
          <div className="breadcrumb">Workspace<ChevronRight size={13} /><strong>{current?.[0] || 'Record details'}</strong></div>
          <DailyQuote />
          <div className="topbar-user">
            <span className="avatar" aria-hidden="true">{initials(label)}</span>
            <div className="user-info"><strong>{label}</strong><span>{user.staff_code}</span></div>
            <span className="role-badge">{user.role === 'COORDINATOR' ? 'Coordinator' : 'Reviewer'}</span>
            <button className="btn btn-ghost btn-sm" onClick={signOut}>
              <LogOut size={16} /><span className="signout-text">Sign out</span>
            </button>
          </div>
        </header>
        <main className="page-content">
          <Outlet />
        </main>
        <Footer />
      </div>
    </div>
  );
}