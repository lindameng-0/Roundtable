import React, { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { BookOpen, Plus, Loader2, ChevronRight, Search, CheckCircle, Clock } from "lucide-react";
import axios from "axios";
import { useAuth } from "../context/AuthContext";
import SiteHeader from "../components/SiteHeader";
import { TableMark } from "../components/Brand";
import { getApi } from "../apiConfig";

const API = getApi();

export default function DashboardPage() {
  const { user } = useAuth();
  const [manuscripts, setManuscripts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState("");
  const load = useCallback(async (signal) => {
    setLoading(true); setError(false);
    try {
      const response = await axios.get(`${API}/manuscripts`, { withCredentials: true, signal });
      setManuscripts(Array.isArray(response.data) ? response.data : []);
    } catch (err) { if (!axios.isCancel(err)) setError(true); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, []);
  useEffect(() => { const controller = new AbortController(); load(controller.signal); return () => controller.abort(); }, [load]);
  const filtered = manuscripts.filter(ms => `${ms.title || ""} ${ms.genre || ""}`.toLowerCase().includes(query.toLowerCase()));
  return <div><SiteHeader /><main id="main-content" className="workspace" tabIndex={-1}>
    <div className="workspace-heading"><div><p>Welcome back{user?.name ? `, ${user.name.split(" ")[0]}` : ""}.</p><h1>Your manuscripts</h1></div><Link to="/setup" className="button button-primary" data-testid="new-manuscript-btn"><Plus size={16} />New manuscript</Link></div>
    {loading ? <div className="feedback-state" role="status"><Loader2 className="animate-spin mb-3" size={22} />Opening your bookshelf…</div> : error ? <div className="feedback-state" role="alert"><p>We couldn’t load your manuscripts. Please try again.</p><button className="button button-quiet" onClick={() => load()}>Try again</button></div> : manuscripts.length === 0 ? <section className="library-empty" data-testid="empty-dashboard"><TableMark /><div><p className="small-note">There’s a place here for your story</p><h2>Let’s open your first draft.</h2><p>Bring a chapter, a short story, or a whole manuscript. Your AI readers will help you see it with fresh eyes.</p><Link to="/setup" className="button button-primary" data-testid="start-first-manuscript-btn"><Plus size={16} />Add your first manuscript</Link></div></section> : <>
      <div className="library-toolbar"><label className="library-search"><Search size={16} /><span className="sr-only">Search manuscripts</span><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Find a title or genre" /></label><p>{manuscripts.length} {manuscripts.length === 1 ? "manuscript" : "manuscripts"} on your shelf</p></div>
      <div data-testid="manuscripts-list">{filtered.map(ms => { const Icon = ms.reading_complete ? CheckCircle : Clock; return <Link to={`/read/${ms.id}`} key={ms.id} className="manuscript-row" data-testid={`manuscript-card-${ms.id}`}><span className="manuscript-spine"><BookOpen strokeWidth={1.2} /></span><div className="manuscript-row-copy"><h2>{ms.title || "Untitled manuscript"}</h2><div className="manuscript-meta"><span>{ms.genre || "Genre not set"}</span><span>{ms.total_sections || 0} {ms.total_sections === 1 ? "section" : "sections"}</span>{ms.created_at && <span>{new Date(ms.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</span>}</div></div><span className={`manuscript-status ${ms.reading_complete ? "complete" : ""}`}><Icon size={13} />{ms.reading_complete ? "Reading complete" : "Continue reading"}</span><ChevronRight size={16} /></Link>; })}</div>
      {filtered.length === 0 && <div className="feedback-state"><p>No manuscripts match “{query}”.</p><button className="button button-quiet" onClick={() => setQuery("")}>Clear search</button></div>}
    </>}
  </main></div>;
}
