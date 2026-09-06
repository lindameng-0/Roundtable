import React, { useState } from "react";
import axios from "axios";
import { BookOpen, CheckCircle2, Eye, EyeOff, Loader2, XCircle } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { getApi } from "../apiConfig";

const API = getApi();

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState("form");
  const [error, setError] = useState("");
  const token = params.get("token") || "";

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (!token) {
      setStatus("error");
      setError("This password reset link is incomplete.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(`${API}/auth/reset-password`, { token, password });
      setStatus("success");
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setStatus("error");
      setError(typeof detail === "string" ? detail : "This password reset link is invalid or has expired.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f3f0e9] px-5 py-10">
      <section className="w-full max-w-md border border-black/10 bg-[#fffdfa] p-8 shadow-[0_24px_70px_rgba(33,31,27,0.08)] sm:p-10">
        <div className="mb-8 flex items-center gap-3"><BookOpen className="h-6 w-6 text-[#7f3f4a]" strokeWidth={1.5} /><span className="font-serif text-2xl">Roundtable</span></div>
        {status === "success" ? (
          <Result icon={<CheckCircle2 className="h-6 w-6" />} title="Password updated" message="Your password has been changed and existing sessions were signed out." />
        ) : status === "error" ? (
          <Result error icon={<XCircle className="h-6 w-6" />} title="Link unavailable" message={error} />
        ) : (
          <>
            <h1 className="font-serif text-3xl">Choose a new password</h1>
            <p className="mt-3 text-sm leading-6 text-ink-500">Use at least 10 characters with one letter and one number.</p>
            <form onSubmit={submit} className="mt-7 space-y-4">
              <PasswordField label="New password" value={password} onChange={setPassword} visible={showPassword} onToggle={() => setShowPassword((value) => !value)} />
              <PasswordField label="Confirm password" value={confirmPassword} onChange={setConfirmPassword} visible={showPassword} onToggle={() => setShowPassword((value) => !value)} />
              {error && <p className="border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
              <button type="submit" disabled={submitting} className="flex w-full items-center justify-center gap-2 bg-[#7f3f4a] px-4 py-3.5 text-sm font-semibold text-white hover:bg-[#69333d] disabled:opacity-60">{submitting && <Loader2 className="h-4 w-4 animate-spin" />}Update password</button>
            </form>
          </>
        )}
      </section>
    </main>
  );
}

function PasswordField({ label, value, onChange, visible, onToggle }) {
  return <label className="block"><span className="mb-2 block text-xs font-semibold uppercase tracking-wider text-ink-500">{label}</span><span className="relative block"><input type={visible ? "text" : "password"} value={value} onChange={(event) => onChange(event.target.value)} required minLength={10} maxLength={128} autoComplete="new-password" className="auth-input pr-12" /><button type="button" onClick={onToggle} className="absolute inset-y-0 right-0 grid w-12 place-items-center text-ink-400" aria-label={visible ? "Hide password" : "Show password"}>{visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button></span></label>;
}

function Result({ icon, title, message, error = false }) {
  return <div><div className={`mb-6 grid h-12 w-12 place-items-center rounded-full ${error ? "bg-red-50 text-red-600" : "bg-[#e5eee8] text-[#416557]"}`}>{icon}</div><h1 className="font-serif text-3xl">{title}</h1><p className="mt-3 text-sm leading-6 text-ink-500">{message}</p><Link to={error ? "/forgot-password" : "/login"} className="mt-7 inline-flex bg-[#7f3f4a] px-6 py-3 text-sm font-semibold text-white hover:bg-[#69333d]">{error ? "Request another link" : "Continue to sign in"}</Link></div>;
}
