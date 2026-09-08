import React, { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import SiteHeader, { SiteFooter } from "../components/SiteHeader";
import { getApi } from "../apiConfig";
import { useAuth } from "../context/AuthContext";

const API = getApi();
const options = { withCredentials: true, timeout: 15000 };
const errorText = (error, fallback) => typeof error.response?.data?.detail === "string" ? error.response.data.detail : fallback;

export default function ConnectionsPage() {
  const { user } = useAuth();
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [permission, setPermission] = useState("read");
  const [days, setDays] = useState(30);
  const [secret, setSecret] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [notice, setNotice] = useState("");
  const secretRef = useRef(null);
  const load = useCallback(async () => {
    setLoading(true);
    try { setKeys((await axios.get(`${API}/integrations/keys`, options)).data); }
    catch (e) { setError(errorText(e, "Could not load connections. Try again.")); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (user?.email_verified) load(); else setLoading(false); }, [load, user?.email_verified]);
  useEffect(() => { if (secret) secretRef.current?.focus(); }, [secret]);

  const create = async event => {
    event.preventDefault();
    if (busy) return;
    setBusy("create"); setError(""); setNotice(""); setSecret(""); setRevealed(false);
    try {
      const { data } = await axios.post(`${API}/integrations/keys`, { name: name.trim(), permission, expires_in_days: days }, options);
      setSecret(data.key); setName("");
      const { key, ...metadata } = data;
      setKeys(current => [metadata, ...current]);
    } catch (e) { setError(errorText(e, "Could not create a key. Refresh the list before retrying.")); }
    finally { setBusy(""); }
  };
  const revoke = async id => {
    if (busy) return;
    setBusy(id); setError(""); setNotice("");
    try {
      await axios.delete(`${API}/integrations/keys/${id}`, options);
      setKeys(current => current.filter(key => key.id !== id));
      setSecret(""); setNotice("Key revoked. It can no longer start requests. Jobs already queued may still finish.");
    } catch (e) { setError(errorText(e, "Could not revoke the key. Try again.")); }
    finally { setBusy(""); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(secret); setNotice("Key copied. Paste it into your assistant’s secure connection settings."); }
    catch { setRevealed(true); secretRef.current?.focus(); secretRef.current?.select(); setNotice("Select and copy the key manually."); }
  };

  return <><SiteHeader /><main id="main-content" className="connections-page page-width" tabIndex={-1}>
    <p className="small-note">Your account</p><h1>Connect an assistant</h1>
    <p className="connections-intro">Let a compatible assistant work with your Roundtable manuscripts through MCP. Give each connection its own key so you can revoke it independently.</p>
    <p className="connection-help">Use an assistant that supports <strong>Streamable HTTP with a custom Authorization header</strong>. Connections that require OAuth sign-in are not supported in this release. <Link to="/connect-assistant">See what a connection can do</Link>.</p>
    {!user?.email_verified ? <p role="status">Verify your account email before creating a connection.</p> : <>
      {error && <div className="connection-message connection-error" role="alert">{error} <button className="text-link" onClick={() => { setError(""); load(); }} disabled={loading || !!busy}>Refresh connections</button></div>}
      {notice && <p className="connection-message" role="status">{notice}</p>}
      <section className="connection-setup" aria-labelledby="new-key-heading"><div>
        <h2 id="new-key-heading">Create a connection key</h2>
        <form onSubmit={create}>
          <label htmlFor="connection-name">Connection name</label><input id="connection-name" value={name} onChange={e => setName(e.target.value)} maxLength={60} required placeholder="My writing assistant" />
          <label htmlFor="connection-permission">Permission</label><select id="connection-permission" value={permission} onChange={e => setPermission(e.target.value)} aria-describedby="permission-description"><option value="read">Read manuscripts and saved feedback</option><option value="run">Read, create manuscripts, and run readings</option></select>
          <p id="permission-description" className="connection-field-note">{permission === "run" ? "This key can submit your writing to AI providers and spend your available account credits on setup, readings, and reports. Estimates are not spending caps. Only connect an assistant you trust." : "This key can read all your manuscripts, reader notes, reports, and credit balance. It cannot start paid AI work."}</p>
          <label htmlFor="connection-expiry">Expires after</label><select id="connection-expiry" value={days} onChange={e => setDays(Number(e.target.value))}><option value={7}>7 days</option><option value={30}>30 days</option><option value={90}>90 days</option></select>
          <button className="button button-primary" disabled={!!busy || !name.trim()} type="submit">{busy === "create" ? "Creating key…" : "Create key"}</button>
        </form>
      </div><div className="connection-instructions"><h2>In your assistant’s settings</h2><ol><li>Add a remote MCP server using Streamable HTTP.</li><li>Use this server URL:<code className="connection-code">{API}/mcp/</code></li><li>Add the header <code>Authorization</code>, with the value <code>Bearer YOUR_KEY</code>. Replace <code>YOUR_KEY</code> with the key you create here.</li><li>Connect and try: “List my Roundtable manuscripts.”</li></ol><p>Save the key in the client’s secure settings, not in a conversation, shared file, or URL. Connected assistants receive the writing and feedback they request. Review their data policies before connecting.</p></div></section>
      {secret && <section className="connection-secret" aria-labelledby="secret-heading"><h2 id="secret-heading">Save your key now</h2><p>This is the only time Roundtable will show the full key. It will disappear when you leave this page.</p><label className="sr-only" htmlFor="new-connection-key">New connection key</label><input ref={secretRef} id="new-connection-key" type={revealed ? "text" : "password"} value={secret} readOnly autoComplete="off" spellCheck={false} /><div className="connection-actions"><button className="button button-primary" onClick={copy}>Copy key</button><button className="button button-quiet" onClick={() => setRevealed(!revealed)}>{revealed ? "Hide key" : "Show key"}</button><button className="text-link" onClick={() => setSecret("")}>I’ve saved it</button></div></section>}
      <section className="connection-list" aria-labelledby="connections-heading"><h2 id="connections-heading">Your connection keys</h2>{loading ? <p role="status">Loading connections…</p> : keys.length === 0 ? <p>No connection keys yet.</p> : <ul>{keys.map(key => <li key={key.id}><div><h3>{key.name}</h3><p>{key.permission === "run" ? "Read and run readings" : "Read only"} · {key.prefix}…</p><p>{new Date(key.expires_at) <= new Date() ? "Expired" : "Expires"} {new Date(key.expires_at).toLocaleDateString()}</p></div><button className="button button-quiet" disabled={!!busy} onClick={() => revoke(key.id)} aria-label={`Revoke ${key.name}`}>{busy === key.id ? "Revoking…" : "Revoke"}</button></li>)}</ul>}<p className="connection-field-note">Revocation blocks new requests immediately. Work already accepted can finish and use credits. Keys cannot change billing, purchase credits, delete manuscripts, or access another account.</p></section>
    </>}
  </main><SiteFooter /></>;
}
