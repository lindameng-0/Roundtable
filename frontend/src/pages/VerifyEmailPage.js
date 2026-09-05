import React, { useEffect, useState } from "react";
import axios from "axios";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { getApi } from "../apiConfig";

const API = getApi();

export default function VerifyEmailPage() {
  const [params] = useSearchParams();
  const [status, setStatus] = useState("loading");
  const [message, setMessage] = useState("Verifying your email address…");
  const token = params.get("token");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("This verification link is incomplete.");
      return;
    }
    axios.post(`${API}/auth/verify-email`, { token })
      .then((response) => {
        setStatus("success");
        setMessage(response.data.message || "Your email has been verified.");
      })
      .catch((error) => {
        setStatus("error");
        const detail = error?.response?.data?.detail;
        setMessage(typeof detail === "string" ? detail : "This verification link is invalid or has expired.");
      });
  }, [token]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f3f0e9] px-5">
      <section className="w-full max-w-md border border-black/10 bg-[#fffdfa] p-9 text-center shadow-[0_24px_70px_rgba(33,31,27,0.08)]">
        <div className={`mx-auto mb-6 grid h-14 w-14 place-items-center rounded-full ${status === "error" ? "bg-red-50 text-red-600" : "bg-[#e5eee8] text-[#416557]"}`}>
          {status === "loading" && <Loader2 className="h-6 w-6 animate-spin" />}
          {status === "success" && <CheckCircle2 className="h-6 w-6" />}
          {status === "error" && <XCircle className="h-6 w-6" />}
        </div>
        <h1 className="font-serif text-3xl">{status === "loading" ? "One moment" : status === "success" ? "Email verified" : "Link unavailable"}</h1>
        <p className="mt-3 text-sm leading-6 text-ink-500">{message}</p>
        {status !== "loading" && <Link to="/login" className="mt-7 inline-flex bg-[#7f3f4a] px-6 py-3 text-sm font-semibold text-white hover:bg-[#69333d]">Continue to sign in</Link>}
      </section>
    </main>
  );
}
