import { NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

// Mirrors Header: the footer is part of the signed-in app chrome, so it
// stays hidden on the auth screens and before login.
const CHROMELESS_ROUTES = ['/login', '/request-access', '/forgot-password', '/set-password'];

const TEAM = ['Mehwish', 'Mansi Sharma', 'Aarushi Chaudhary'];
const teamLine = `${TEAM.slice(0, -1).join(', ')} and ${TEAM[TEAM.length - 1]}`;

export default function Footer() {
  const { user } = useAuth();
  const { pathname } = useLocation();

  if (!user || CHROMELESS_ROUTES.includes(pathname)) {
    return null;
  }

  const year = new Date().getFullYear();

  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <div className="site-footer-brand">
          <div className="site-footer-logo">
            <span className="site-logo-mark" aria-hidden="true" />
            <span>FindIt Campus</span>
          </div>
          <p className="site-footer-tagline">
            Geo-temporal fusion matching for campus lost &amp; found.
          </p>
        </div>

        <nav className="site-footer-col" aria-label="Browse">
          <span className="site-footer-heading mono">Browse</span>
          <NavLink to="/lost">Lost</NavLink>
          <NavLink to="/found">Found</NavLink>
          <NavLink to="/claimed">Claimed</NavLink>
        </nav>

        <nav className="site-footer-col" aria-label="Report">
          <span className="site-footer-heading mono">Report</span>
          <NavLink to="/report/lost">Something lost</NavLink>
          <NavLink to="/report/found">Something found</NavLink>
        </nav>

        <nav className="site-footer-col" aria-label="Account">
          <span className="site-footer-heading mono">Account</span>
          <NavLink to="/me">My account</NavLink>
          <NavLink to="/change-password">Reset password</NavLink>
        </nav>
      </div>

      <div className="site-footer-bottom">
        <span>&copy; {year} FindIt Campus</span>
        <span className="site-footer-team">Built by {teamLine}.</span>
      </div>
    </footer>
  );
}
