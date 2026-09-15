import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Loader2 } from "lucide-react";
import axios from "axios";
import { getApi } from "../apiConfig";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH

const API = getApi();

/**
 * Handles the redirect from the backend after Google OAuth.
 *
 * The backend sets an HTTP-only session cookie and redirects here. This page
 * confirms the cookie with /api/auth/me; JavaScript never receives the token.
 */
export default function AuthCallback() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const error = params.get("error");

    if (error) {
      console.error("Auth error from Google OAuth:", error);
      navigate("/login?error=" + encodeURIComponent(error), { replace: true });
      return;
    }

    const controller = new AbortController();
    setFailed(false);
    (async () => {
      try {
        const res = await axios.get(`${API}/auth/me`, {
          withCredentials: true,
          timeout: 15000,
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        login(res.data);

        // Clean up the URL and redirect
        window.history.replaceState(null, "", window.location.pathname);
        navigate("/dashboard", { replace: true });
      } catch (err) {
        if (!controller.signal.aborted) setFailed(true);
      }
    })();
    return () => controller.abort();
  }, [login, navigate, attempt]);

  return (
    <div className="min-h-screen bg-paper flex items-center justify-center">
      {failed ? <div className="text-center max-w-md px-6" role="alert">
        <h1 className="font-serif text-2xl mb-3">We couldn't finish signing you in</h1>
        <p className="text-sm text-ink-400 mb-6">Google sent you back, but Readerfold couldn't confirm your session. You can retry the connection or return to sign in.</p>
        <button className="button button-primary" onClick={() => setAttempt(value => value + 1)}>Try again</button>
        <Link className="block mt-4 text-sm underline" to="/login">Return to sign in</Link>
      </div> : <div className="text-center" role="status">
        <Loader2 className="w-6 h-6 animate-spin text-clay mx-auto mb-3" strokeWidth={1.5} />
        <p className="text-sm text-ink-400">Signing you in...</p>
      </div>}
    </div>
  );
}
