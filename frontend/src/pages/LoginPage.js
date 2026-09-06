import React, { useEffect, useState } from "react";
import { ArrowRight, BookOpen, CheckCircle2, Eye, EyeOff, Loader2, Mail } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { getApi, getApiBase } from "../apiConfig";
import { useAuth } from "../context/AuthContext";

const API = getApi();
const GOOGLE_LOGIN_URL = getApiBase() + "/api/auth/google/login";

function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 0 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  );
}

function errorMessage(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg.replace(/^Value error, /, "");
  return "Something went wrong. Please try again.";
}

export default function LoginPage({ initialMode = "signin" }) {
  const [mode, setMode] = useState(initialMode);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [verificationSent, setVerificationSent] = useState(false);
  const [resent, setResent] = useState(false);
  const navigate = useNavigate();
  const { login } = useAuth();

  useEffect(() => {
    setMode(initialMode);
    setError("");
    setVerificationSent(false);
  }, [initialMode]);

  const switchMode = (nextMode) => {
    setMode(nextMode);
    setError("");
    setVerificationSent(false);
    navigate(nextMode === "signup" ? "/signup" : "/login", { replace: true });
  };

  const submit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      if (mode === "signup") {
        await axios.post(`${API}/auth/signup`, { name, email, password });
        setVerificationSent(true);
      } else {
        const response = await axios.post(`${API}/auth/login`, { email, password }, { withCredentials: true });
        login(response.data.user);
        navigate("/setup", { replace: true });
      }
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  const resend = async () => {
    setSubmitting(true);
    setError("");
    try {
      await axios.post(`${API}/auth/resend-verification`, { email });
      setResent(true);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#f3f0e9] text-ink-900 lg:grid lg:grid-cols-[minmax(360px,0.9fr)_minmax(520px,1.1fr)]">
      <section className="relative hidden overflow-hidden bg-[#17211e] px-12 py-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="absolute inset-0 opacity-20" style={{ backgroundImage: "radial-gradient(circle at 1px 1px, #d5b77a 1px, transparent 0)", backgroundSize: "24px 24px" }} />
        <div className="relative flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center border border-[#d5b77a]/50 bg-[#d5b77a]/10"><BookOpen className="h-5 w-5 text-[#d5b77a]" strokeWidth={1.5} /></div>
          <span className="font-serif text-3xl tracking-tight">Roundtable</span>
        </div>
        <div className="relative max-w-xl pb-8">
          <p className="mb-5 text-xs font-semibold uppercase tracking-[0.28em] text-[#d5b77a]">The reading room</p>
          <h1 className="font-serif text-5xl leading-[1.06] xl:text-6xl">Hear where your story lands before it meets the world.</h1>
          <p className="mt-7 max-w-lg text-base leading-7 text-white/65">Bring a manuscript to a panel of distinct readers. Follow their reactions, questions, and shifting trust from the first page to the last.</p>
          <div className="mt-10 grid grid-cols-3 gap-3" aria-hidden="true">
            {["Pacing", "Character", "Continuity"].map((label, index) => (
              <div key={label} className="border border-white/10 bg-white/[0.04] p-4">
                <div className={`mb-7 h-2 w-2 rounded-full ${index === 0 ? "bg-[#d5b77a]" : index === 1 ? "bg-[#8ca79b]" : "bg-[#9c7b86]"}`} />
                <span className="text-xs tracking-wide text-white/55">{label}</span>
              </div>
            ))}
          </div>
        </div>
        <p className="relative text-xs text-white/40">Your manuscript stays private to your account.</p>
      </section>

      <section className="flex min-h-screen items-center justify-center px-5 py-10 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-9 flex items-center gap-3 lg:hidden"><BookOpen className="h-6 w-6 text-[#7f3f4a]" strokeWidth={1.5} /><span className="font-serif text-2xl">Roundtable</span></div>

          {verificationSent ? (
            <div className="border border-black/10 bg-[#fffdfa] p-8 shadow-[0_24px_70px_rgba(33,31,27,0.08)] sm:p-10">
              <div className="mb-6 grid h-12 w-12 place-items-center rounded-full bg-[#e5eee8] text-[#416557]"><Mail className="h-5 w-5" /></div>
              <h1 className="font-serif text-3xl">Check your inbox</h1>
              <p className="mt-3 text-sm leading-6 text-ink-500">We sent a verification link to <strong className="font-semibold text-ink-800">{email}</strong>. Verify your email before signing in.</p>
              {resent && <p className="mt-4 flex items-center gap-2 text-sm text-[#416557]"><CheckCircle2 className="h-4 w-4" />A new link has been requested.</p>}
              {error && <p className="mt-4 border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
              <button type="button" onClick={resend} disabled={submitting} className="mt-7 w-full border border-black/15 px-4 py-3 text-sm font-semibold hover:border-[#7f3f4a] hover:text-[#7f3f4a] disabled:opacity-50">{submitting ? "Sending…" : "Resend verification email"}</button>
              <button type="button" onClick={() => switchMode("signin")} className="mt-4 w-full text-sm text-ink-500 underline underline-offset-4 hover:text-ink-900">Return to sign in</button>
            </div>
          ) : (
            <>
              <div className="mb-8">
                <p className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-[#7f3f4a]">{mode === "signup" ? "Join the table" : "Welcome back"}</p>
                <h1 className="font-serif text-4xl tracking-tight">{mode === "signup" ? "Create your account" : "Sign in to Roundtable"}</h1>
                <p className="mt-3 text-sm leading-6 text-ink-500">{mode === "signup" ? "Start with an email and password, or continue with Google." : "Return to your manuscripts and reader reports."}</p>
              </div>

              <div className="mb-6 grid grid-cols-2 border-b border-black/10">
                <button type="button" onClick={() => switchMode("signin")} className={`pb-3 text-sm font-semibold ${mode === "signin" ? "border-b-2 border-[#7f3f4a] text-ink-900" : "text-ink-400"}`}>Sign in</button>
                <button type="button" onClick={() => switchMode("signup")} className={`pb-3 text-sm font-semibold ${mode === "signup" ? "border-b-2 border-[#7f3f4a] text-ink-900" : "text-ink-400"}`}>Create account</button>
              </div>

              <form onSubmit={submit} className="space-y-4">
                {mode === "signup" && <Field label="Name"><input value={name} onChange={(event) => setName(event.target.value)} required minLength={2} maxLength={80} autoComplete="name" className="auth-input" placeholder="Your name" /></Field>}
                <Field label="Email"><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" className="auth-input" placeholder="you@example.com" /></Field>
                <Field
                  label="Password"
                  action={mode === "signin" ? <Link to="/forgot-password" className="normal-case tracking-normal text-[#7f3f4a] hover:underline">Forgot password?</Link> : null}
                >
                  <span className="relative block">
                    <input type={showPassword ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} required minLength={mode === "signup" ? 10 : undefined} maxLength={128} autoComplete={mode === "signup" ? "new-password" : "current-password"} className="auth-input pr-12" placeholder={mode === "signup" ? "At least 10 characters" : "Your password"} />
                    <button type="button" onClick={() => setShowPassword((value) => !value)} className="absolute inset-y-0 right-0 grid w-12 place-items-center text-ink-400 hover:text-ink-700" aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button>
                  </span>
                  {mode === "signup" && <span className="mt-2 block text-xs text-ink-400">Use 10+ characters with at least one letter and one number.</span>}
                </Field>
                {error && <p className="border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
                <button type="submit" disabled={submitting} className="group flex w-full items-center justify-center gap-2 bg-[#7f3f4a] px-4 py-3.5 text-sm font-semibold text-white hover:bg-[#69333d] disabled:opacity-60">
                  {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <>{mode === "signup" ? "Create account" : "Sign in"}<ArrowRight className="h-4 w-4 group-hover:translate-x-0.5" /></>}
                </button>
              </form>

              <div className="my-6 flex items-center gap-4 text-xs uppercase tracking-[0.18em] text-ink-300"><span className="h-px flex-1 bg-black/10" />or<span className="h-px flex-1 bg-black/10" /></div>
              <a href={GOOGLE_LOGIN_URL} className="flex w-full items-center justify-center gap-3 border border-black/15 bg-[#fffdfa] px-4 py-3.5 text-sm font-semibold hover:border-black/30 hover:bg-white" data-testid="google-signin-btn"><GoogleMark />Continue with Google</a>
              <p className="mt-7 text-center text-xs text-ink-400">{mode === "signup" ? <>Already have an account? <Link to="/login" className="font-semibold text-[#7f3f4a] hover:underline">Sign in</Link></> : <>New to Roundtable? <Link to="/signup" className="font-semibold text-[#7f3f4a] hover:underline">Create an account</Link></>}</p>
            </>
          )}
        </div>
      </section>
    </main>
  );
}

function Field({ label, action, children }) {
  return <label className="block"><span className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-ink-500"><span>{label}</span>{action}</span>{children}</label>;
}
