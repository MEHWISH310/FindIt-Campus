import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * Wraps a route that requires login (report creation, viewing matches).
 * While the auth check is still loading (restoring session from a stored
 * token) it renders nothing rather than briefly flashing the login page.
 * Also bounces a logged-in-but-must-set-password user to /set-password
 * first, since nothing else should be usable until that's done.
 * Pass adminOnly to also bounce non-admin users back to "/" -- used for
 * /admin (see App.jsx).
 */
export default function ProtectedRoute({ children, adminOnly = false }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return null;

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  if (user.must_set_password && location.pathname !== '/set-password') {
    return <Navigate to="/set-password" replace />;
  }

  if (adminOnly && !user.is_admin) {
    return <Navigate to="/" replace />;
  }

  return children;
}