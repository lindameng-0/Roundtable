import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import axios from "axios";
import { getApi } from "../apiConfig";

const API = getApi();

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = loading, null = logged out
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const token = localStorage.getItem("session_token");
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await axios.get(`${API}/auth/me`, { headers, withCredentials: true });
      setUser(res.data);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // CRITICAL: If returning from the OAuth callback page (/auth/callback?session_token=…),
    // skip the /me check here — AuthCallback.js will read the token and call login() directly.
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const isCallback =
      window.location.pathname === "/auth/callback" &&
      new URLSearchParams(window.location.search).has("session_token");
    if (isCallback) {
      setLoading(false);
      return;
    }
    checkAuth();
  }, [checkAuth]);

  const login = useCallback((userData, token) => {
    if (token) localStorage.setItem("session_token", token);
    setUser(userData);
  }, []);

  const logout = useCallback(async () => {
    const token = localStorage.getItem("session_token");
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    await axios.post(`${API}/auth/logout`, {}, { headers, withCredentials: true }).catch(() => {});
    localStorage.removeItem("session_token");
    setUser(null);
  }, []);

  const getAuthHeaders = useCallback(() => {
    const token = localStorage.getItem("session_token");
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, getAuthHeaders, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
