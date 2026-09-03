import { NavLink, useLocation } from 'react-router-dom';
import { useEffect, useState, useCallback } from 'react';
import ThemeToggle from './ThemeToggle';
import Modal from './Modal';
import { listReports, listCustodyRecords, REPORTS_CHANGED_EVENT } from '../api/client';
import { useAuth } from '../context/AuthContext';

// Auth screens (login, first-time signup, and the set-a-new-password
// flow) are shown without the site header -- it only appears once the
// user is actually into the app.
const HEADERLESS_ROUTES = ['/login', '/request-access', '/forgot-password', '/set-password'];

export default function Header() {
  const [counts, setCounts] = useState({ lost: null, found: null, claimed: null });
  const [logoutOpen, setLogoutOpen] = useState(false);
  const { user, logout } = useAuth();
  const { pathname } = useLocation();

  const refreshCounts = useCallback(() => {
    Promise.all([listReports('lost'), listReports('found'), listCustodyRecords()])
      .then(([lost, found, claimed]) => {
        // Total count of every report of that type -- resolved/claimed
        // reports still count, they just aren't excluded here anymore.
        setCounts({
          lost: (lost ?? []).length,
          found: (found ?? []).length,
          claimed: (claimed ?? []).length,
        });
      })
      .catch(() => {
        setCounts({ lost: 0, found: 0, claimed: 0 });
      });
  }, []);

  useEffect(() => {
    refreshCounts();
    // Any successful report creation or claim (see client.js) fires this
    // so the nav badge updates immediately, without a page refresh.
    window.addEventListener(REPORTS_CHANGED_EVENT, refreshCounts);
    return () => window.removeEventListener(REPORTS_CHANGED_EVENT, refreshCounts);
  }, [refreshCounts]);

  // Header only shows once logged in, and never on the auth screens.
  if (!user || HEADERLESS_ROUTES.includes(pathname)) {
    return null;
  }

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
            {counts.claimed !== null && <span className="nav-count">{counts.claimed}</span>}
          </NavLink>
        </nav>

        <div className="site-actions">
          <ThemeToggle />

          {user ? (
            <div className="site-actions" style={{ gap: 8 }}>
              <NavLink to="/me" title={user.email} className="header-btn">
                {user.name || user.email.split('@')[0]}
              </NavLink>
              <button type="button" className="header-btn" onClick={() => setLogoutOpen(true)}>
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

      {logoutOpen && (
        <Modal onClose={() => setLogoutOpen(false)} labelledBy="logout-modal-heading">
          <h2 id="logout-modal-heading" className="modal-heading">
            Log out?
          </h2>
          <p className="modal-text">You'll need to log in again to report or claim items.</p>
          <div className="modal-actions">
            <button
              type="button"
              className="claim-form-cancel"
              onClick={() => setLogoutOpen(false)}
            >
              Cancel
            </button>
            <button type="button" className="submit-btn" onClick={logout}>
              Log out
            </button>
          </div>
        </Modal>
      )}
    </header>
  );
}