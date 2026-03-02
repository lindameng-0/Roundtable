import React from "react";
import { BookOpen } from "lucide-react";

const EMERGENT_GOOGLE_AUTH_URL = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(window.location.origin + "/auth/callback")}`;

export default function LoginPage() {
  return (
    <div
      className="min-h-screen bg-paper flex items-center justify-center"
      style={{ fontFamily: "'Manrope', sans-serif" }}
    >
      <div className="max-w-sm w-full mx-auto px-6">
        <div className="text-center mb-10">
          <div className="flex items-center justify-center gap-2 mb-4">
            <BookOpen className="w-7 h-7 text-clay" strokeWidth={1.5} />
            <span
              className="text-2xl text-ink-900"
              style={{ fontFamily: "'Cormorant Garamond', serif", fontWeight: 500 }}
            >
              Roundtable
            </span>
          </div>
          <p className="text-sm text-ink-400 leading-relaxed">
            A panel of AI readers for your manuscript.
          </p>
        </div>

        <div
          className="border border-ink-900/8 bg-white p-8"
          style={{ borderRadius: "2px" }}
          data-testid="login-card"
        >
          <h1
            className="font-serif text-xl text-ink-900 mb-2"
            style={{ fontFamily: "'Cormorant Garamond', serif" }}
          >
            Sign in
          </h1>
          <p className="text-xs text-ink-400 mb-6 leading-relaxed">
            Sign in to save your manuscripts and access them from any device.
          </p>

          <a
            href={EMERGENT_GOOGLE_AUTH_URL}
            data-testid="google-signin-btn"
            className="flex items-center justify-center gap-3 w-full border border-ink-900/12 bg-white hover:bg-paper text-ink-700 px-4 py-3 text-sm font-medium transition-all"
            style={{ borderRadius: "2px" }}
          >
            <svg viewBox="0 0 24 24" width="18" height="18">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            Sign in with Google
          </a>

          <p className="text-xs text-ink-400 text-center mt-4">
            No password required. No credit card.
          </p>
        </div>

        <div className="text-center mt-5">
          <a
            href="/setup"
            data-testid="skip-auth-link"
            className="text-xs text-ink-400 hover:text-clay transition-colors underline underline-offset-2"
          >
            Continue without signing in
          </a>
          <p className="text-xs text-ink-400 mt-1">(manuscripts won't be saved to your account)</p>
        </div>

        <p className="text-xs text-center text-ink-400 mt-8">
          Your manuscripts are private and only visible to you.
        </p>
      </div>
    </div>
  );
}
