import React, { useEffect, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { getApi } from "../apiConfig";
import SiteHeader, { SiteFooter } from "../components/SiteHeader";
import { isBrowserExcluded } from "../siteAnalytics";

const number = value => Number(value || 0).toLocaleString();
function Breakdown({ title, rows, label }) {
  return <section><h2>{title}</h2>{rows.length ? <table><thead><tr><th>{label}</th><th>Visitors</th><th>Clicked signup</th></tr></thead><tbody>{rows.map(row => <tr key={row.name}><td>{row.name}</td><td>{number(row.visitors)}</td><td>{number(row.signup_click_visitors)}</td></tr>)}</tbody></table> : <p>No distinct visitor activity recorded yet.</p>}</section>;
}

export default function OwnerAnalyticsPage() {
  const { user } = useAuth();
  const [days, setDays] = useState(30);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!user?.is_owner) { setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true); setError(""); setData(null);
    axios.get(`${getApi()}/analytics/summary`, { params: { days }, withCredentials: true, signal: controller.signal, timeout: 15000 })
      .then(response => setData(response.data))
      .catch(err => { if (!controller.signal.aborted) setError(err.response?.status === 403 ? "This account does not have owner access." : "Analytics could not load. Check the API and database migration, then retry."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [user?.is_owner, days, revision]);
  if (!user?.is_owner) return <><SiteHeader /><main id="main-content" className="page-width owner-analytics"><h1>Owner access only</h1><p>This dashboard is restricted to the verified site owner.</p><Link to="/dashboard">Return to your manuscripts</Link></main></>;
  const funnel = data?.funnel || {};
  const distinct = data?.distinct_available;
  const metric = value => distinct ? number(value) : "Unavailable";
  const daily = data?.daily_visitors || [];
  const peak = Math.max(1, ...daily.map(row => row.visitors));
  const completed = (funnel.email_verified || 0) + (funnel.google_signup_completed || 0);
  const takeaway = !distinct ? "Distinct visitor measurement is unavailable. Raw activity is still shown below."
    : !data?.unique_visitors ? "Waiting for your first visitors in this new measurement series."
    : !data?.interested_visitors ? "Visitors are arriving, but no signup interest has been recorded yet."
    : !completed ? "Some visitors are showing signup interest. No signup completions are recorded in this period yet."
    : "Signup interest is turning into completed accounts.";
  return <><SiteHeader /><main id="main-content" className="page-width owner-analytics" tabIndex={-1}>
    <div className="analytics-heading"><div><h1>Are visitors interested?</h1><p>Follow discovery, signup intent, and completed accounts.</p></div><div className="analytics-controls"><label htmlFor="analytics-period">Period</label><select id="analytics-period" value={days} onChange={e => setDays(Number(e.target.value))}><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></select><button className="button button-quiet" disabled={loading} onClick={() => setRevision(v => v + 1)}>Refresh</button></div></div>
    <aside className="analytics-exclusion" aria-label="Your traffic exclusion"><strong>Your views and clicks are excluded</strong><p>{isBrowserExcluded() ? "This browser stays excluded after sign-out. Sign in once in each other browser you use to exclude it too." : "Your signed-in owner account is excluded. Allow browser storage to keep this browser excluded after sign-out."}</p><p>Fresh start: earlier traffic is hidden. Only activity collected after the new measurement series went live appears here.</p></aside>
    {loading && <p role="status">Loading your analytics...</p>}
    {error && <p role="alert">{error}</p>}
    {data && data.measurement_series !== "interest_v2" && <p role="status" className="analytics-empty">The new dashboard is ready. Deploy the updated backend to start the fresh measurement series; older counts are hidden.</p>}
    {data?.measurement_series === "interest_v2" && <>
      <section className="analytics-readout" aria-label="Interest summary"><h2>{takeaway}</h2><p>{data.unique_visitors < 30 ? "This is an early, small sample. Watch the counts grow before judging signup performance." : "Compare equal periods and check where interest stops before changing the signup experience."}</p></section>
      <dl className="analytics-stats">
        <div><dt>Estimated distinct visitors</dt><dd>{metric(data.unique_visitors)}</dd><p>Repeat page views count once per network in this period.</p></div>
        <div><dt>Visitors showing signup intent</dt><dd>{metric(data.interested_visitors)}</dd><p>Clicked signup, submitted the form, or chose Google on signup. Each network counts once.</p></div>
        <div><dt>Visitor interest rate</dt><dd>{distinct && data.interest_rate !== null ? `${data.interest_rate}%` : "--"}</dd><p>Measured page visitors who also showed signup intent in this period.</p></div>
      </dl>
      <section><h2>From curiosity to an account</h2><p>Activity within the selected period. These steps are separate counts, not a tracked journey for each person.</p>
        <div className="analytics-journey">
          <div><h3>Opened signup</h3><strong>{number(funnel.signup_pageviews)}</strong><p>Page views, including repeats.</p></div>
          <div><h3>Submitted email signup</h3><strong>{number(funnel.signup_submissions)}</strong><p>{metric(funnel.unique_signup_submit_visitors)} distinct submit visitors.</p></div>
          <div><h3>Verification email sent</h3><strong>{number(funnel.signup_accepted)}</strong><p>{number(funnel.email_verified)} email verifications completed.</p></div>
          <div><h3>New Google accounts</h3><strong>{number(funnel.google_signup_completed)}</strong><p>{number(funnel.google_auth_started)} Google sign-in starts, including returning users.</p></div>
        </div>
        {funnel.signup_email_failed > 0 && <p className="analytics-alert" role="status">{number(funnel.signup_email_failed)} verification email send failures. Check email delivery before changing your signup invitation.</p>}
      </section>
      <section><h2>Daily visitors</h2><p>Estimated distinct networks each day, in UTC. A returning visitor can appear on multiple days, but counts once in the period total.</p>
        {distinct ? <><div className="analytics-bars" role="img" aria-label="Daily distinct visitors; exact counts available below">{daily.map(row => <div key={row.day} title={`${row.day}: ${row.visitors} visitors`}><span style={{height: `${row.visitors / peak * 100}%`}} /></div>)}</div><div className="analytics-axis"><span>{daily[0]?.day}</span><span>{daily.at(-1)?.day}</span></div><details><summary>Show daily counts</summary><table><thead><tr><th>Date (UTC)</th><th>Visitors</th></tr></thead><tbody>{daily.map(row => <tr key={row.day}><td>{row.day}</td><td>{number(row.visitors)}</td></tr>)}</tbody></table></details></> : <p>Distinct visitor measurement is unavailable.</p>}
      </section>
      {distinct && <div className="analytics-columns"><Breakdown title="Pages that spark interest" label="Page" rows={data.visitor_pages || []} /><Breakdown title="Where visitors come from" label="Source" rows={data.visitor_sources || []} /></div>}
      <p className="small-note">Visitors can appear in more than one page or source row. Sources reflect incoming referrers, not verified signup attribution.</p>
      <details className="analytics-details"><summary>Raw activity and measurement notes</summary><p>{number(data.pageviews)} public page views; {number(data.signup_clicks)} signup-link clicks; {number(data.unique_signup_click_visitors)} distinct signup click visitors.</p><p>Reloads and public-page navigation add page views. Switching browser tabs alone does not. Raw events can include repeats and bots.</p><p>Distinct visitors are estimates based on a private hash of the request IP, not verified people. Shared networks can merge visitors; network changes can count someone again. Privacy settings can prevent measurement. Hashes are kept for up to 90 days and reset when the secret changes; raw IPs are never stored in analytics.</p><p>Completions may come from visits before the selected period or from another device. Google starts include existing-account sign-ins. Older measurement data and all-time workspace totals are hidden from this dashboard.</p></details>
      <p className="small-note">Updated {new Date(data.generated_at).toLocaleString()}</p>
    </>}
  </main><SiteFooter /></>;
}
