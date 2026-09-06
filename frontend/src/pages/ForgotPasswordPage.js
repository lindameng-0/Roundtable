import React, { useState } from "react";
import axios from "axios";
import { ArrowLeft, BookOpen, CheckCircle2, Loader2, Mail } from "lucide-react";
import { Link } from "react-router-dom";
import { getApi } from "../apiConfig";

const API = getApi();

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await axios.post(`${API}/auth/forgot-password`, { email });
      setSent(true);
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Unable to request a reset link. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f3f0e9] px-5 py-10">
      <section className="w-full max-w-md border border-black/10 bg-[#fffdfa] p-8 shadow-[0_24px_70px_rgba(33,31,27,0.08)] sm:p-10">
        <div className="mb-8 flex items-center gap-3"><BookOpen className="h-6 w-6 text-[#7f3f4a]" strokeWidth={1.5} /><span className="font-serif text-2xl">Roundtable</span></div>
        {sent ? (
          <div>
            <div className="mb-6 grid h-12 w-12 place-items-center rounded-full bg-[#e5eee8] text-[#416557]"><CheckCircle2 className="h-5 w-5" /></div>
            <h1 className="font-serif text-3xl">Check your inbox</h1>
            <p className="mt-3 text-sm leading-6 text-ink-500">If an account exists for <strong className="font-semibold text-ink-800">{email}</strong>, we sent a link to choose a new password.</p>
            <Link to="/login" className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-[#7f3f4a] hover:underline"><ArrowLeft className="h-4 w-4" />Return to sign in</Link>
          </div>
        ) : (
          <>
            <div className="mb-6 grid h-12 w-12 place-items-center rounded-full bg-[#f2e5e7] text-[#7f3f4a]"><Mail className="h-5 w-5" /></div>
            <h1 className="font-serif text-3xl">Reset your password</h1>
            <p className="mt-3 text-sm leading-6 text-ink-500">Enter your account email and we’ll send you a secure reset link.</p>
            <form onSubmit={submit} className="mt-7">
              <label className="block"><span className="mb-2 block text-xs font-semibold uppercase tracking-wider text-ink-500">Email</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" className="auth-input" placeholder="you@example.com" /></label>
              {error && <p className="mt-4 border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
              <button type="submit" disabled={submitting} className="mt-5 flex w-full items-center justify-center gap-2 bg-[#7f3f4a] px-4 py-3.5 text-sm font-semibold text-white hover:bg-[#69333d] disabled:opacity-60">{submitting && <Loader2 className="h-4 w-4 animate-spin" />}Send reset link</button>
            </form>
            <Link to="/login" className="mt-6 inline-flex items-center gap-2 text-sm text-ink-500 hover:text-ink-900"><ArrowLeft className="h-4 w-4" />Back to sign in</Link>
          </>
        )}
      </section>
    </main>
  );
}
