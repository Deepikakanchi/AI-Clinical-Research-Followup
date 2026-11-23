/*
 * components/common/AuthContext.jsx - Login session and role guard.
 *
 * - signIn(): after POST /api/auth/login, saves the session in sessionStorage
 *   (cleared when the browser tab closes) and redirects to the backend's home_path.
 * - On page refresh: restores the session and confirms it with GET /api/auth/me,
 *   so the role always comes from the database.
 * - signOut(): clears everything and returns to /login. Any 401 from the API
 *   signs the user out automatically (expired token or deactivated account).
 * - RequireRole: shows a page only to the right role; others go to /not-allowed.
 */
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { api, setAuth } from '@/api/client';

const AuthContext = createContext(null);
const STORAGE_KEY = 'clinical-followup-session';
const ROLES = ['COORDINATOR', 'REVIEWER'];

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const clearSession = useCallback(() => {
    sessionStorage.removeItem(STORAGE_KEY);
    setAuth(null);
    setUser(null);
    queryClient.clear();
  }, [queryClient]);

  const signOut = useCallback(() => {
    clearSession();
    navigate('/login', { replace: true });
  }, [clearSession, navigate]);

  // Restore and confirm the session once, when the app loads.
  useEffect(() => {
    let saved = null;
    try {
      saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null');
    } catch {
      sessionStorage.removeItem(STORAGE_KEY);
    }
    if (!saved?.token) {
      setReady(true);
      return;
    }
    setAuth(saved.token, signOut);
    api.me()
      .then(me => {
        if (!ROLES.includes(me.role)) return clearSession();
        const session = { ...saved, ...me };
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
        setUser(session);
      })
      .catch(error => {
        if (error.status === 401) clearSession();
        else setUser(saved); // backend unreachable: keep the session; pages will show the error
      })
      .finally(() => setReady(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // login = response of POST /api/auth/login:
  // { token, token_type, staff_code, role, display_label, home_path }
  function signIn(login) {
    if (!ROLES.includes(login.role)) throw new Error('This account has no portal role.');
    const session = {
      token: login.token,
      staff_code: login.staff_code,
      role: login.role,
      display_label: login.display_label,
      home_path: login.home_path,
    };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    setAuth(session.token, signOut);
    queryClient.clear();
    setUser(session);
    navigate(session.home_path, { replace: true });
  }

  return <AuthContext.Provider value={{ user, ready, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}

export function RequireRole({ role, children }) {
  const { user, ready } = useAuth();
  if (!ready) return <div className="page-loading">Loading workspace…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (role && user.role !== role) return <Navigate to="/not-allowed" replace />;
  return children;
}