import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { getMe, setAuthToken, clearAuthToken, getStoredToken, ApiError } from '../api/client';

const AuthContext = createContext(null);

/**
 * Wraps the app, keeping the logged-in user (or null) in state and
 * persisting the JWT in localStorage so a refresh doesn't log you out.
 * Everything else (Header's login/logout button, ProtectedRoute, pages
 * that need `user`) reads from this via useAuth().
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // On first mount, if a token is already stored, fetch /auth/me to
  // restore the session -- otherwise a page refresh would silently log
  // everyone out even though the token is still valid.
  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setLoading(false);
      return;
    }
    getMe()
      .then((me) => setUser(me))
      .catch(() => {
        clearAuthToken();
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback((token, userData) => {
    setAuthToken(token);
    setUser(userData);
  }, []);

  const logout = useCallback(() => {
    clearAuthToken();
    setUser(null);
  }, []);

  const refreshUser = useCallback(() => {
    return getMe()
      .then((me) => {
        setUser(me);
        return me;
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearAuthToken();
          setUser(null);
        }
        throw err;
      });
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}