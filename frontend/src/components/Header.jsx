import { NavLink } from 'react-router-dom';
import { useEffect, useState, useCallback } from 'react';
import ThemeToggle from './ThemeToggle';
import { listReports, REPORTS_CHANGED_EVENT } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function Header() {
  const [counts, setCounts] = useState({ lost: null, found: null });
  const { user, logout } = useAuth();

  const refreshCounts = useCallback(() => {
    Promise.all([listReports('lost'), listReports('found')])
      .then(([lost, found]) => {
        // Only count reports still actually open -- a claimed/resolved
        // report shouldn't keep padding the nav badge. This is what makes
        // the count drop back down after a successful claim (see
        // client.js's claimMatch, which fires REPORTS_CHANGED_EVENT).
        const openCount = (list) => (list ?? []).filter((r) => r.status === 'open').length;
        setCounts({ lost: openCount(lost), found: openCount(found) });
      })
      .catch(() => {
        setCounts({ lost: 0, found: 0 });
      });
  }, []);

  useEffect(() => {
    refreshCounts();
    // Any successful report creation or claim (see client.js) fires this
    // so the nav badge updates immediately, without a page refresh.
    window.addEventListener(REPORTS_CHANGED_EVENT, refreshCounts);
    return () => window.removeEventListener(REPORTS_CHANGED_EVENT, refreshCounts);
  }, [refreshCounts]);

  return (
    <header className="site-header">
      <div className="site-header-inner">
        <NavLink to="/" className="site-logo" aria-label="FindIt Campus">
          <span className="site-logo-mark" aria-hidden="true" />
          <span className="site-logo-full" aria-hidden="true">FindIt Campus</span>
          <span className="site-logo-short" aria-hidden="true">FindIt</span>
        </NavLink>

        <nav className="site-nav">
          <NavLink to="/lost" className={({ isActive }) => (isActive ? 'active' : '')}>
            Lost
            {counts.lost !== null && <span className="nav-count">{counts.lost}</span>}
          </NavLink>
          <NavLink to="/found" className={({ isActive }) => (isActive ? 'active' : '')}>
            Found
            {counts.found !== null && <span className="nav-count">{counts.found}</span>}
          </NavLink>
          <NavLink to="/claimed" className={({ isActive }) => (isActive ? 'active' : '')}>
            Claimed
          </NavLink>
        </nav>

        <div className="site-actions">
          <NavLink to="/report/lost" className="header-btn header-btn--lost">
            Report lost
          </NavLink>
          <NavLink to="/report/found" className="header-btn header-btn--found">
            Report found
          </NavLink>
          <ThemeToggle />

          {user ? (
            <div className="site-actions" style={{ gap: 8 }}>
              <NavLink to="/change-password" title={user.email} className="header-btn">
                {user.name || user.email.split('@')[0]}
              </NavLink>
              <button type="button" className="header-btn" onClick={logout}>
                Log out
              </button>
            </div>
          ) : (
            <NavLink to="/login" className="header-btn">
              Log in
            </NavLink>
          )}
        </div>
      </div>
    </header>
  );
}