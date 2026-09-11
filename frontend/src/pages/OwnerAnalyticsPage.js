import React, { useEffect, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { getApi } from "../apiConfig";
import SiteHeader, { SiteFooter } from "../components/SiteHeader";

const number = value => Number(value).toLocaleString();
function Breakdown({ title, values, label }) {
  return <section><h2>{title}</h2>{Object.keys(values).length ? <table><thead><tr><th>{label}</th><th>Page views</th></tr></thead><tbody>{Object.entries(values).map(([key, value]) => <tr key={key}><td>{key}</td><td>{number(value)}</td></tr>)}</tbody></table> : <p>No recorded visits in this period.</p>}</section>;
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
  const peak = Math.max(1, ...(data?.daily.map(row => row.views) || []));
  const aiViews = data ? ["chatgpt", "perplexity", "claude", "gemini", "copilot"].reduce((sum, key) => sum + (data.sources[key] || 0), 0) : 0;
  return <><SiteHeader /><main id="main-content" className="page-width owner-analytics" tabIndex={-1}>
    <div className="analytics-heading"><div><p className="small-note">Owner's notebook</p><h1>How Roundtable is growing</h1><p>A view of discovery, interest, and the work being read.</p></div><div className="analytics-controls"><label htmlFor="analytics-period">Period</label><select id="analytics-period" value={days} onChange={e => setDays(Number(e.target.value))}><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></select><button className="button button-quiet" disabled={loading} onClick={() => setRevision(v => v + 1)}>Refresh</button></div></div>
    {loading && <p role="status">Loading your analytics…</p>}
    {error && <p role="alert">{error}</p>}
    {data && <>
      {!data.pageviews && <p className="analytics-empty">Your first visits will appear here after the updated site is published. Zero means no recorded traffic in this period.</p>}
      <dl className="analytics-stats">{[["Public page views", data.pageviews], ["AI referral views", aiViews], ["Signup-link clicks", data.signup_clicks]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{number(value)}</dd></div>)}</dl>
      <section className="analytics-trend"><h2>Daily discovery</h2><p>Page views per day, in UTC. Includes repeat visits.</p><div className="analytics-bars" role="img" aria-label={`Daily page views over ${days} days; ${number(data.pageviews)} total. Exact values are in the table below.`}>{data.daily.map(row => <div key={row.day} title={`${row.day}: ${row.views} views`}><span style={{ height: `${row.views / peak * 100}%` }} /></div>)}</div><div className="analytics-axis"><span>{data.daily[0]?.day}</span><span>{data.daily.at(-1)?.day}</span></div><details><summary>View daily counts</summary><table><thead><tr><th>Date (UTC)</th><th>Page views</th></tr></thead><tbody>{data.daily.map(row => <tr key={row.day}><td>{row.day}</td><td>{number(row.views)}</td></tr>)}</tbody></table></details></section>
      <div className="analytics-columns"><Breakdown title="Where visits come from" label="Referrer category" values={data.sources} /><Breakdown title="What people read" label="Public page" values={data.pages} /></div>
      <section><h2>Work in the reading room</h2><p>Current database totals across all time; independent of the traffic period.</p><dl className="analytics-stats">{[["Verified accounts", data.totals.verified_accounts], ["Saved manuscripts", data.totals.manuscripts], ["Editorial reports", data.totals.reports]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{number(value)}</dd></div>)}</dl></section>
      <section className="analytics-next"><h2>What to look at next</h2><ul><li>Compare your most-read pages with signup-link clicks. Try a clearer example or invitation on pages that attract interest.</li><li>Use <a href="https://search.google.com/search-console" target="_blank" rel="noreferrer">Google Search Console</a> to inspect indexed pages, search queries, impressions, and clicks.</li><li>Use <a href="https://www.bing.com/webmasters" target="_blank" rel="noreferrer">Bing Webmaster Tools</a> to review indexing and available AI citation reporting.</li><li>Compare the same-length periods after a content change. Give search engines time to recrawl the page.</li></ul></section>
      <p className="analytics-method">These are anonymous page and click counts, not unique visitors or a conversion funnel. Referral categories come from the browser's incoming referrer; missing referrers appear as direct. AI referrals measure clicks, not mentions or citations. Google AI and ordinary Google traffic cannot be separated here. Blockers, privacy preferences, bots, and repeat visits affect counts. No manuscript content, email addresses, raw referrers, query strings, visitor IDs, or analytics cookies are stored. Counters are retained for up to 400 days and pruned on new traffic.</p>
      <p className="small-note">Updated {new Date(data.generated_at).toLocaleString()}</p>
    </>}
  </main><SiteFooter /></>;
}
