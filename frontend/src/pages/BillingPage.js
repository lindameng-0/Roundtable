import { useConfirmation } from "../components/ConfirmationProvider";
import React, { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { Check, Loader2, RefreshCw } from "lucide-react";
import { getApi } from "../apiConfig";
import { useAuth } from "../context/AuthContext";
import SiteHeader, { SiteFooter } from "../components/SiteHeader";
import { initializePaddle, openPaddleCheckout } from "../paddleCheckout";
import "../billing.css";

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

  const plans = catalog?.items.filter(item => item.mode === "subscription") || [];
  const packs = catalog?.items.filter(item => item.mode === "payment") || [];
  const hasRollover = catalog?.catalog_version >= 2;
  const planName = plans.find(plan => plan.id === balance?.plan)?.name || "Free";

  return <div className="billing-page"><SiteHeader /><main id="main-content" className="page-width billing-content pb-20" tabIndex={-1}>
    <div className="billing-intro"><div><p className="small-note">A fresh perspective, at your pace</p><h1>Room for your<br />next revision.</h1></div><p>Buy a reading pack when your draft is ready, or choose a monthly allowance for a regular writing practice. Every option includes the same reader perspectives and editorial tools.</p></div>
    {error && <div role="alert" className="billing-notice">{error}<button onClick={refresh} className="ml-4 underline">Retry</button></div>}
    {location.search.includes("checkout=success") && <p role="status" className="billing-notice">Your allowance updates after Paddle confirms payment. This can take a moment; refresh below to check.</p>}
    {location.search.includes("checkout=cancelled") && <p role="status" className="billing-notice">Checkout was cancelled. Your existing allowance is unchanged.</p>}
    {balance && <section aria-label="Your reading allowance" className="billing-wallet">
      <div><p className="small-note">{planName} account</p><h2>{balance.available_credits > 0 ? "Ready for your next reading" : "Add room for another reading"}</h2><p>Your saved manuscripts, notes, and reports are always available.</p></div>
      <div className="billing-wallet-actions"><button onClick={refresh} aria-label="Refresh balance" className="button button-quiet"><RefreshCw size={14} />Refresh</button>{balance.has_customer && <button onClick={() => purchase("portal")} disabled={!!busy} className="button button-quiet">Manage subscription</button>}</div>
      <details className="billing-allowance-details"><summary>View your allowance</summary>
        <p className="billing-balance">{format(balance.available_credits)} credits available</p>
        <p>{format(balance.monthly_credits)} monthly, {format(balance.topup_credits)} purchased, and {format(balance.starter_credits)} starter credits.</p>
        {Number(balance.rollover_credits) > 0 && <p>{format(balance.rollover_credits)} rollover credits, available until {new Date(balance.rollover_end * 1000).toLocaleDateString()}.</p>}
        {Number(balance.reserved_credits) > 0 && <p>{format(balance.reserved_credits)} temporarily set aside for work in progress. Unused amounts return automatically.</p>}
        {balance.period_end && balance.plan !== "free" && <p>Current billing period ends {new Date(balance.period_end * 1000).toLocaleDateString()}.</p>}
        {balance.next_plan && balance.next_plan !== balance.plan && <p>Next renewal: {plans.find(plan => plan.id === balance.next_plan)?.name || balance.next_plan}.</p>}
      </details>
    </section>}
    {balance?.payment_review && <p role="alert" className="billing-notice">Your payment needs review before you can start new AI work. Please contact support. Your saved work remains available.</p>}
    {balance?.pending_checkout && <p className="billing-notice">You have an unfinished checkout. Choose the same offer to resume it, or <button disabled={!!busy} onClick={cancelPending} className="underline">cancel this checkout</button>.</p>}
    {loading ? <div className="py-20" role="status"><Loader2 className="animate-spin" /><span className="sr-only">Loading plans</span></div> : catalog && <>
      {!catalog.payments_enabled && <p className="billing-notice" role="status">Checkout is currently unavailable. You can still try the readers with your free starter allowance.</p>}
      {catalog.payments_enabled && catalog.environment === "sandbox" && <p className="billing-notice" role="status">Test checkout only. No real payments are collected.</p>}
      <section aria-labelledby="packs-heading" className="billing-offers">
        <div className="billing-section-heading"><h2 id="packs-heading">A reading, when you need one.</h2><p>One-time packs. No subscription required. Purchased credits never expire.</p></div>
        <div className="reading-pack-grid">{packs.map((pack, index) => <article className="reading-pack" key={pack.id}>
          <h3>{pack.name}</h3><p className="pack-purpose">{["For a draft you are ready to share.", "For another pass, or a few different perspectives.", "For several drafts and the revisions between them."][index]}</p>
          <p><span className="pack-price">${pack.cents / 100}</span><span className="pack-frequency"> once</span></p>
          <p className="pack-allowance">{pack.credits} credits, yours until used</p>
          <button data-testid={`buy-${pack.id}`} onClick={() => purchase(pack.id)} disabled={!!busy || !pack.available} className="button button-quiet">{busy === pack.id ? "Opening checkout?" : !pack.available ? "Checkout unavailable" : "Buy reading pack"}</button>
        </article>)}</div>
      </section>
      <section aria-labelledby="plans-heading" className="billing-offers">
        <div className="billing-section-heading"><h2 id="plans-heading">For a regular writing practice.</h2><p>Monthly plans give you a lower price per credit. You can add a one-time pack whenever you need more.</p></div>
        <div className="plan-grid">
          {[{ id: "free", name: "First reading", cents: 0, credits: catalog.starter_credits }, ...plans].map(plan => <article key={plan.id} className={`plan-card ${plan.id}`}>
            <div className="plan-name"><h3>{plan.name}</h3></div>
            <p className="plan-purpose">{{free: "Try a chapter or short excerpt first.", pro: "Keep a draft moving through revision.", studio: "Make space for more drafts and more perspectives."}[plan.id]}</p>
            <p className="mt-5"><span className="plan-price">${plan.cents / 100}</span>{plan.id !== "free" && <span className="text-sm text-ink-500"> / month</span>}</p>
            <p className="plan-allowance">{plan.credits} {plan.id === "free" ? "starter credits, once" : "credits each month"}</p>
            <ul><li><Check />Distinct AI reader perspectives</li><li><Check />Notes beside your manuscript</li><li><Check />Editorial reports</li><li><Check />{plan.id === "free" ? "No card required" : plan.rollover ? "One billing cycle of capped rollover" : "Optional one-time packs"}</li></ul>
            <button data-testid={`choose-${plan.id}`} onClick={() => plan.id === "free" ? navigate(user ? "/setup" : "/signup") : purchase(plan.id)} disabled={!!busy || (plan.id !== "free" && (!plan.available || balance?.next_plan === plan.id))} className={`button ${plan.id === "pro" ? "button-primary" : "button-quiet"}`}>
              {busy === plan.id ? "Opening checkout?" : balance?.next_plan === plan.id ? "Your current selection" : plan.id === "free" ? "Try your first reading" : !plan.available ? "Checkout unavailable" : balance?.plan && balance.plan !== "free" ? "Switch to " + plan.name : "Choose " + plan.name}
            </button>
          </article>)}
        </div>
      </section>
      <section className="billing-how-it-works" aria-labelledby="allowance-heading"><h2 id="allowance-heading">What does a reading include?</h2>
        <p>Choose your AI readers, follow their responses beside the manuscript, and bring their perspectives together in an editorial report. Longer manuscripts and larger panels use more of your allowance.</p>
        <p>For a first try, start with a chapter or excerpt of around 5,000 words and three readers. We show an estimate for your selected readers and first report before you start. Your actual usage depends on the length of the responses.</p>
        <p>There is no charge to reopen saved notes or reports. Changing a reader or asking for a new report uses additional credits.</p>
        <Link to={user ? "/setup" : "/signup"} className="text-link">Bring your manuscript</Link>
      </section>
    </>}
    <details className="billing-terms"><summary>How billing and rollover work</summary>
      <p>Paddle processes payments. Applicable taxes are shown at checkout. Monthly plans renew automatically until cancelled; manage them from your billing account.</p>
      <p>{hasRollover ? "On a consecutive paid renewal, unused available monthly credits roll into the next billing cycle, up to the new plan?s monthly allowance. Rollover is used first and expires at that cycle?s end; it does not roll again. No renewal means no rollover. Legacy plans retain their original allowances and expiration rules until you switch." : "Monthly credits expire at the end of their paid billing period."} Starter and purchased credits do not expire.</p>
      <p>Credits cover AI work, including reader setup. Temporary reservations protect work in progress; unused amounts return after the call. Failed model calls are not charged. Estimates are not fixed-price guarantees, and a longer response may require more allowance. Saved manuscripts and reports remain accessible at zero balance.</p>
    </details>
    {balance?.history?.length > 0 && <details className="billing-terms"><summary>Recent billing activity</summary><div className="overflow-x-auto"><table className="w-full text-sm text-left"><thead><tr className="border-b border-ink-900/15"><th className="py-3">Activity</th><th>Date</th><th>Credits</th></tr></thead><tbody>{balance.history.map((entry, i) => <tr key={i} className="border-b border-ink-900/5"><td className="py-3 capitalize">{entry.kind}</td><td>{new Date(entry.created_at).toLocaleDateString()}</td><td>{format(entry.credits)}</td></tr>)}</tbody></table></div></details>}
  </main><SiteFooter /></div>;
}
