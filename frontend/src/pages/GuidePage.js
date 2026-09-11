import React from "react";
import { Link, useLocation } from "react-router-dom";
import SiteHeader, { SiteFooter } from "../components/SiteHeader";
import content from "../searchContent.json";

export function ProductFAQ() {
  return <section className="search-faq page-width" aria-labelledby="faq-heading"><h2 id="faq-heading">Before you bring your draft</h2>{content.faq.map(item => <details key={item.question}><summary>{item.question}</summary><p>{item.answer}</p></details>)}<p><Link to="/pricing">Explore plans and credits</Link> · <Link to="/privacy">How your work is handled</Link></p></section>;
}

export default function GuidePage() {
  const { pathname } = useLocation();
  const guide = content.guides[pathname.replace(/\/$/, "")];
  return <><SiteHeader /><main id="main-content" className="search-guide page-width" tabIndex={-1}><nav aria-label="Breadcrumb"><Link to="/">Roundtable</Link> / Writing resources</nav><h1>{guide.heading}</h1><p className="guide-intro">{guide.intro}</p>{guide.sections.map(section => <section key={section.heading}><h2>{section.heading}</h2><p>{section.text}</p></section>)}<Link to="/signup" className="button button-primary">Try a reading with your draft</Link><p>Written by the Roundtable team. AI feedback supports your judgment; it does not guarantee publication or reader response.</p><nav aria-label="Related resources"><Link to="/use-cases">Worked revision examples</Link> ? <Link to="/sample-reading">Explore an annotated sample reading</Link> ? <Link to={pathname.startsWith("/ai-beta-reader") ? "/manuscript-feedback" : "/ai-beta-reader"}>{pathname.startsWith("/ai-beta-reader") ? "Working with manuscript feedback" : "How AI beta readers work"}</Link> · <Link to="/pricing">Plans and credits</Link></nav></main><ProductFAQ /><SiteFooter /></>;
}
