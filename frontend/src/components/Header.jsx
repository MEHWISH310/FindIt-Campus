import { NavLink } from 'react-router-dom';
import { useEffect, useState } from 'react';
import ThemeToggle from './ThemeToggle';
import { listReports } from '../api/client';

export default function Header() {
  const [counts, setCounts] = useState({ lost: null, found: null });

  useEffect(() => {
    let cancelled = false;
    Promise.all([listReports('lost'), listReports('found')])
      .then(([lost, found]) => {
        if (!cancelled) setCounts({ lost: lost?.length ?? 0, found: found?.length ?? 0 });
      })
      .catch(() => {
        if (!cancelled) setCounts({ lost: 0, found: 0 });
      });
    return () => {
      cancelled = true;
    };
  }, []);

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