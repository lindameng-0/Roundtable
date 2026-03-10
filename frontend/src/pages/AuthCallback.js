import React, { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Loader2 } from "lucide-react";
import axios from "axios";
import { getApi } from "../apiConfig";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH

const API = getApi();

/**
 * Handles the redirect from the backend after Google OAuth.
 *
 * The backend sends the browser here as:
 *   /auth/callback?session_token=<token>
 *
 * We read the token from the query string, store it in localStorage,
 * call /api/auth/me to get the user object, then navigate to /setup.
 */
export default function AuthCallback() {
  const navigate = useNavigate();
  const { login } = useAuth();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sessionToken = params.get("session_token");
    const error = params.get("error");

    if (error) {
      console.error("Auth error from Google OAuth:", error);
      navigate("/login?error=" + encodeURIComponent(error), { replace: true });
      return;
    }

    if (!sessionToken) {
      navigate("/login", { replace: true });
      return;
    }

    (async () => {
      try {
        // Store the session token
        localStorage.setItem("session_token", sessionToken);

        // Fetch the current user using the new token
        const res = await axios.get(`${API}/auth/me`, {
          headers: { Authorization: `Bearer ${sessionToken}` },
          withCredentials: true,
        });

        const user = res.data;
        login(user, sessionToken);

        // Clean up the URL and redirect
        window.history.replaceState(null, "", window.location.pathname);
        setTimeout(() => navigate("/setup", { replace: true }), 0);
      } catch (err) {
        console.error("Auth callback failed:", err);
        localStorage.removeItem("session_token");
        navigate("/login", { replace: true });
      }
    })();
  }, [login, navigate]);

  return (
    <div className="min-h-screen bg-paper flex items-center justify-center">
      <div className="text-center">
        <Loader2 className="w-6 h-6 animate-spin text-clay mx-auto mb-3" strokeWidth={1.5} />
        <p className="text-sm text-ink-400">Signing you in...</p>
      </div>
    </div>
  );
}
