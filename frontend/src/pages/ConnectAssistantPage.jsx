import React from "react";
import { Link } from "react-router-dom";
import SiteHeader, { SiteFooter } from "../components/SiteHeader";

export default function ConnectAssistantPage() {
  return <><SiteHeader /><main id="main-content" className="search-guide page-width" tabIndex={-1}>
    <nav aria-label="Breadcrumb"><Link to="/">Roundtable</Link> / Assistant connections</nav>
    <h1>Your manuscript feedback, in your assistant.</h1>
    <p className="guide-intro">Connect a compatible AI assistant to Roundtable through the Model Context Protocol (MCP). Bring saved reader reactions into your writing conversation, or ask your assistant to arrange a new reading.</p>
    <section><h2>Start with a saved reading</h2><p>A read-only connection can list your manuscripts, retrieve passages and reader notes, check progress, and read saved editorial reports. It can also check your credit balance. For example: “Open my latest Roundtable reading and compare what the readers said about the opening.”</p><p>The assistant receives the content it requests. Choose an assistant whose handling of your writing you are comfortable with. A connection never makes your manuscripts public on Roundtable.</p></section>
    <section><h2>Let your assistant arrange a reading</h2><p>A key with reading permission can create a manuscript from text, prepare readers, estimate a reading, queue it, and request an editorial report. Account credits pay for the same AI work as on the website.</p><p>The assistant should explain costs and ask before paid actions. Readings and reports check the approved estimate before starting, but that estimate is not a hard spending limit. Genre analysis and reader setup can also use credits. Start with read-only access if you only need existing feedback.</p></section>
    <section><h2>Connect in a few steps</h2><ol className="connection-steps"><li>Sign in to your verified Roundtable account and open <Link to="/connections">Connections</Link>.</li><li>Create a named key with the permission and expiry you want.</li><li>In your assistant, add the server URL shown in Connections and an Authorization header containing your key.</li><li>Ask the assistant to list your manuscripts, then select the draft you want to discuss.</li></ol><p>This release supports remote MCP clients that accept Streamable HTTP and custom bearer-token headers. It does not offer OAuth sign-in. If your client only supports OAuth connections, it cannot connect yet.</p></section>
    <section><h2>You control the connection</h2><p>Keys expire after 7, 30, or 90 days and can be revoked in Connections. Roundtable shows each full key once and stores only its hash. Keys cannot purchase credits, change billing, delete manuscripts, or access other accounts. Revoking a key stops new requests; jobs already accepted may still finish and use credits.</p></section>
    <Link to="/connections" className="button button-primary">Set up a connection</Link>
    <nav className="sample-related" aria-label="Related resources"><Link to="/sample-reading/">Explore sample feedback</Link><Link to="/pricing/">Plans and credits</Link><Link to="/privacy/">How your writing is handled</Link></nav>
  </main><SiteFooter /></>;
}
