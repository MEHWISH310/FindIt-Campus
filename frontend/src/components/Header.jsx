import { NavLink } from 'react-router-dom';
import { useEffect, useState, useCallback } from 'react';
import ThemeToggle from './ThemeToggle';
import { listReports, REPORTS_CHANGED_EVENT } from '../api/client';

export default function Header() {
  const [counts, setCounts] = useState({ lost: null, found: null });

  const refreshCounts = useCallback(() => {
    Promise.all([listReports('lost'), listReports('found')])
      .then(([lost, found]) => {
        setCounts({ lost: lost?.length ?? 0, found: found?.length ?? 0 });
      })
      .catch(() => {
        setCounts({ lost: 0, found: 0 });
      });
  }, []);

  useEffect(() => {
    refreshCounts();
    // Any successful report creation (see client.js) fires this so the
    // nav badge updates immediately, without a page refresh. The same
    // event will fire on claim/resolve once that flow exists, so counts
    // drop back down too instead of only ever growing.
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
        </nav>

        <div className="site-actions">
          <NavLink to="/report/lost" className="header-btn header-btn--lost">
            Report lost
          </NavLink>
          <NavLink to="/report/found" className="header-btn header-btn--found">
            Report found
          </NavLink>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}