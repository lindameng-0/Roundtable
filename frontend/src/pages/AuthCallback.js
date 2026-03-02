import React, { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Loader2 } from "lucide-react";
import axios from "axios";
import { getApi } from "../apiConfig";

const API = getApi();

/**
 * Handles the OAuth redirect: reads session_id from URL hash,
 * exchanges it for a session, then redirects to /setup (manuscript page).
 */
export default function AuthCallback() {
  const navigate = useNavigate();
  const { login } = useAuth();

  useEffect(() => {
    const hash = window.location.hash;
    const params = new URLSearchParams(hash.replace("#", "?"));
    const sessionId = params.get("session_id");

    if (!sessionId) {
      navigate("/login", { replace: true });
      return;
    }

    (async () => {
      try {
        const res = await axios.post(
          `${API}/auth/session`,
          { session_id: sessionId },
          { withCredentials: true }
        );
        const { user, session_token } = res.data;
        if (session_token) localStorage.setItem("session_token", session_token);
        login(user, session_token);
        // Clear hash and redirect after state is committed so /setup sees logged-in user
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
        setTimeout(() => navigate("/setup", { replace: true }), 0);
      } catch (err) {
        console.error("Auth callback failed:", err);
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
