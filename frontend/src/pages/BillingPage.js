import { useConfirmation } from "../components/ConfirmationProvider";
import React, { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { ArrowRight, Check, Loader2, RefreshCw } from "lucide-react";
import { getApi } from "../apiConfig";
import { useAuth } from "../context/AuthContext";
import SiteHeader, { SiteFooter } from "../components/SiteHeader";
import { initializePaddle, openPaddleCheckout } from "../paddleCheckout";

const API = getApi();
const format = (n) => Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });

export default function BillingPage() {
  const confirm = useConfirmation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [catalog, setCatalog] = useState(null);
  const [balance, setBalance] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    setError("");
    try {
      const [products, account] = await Promise.all([
        axios.get(`${API}/billing/catalog`),
        user ? axios.get(`${API}/billing/balance`, { withCredentials: true }) : Promise.resolve(null),
      ]);
      setCatalog(products.data);
      setBalance(account?.data || null);
    } catch {
      setError("We couldn’t load billing details. Please refresh to try again.");
    } finally { setLoading(false); }
  }, [user]);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    // Paddle payment/recovery emails use the approved default payment link.
    // Initialization automatically opens its _ptxn transaction query parameter.
    if (catalog?.payments_enabled && new URLSearchParams(location.search).has("_ptxn")) {
      initializePaddle(catalog).catch(() => setError("Couldn’t open your payment link. Please refresh to retry."));
    }
  }, [catalog, location.search]);
  useEffect(() => {
    const handle = (event) => {
      if (["checkout.closed", "checkout.completed", "checkout.error"].includes(event.detail)) {
        setBusy(null);
        refresh();
        if (event.detail === "checkout.error") setError("Checkout couldn’t finish. You can safely resume it below.");
      }
    };
    window.addEventListener("roundtable-checkout", handle);
    return () => window.removeEventListener("roundtable-checkout", handle);
  }, [refresh]);
  useEffect(() => {
    if (!user || !location.search.includes("checkout=success")) return;
    let attempts = 0;
    const timer = window.setInterval(() => {
      refresh();
      if (++attempts >= 6) window.clearInterval(timer);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [user, location.search, refresh]);

  const purchase = async (item) => {
    if (!user) { navigate("/signup"); return; }
    setBusy(item); setError("");
    try {
      const isPlanChange = ["pro", "studio"].includes(item) && balance?.plan && balance.plan !== "free";
      if (isPlanChange) {
        if (!(await confirm({ title: "Change your plan?", description: "Your new plan starts at the next paid renewal. Your current credit allowance stays unchanged until then.", action: "Change plan" }))) { setBusy(null); return; }
        await axios.post(`${API}/billing/change-plan`, { item }, { withCredentials: true });
        setBusy(null);
        await refresh();
        return;
      }
      const response = await axios.post(`${API}/billing/${item === "portal" ? "portal" : "checkout"}`,
        item === "portal" ? {} : { item }, { withCredentials: true });
      if (item === "portal") {
        const url = new URL(response.data.url);
        if (url.protocol !== "https:" || !(url.hostname === "paddle.com" || url.hostname.endsWith(".paddle.com"))) throw new Error("Invalid payment destination");
        window.location.assign(url.href);
      } else {
        await openPaddleCheckout(catalog, response.data.transaction_id);
        setBusy(null);
        await refresh();
      }
    } catch (err) {
      setError(err.response?.data?.detail?.message || err.response?.data?.detail || "Couldn’t open checkout. Please try again.");
      setBusy(null);
    }
  };

  const cancelPending = async () => {
    setBusy("cancel"); setError("");
    try {
      await axios.post(`${API}/billing/checkout/cancel`, {}, { withCredentials: true });
      await refresh();
    } catch (err) {
      setError(err.response?.data?.detail || "Couldn’t cancel checkout. Please retry.");
    } finally { setBusy(null); }
  };

  return <div className="billing-page"><SiteHeader /><main id="main-content" className="page-width billing-content pb-20" tabIndex={-1}>
      <div className="billing-intro"><div><p className="small-note">Plans &amp; credits</p><h1>Make room for<br />your next draft.</h1></div><p>Start with 10 credits to explore. Find a monthly plan that fits your writing, with a little extra whenever you need it.</p></div>
      {error && <div role="alert" className="mt-6 border-l-2 border-red-700 bg-red-50 p-4 text-sm">{error}<button onClick={refresh} className="ml-4 underline">Retry</button></div>}
      {location.search.includes("checkout=success") && <p role="status" className="mt-6 border border-ink-900/10 p-4 text-sm">You’ve returned from checkout. Credits appear after payment is confirmed; this can take a moment. You can refresh your balance below.</p>}
      {location.search.includes("checkout=cancelled") && <p role="status" className="mt-6 text-sm text-ink-500">Checkout was cancelled. You can continue using your existing credits.</p>}
      {balance && <section aria-label="Your credits" className="credit-summary mt-10 flex flex-wrap items-center justify-between gap-6">
        <div><p className="text-xs uppercase tracking-widest text-ink-500">Your reading allowance</p><p className="font-serif text-4xl mt-2">{format(balance.available_credits)} <span className="text-xl">credits available</span></p></div>
        <div className="text-sm leading-7 text-ink-500">
          <p>{format(balance.monthly_credits)} monthly · {format(balance.topup_credits)} purchased · {format(balance.starter_credits)} starter</p>
          <p>{format(balance.reserved_credits)} reserved for work in progress</p>
          {balance.period_end && balance.plan !== "free" && <p>Current billing period ends {new Date(balance.period_end * 1000).toLocaleDateString()}</p>}
          {balance.next_plan && balance.next_plan !== balance.plan && <p className="capitalize">Next paid renewal: {balance.next_plan}</p>}
        </div>
        <div className="flex gap-4"><button onClick={refresh} aria-label="Refresh balance" className="p-2"><RefreshCw className="w-4 h-4" /></button>{balance.has_customer && <button onClick={() => purchase("portal")} disabled={!!busy} className="text-sm underline underline-offset-4">Manage subscription</button>}</div>
      </section>}
      {balance?.payment_review && <p role="alert" className="mt-6 p-4 border-l-2 border-[#493449] text-sm">Your payment needs review before you can start new AI work. Please contact support. Your saved manuscripts and reports remain available.</p>}
      {balance?.pending_checkout && <p className="mt-6 text-sm text-ink-500">You have an unfinished checkout. Choose the same plan or pack to resume it, or <button disabled={!!busy} onClick={cancelPending} className="underline underline-offset-4">cancel this checkout</button>.</p>}
      {loading ? <div className="py-20" role="status"><Loader2 className="animate-spin" /><span className="sr-only">Loading plans</span></div> : catalog && <>
        {!catalog.payments_enabled && <p className="mt-8 text-sm text-ink-500">Paid plans are opening soon. Starter credits are available when you create an account.</p>}
        <section aria-label="Plans" className="plan-grid">
          {[{ id: "free", name: "Free", cents: 0, credits: catalog.starter_credits }, ...catalog.items.filter(p => p.mode === "subscription")].map((plan) => <article key={plan.id} className={`plan-card ${plan.id}`}>
            <div className="plan-name"><h2>{plan.name}</h2>{plan.id === "pro" && <span>A regular writing practice</span>}</div>
            <p className="plan-purpose">{{free: "For your first fresh perspective.", pro: "For the draft taking shape.", studio: "For more stories on your desk."}[plan.id]}</p>
            <p className="mt-5"><span className="plan-price">${plan.cents / 100}</span>{plan.id !== "free" && <span className="text-sm text-ink-500"> / month</span>}</p>
            <p className="plan-allowance">{plan.credits} {plan.id === "free" ? "starter credits, once" : "credits each month"}</p>
            <ul><li><Check />Distinct AI reader perspectives</li><li><Check />Feedback beside your manuscript</li><li><Check />Editorial reports</li><li><Check />{plan.id === "free" ? "No card required" : "Optional one-time credit top-ups"}</li></ul>
            <button onClick={() => plan.id === "free" ? navigate(user ? "/setup" : "/signup") : purchase(plan.id)} disabled={!!busy || (plan.id !== "free" && (!plan.available || balance?.next_plan === plan.id))} className={`button ${plan.id === "pro" ? "button-primary" : "button-quiet"}`}>
              {busy === plan.id ? "Opening checkout…" : balance?.next_plan === plan.id ? "Your current selection" : plan.id === "free" ? "Start reading" : !plan.available ? "Coming soon" : balance?.plan && balance.plan !== "free" ? "Switch to " + plan.name : "Choose " + plan.name}<ArrowRight className="w-4 h-4" />
            </button>
          </article>)}
        </section>
        <section className="mt-16 grid md:grid-cols-2 gap-10" aria-label="Top up credits">
          <div><p className="text-xs uppercase tracking-widest text-[#493449]">For a particularly prolific month</p><h2 className="font-serif text-4xl mt-4">A little more room.</h2><p className="text-sm text-ink-500 mt-4 leading-7 max-w-md">Top-ups are one-time purchases. They don’t expire, and we use your monthly allowance first. Monthly plans offer a lower price per credit.</p></div>
          <div className="border-t border-ink-900/15">{catalog.items.filter(p => p.mode === "payment").map(pack => <div key={pack.id} className="flex items-center justify-between gap-4 py-5 border-b border-ink-900/15"><span className="font-serif text-2xl">{pack.name}</span><span>${pack.cents / 100}</span><button onClick={() => purchase(pack.id)} disabled={!!busy || !pack.available} className="text-sm underline underline-offset-4 disabled:opacity-40">{busy === pack.id ? "Opening…" : "Add credits"}</button></div>)}</div>
        </section>
      </>}
      <section className="mt-16 max-w-3xl border-t border-ink-900/15 pt-8"><h2 className="font-serif text-3xl">A note on credits</h2><p className="mt-4 text-sm leading-7 text-ink-500">Payments are processed by Paddle. Applicable taxes are shown at checkout. Credits cover AI work, including reader setup. We estimate reading and report usage before you start. The final amount depends on response length; temporary reservations are returned when unused. Failed model calls aren’t charged. Monthly credits expire at the end of their billing period. Starter and purchased credits don’t expire. Your saved manuscripts and reports remain accessible at zero balance.</p></section>
      {balance?.history?.length > 0 && <section className="mt-12"><h2 className="font-serif text-3xl mb-5">Recent activity</h2><div className="overflow-x-auto"><table className="w-full text-sm text-left"><thead><tr className="border-b border-ink-900/15"><th className="py-3">Activity</th><th>Date</th><th>Credits</th></tr></thead><tbody>{balance.history.map((entry, i) => <tr key={i} className="border-b border-ink-900/5"><td className="py-3 capitalize">{entry.kind}</td><td>{new Date(entry.created_at).toLocaleDateString()}</td><td>{format(entry.credits)}</td></tr>)}</tbody></table></div></section>}
  </main><SiteFooter /></div>;
}
