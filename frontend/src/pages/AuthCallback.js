import React, { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Loader2 } from "lucide-react";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

/**
 * Handles the OAuth redirect: reads session_id from URL hash,
 * exchanges it for a session, then redirects to /dashboard.
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
        const { user } = res.data;
        const token = sessionId; // backend sets cookie; we also store for header fallback
        // Actually store the session_token returned from the backend if available
        const token2 = res.headers["x-session-token"] || sessionId;
        login(user, null);
        navigate("/dashboard", { replace: true });
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
