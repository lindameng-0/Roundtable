import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { getApi } from "../apiConfig";
import { excludeOwnerBrowser } from "../siteAnalytics";

const API = getApi();

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = loading, null = logged out
  const [loading, setLoading] = useState(true);
  const authRevision = useRef(0);

  const checkAuth = useCallback(async () => {
    const revision = ++authRevision.current;
    try {
      const res = await axios.get(`${API}/auth/me`, { withCredentials: true, timeout: 10000 });
      if (revision !== authRevision.current) return;
      excludeOwnerBrowser(res.data);
      setUser(res.data);
    } catch {
      if (revision === authRevision.current) setUser(null);
    } finally {
      if (revision === authRevision.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
    return () => { authRevision.current += 1; };
  }, [checkAuth]);

  const login = useCallback((userData) => {
    // A slow initial session check must not undo a completed sign-in.
    authRevision.current += 1;
    excludeOwnerBrowser(userData);
    setUser(userData);
    setLoading(false);
  }, []);

  const logout = useCallback(async () => {
    const revision = ++authRevision.current;
    await axios.post(`${API}/auth/logout`, {}, { withCredentials: true }).catch(() => {});
    if (revision === authRevision.current) {
      setUser(null);
      setLoading(false);
    }
  }, []);

  const getAuthHeaders = useCallback(() => ({}), []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, getAuthHeaders, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
