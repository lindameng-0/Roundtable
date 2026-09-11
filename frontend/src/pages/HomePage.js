import React, { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Check, MessageCircle } from "lucide-react";
import SiteHeader, { SiteFooter } from "../components/SiteHeader";
import { UseCaseLinks } from "./UseCasePage";
import { ProductFAQ } from "./GuidePage";
import { TableMark } from "../components/Brand";

const perspectives = [
  { name: "The emotional reader", initials: "E", focus: "Character & connection", quote: "I believe she misses him. Hiding the second cup tells me more than saying she feels lonely would.", detail: "A small action makes the emotion feel earned.", tone: "moss" },
  { name: "The analytical reader", initials: "A", focus: "Structure & clarity", quote: "The untouched cup gives me a question to carry into the next paragraph: who was she expecting?", detail: "A concrete detail creates a reason to keep reading.", tone: "plum" },
  { name: "The skeptical reader", initials: "S", focus: "Logic & credibility", quote: "She expects someone, but hides the cup before the knock. I want to understand what changes her mind.", detail: "The motivation may need a little more context.", tone: "ochre" },
];

export function ReadingExample() {
  const [selected, setSelected] = useState(0);
  const reader = perspectives[selected];
  return <div className="reading-example" id="reading-example">
    <div className="example-heading"><span><span className="status-dot" />Inside a reading</span><span>Illustrative example</span></div>
    <div className="example-manuscript"><p className="manuscript-caption">The second cup</p><p>By eight, the tea had gone cold.</p><p>Clara cleared one place at the table, then stopped. <mark>She put the second cup in the cupboard, where she would not have to see it.</mark></p><p>When the knock finally came, she left it there.</p><span className="margin-note"><MessageCircle size={16} /> 3 perspectives</span></div>
    <div className="example-readers" role="group" aria-label="Choose a reader perspective">{perspectives.map((p, i) => <button key={p.name} type="button" aria-pressed={selected === i} onClick={() => setSelected(i)} className={`example-reader ${selected === i ? "selected" : ""}`}><span className={`reader-initial ${p.tone}`}>{p.initials}</span><span>{p.name.replace("The ", "").replace(" reader", "")}</span></button>)}</div>
    <div className={`example-response ${reader.tone}`} aria-live="polite"><p className="response-focus">{reader.focus}</p><blockquote>“{reader.quote}”</blockquote><p>{reader.detail}</p></div>
  </div>;
}

export default function HomePage() {
  return <><SiteHeader /><main id="main-content" tabIndex={-1}>
    <section className="home-hero page-width">
      <div className="hero-copy"><p className="small-note"><span className="short-rule" />Beta reader feedback for fiction writers</p><h1>Meet your story<br />through other eyes.</h1><p className="hero-description">Get passage-level feedback on character, pacing, clarity, and plot from up to five distinct AI beta readers. Compare their perspectives and decide what serves your story.</p><div className="hero-actions"><Link to="/signup" className="button button-primary">Bring your manuscript <ArrowUpRight size={18} /></Link><Link to="/sample-reading/" className="text-link">Explore a sample reading</Link></div><p className="hero-footnote">Try your first reading free. No card needed. <Link to="/beta-readers/" className="text-link">Learn how beta readers help</Link></p><p className="hero-footnote"><strong>Your draft stays yours.</strong> We don’t publish your writing or use it to train AI. <Link to="/privacy/" className="text-link">How we protect your work</Link></p><div className="hero-colophon"><TableMark /><p>For the draft you believe in.<br />And the one you’re still figuring out.</p></div></div>
      <ReadingExample />
    </section>
    <section className="how-section" id="how-it-works"><div className="page-width"><div className="section-intro"><p className="small-note">From a first impression to your next revision</p><h2>A thoughtful read.<br />A clearer way forward.</h2><p>Follow the reading as it happens, then bring the observations together in an editorial report.</p></div><div className="how-steps">{[
      ["Bring a draft", "Paste your writing or upload a TXT, DOCX, or PDF. Confirm its genre and the audience you have in mind."],
      ["Gather your readers", "Choose up to five AI readers with different tastes. Give each a focus, from emotional authenticity to plot logic."],
      ["Find your next revision", "Read their reactions beside your words. Use the editorial report to explore patterns and decide what deserves another look."],
    ].map(([title, text], i) => <article key={title}><span className="step-number">{i + 1}</span><h3>{title}</h3><p>{text}</p></article>)}</div></div></section>
    <section className="writer-note page-width"><TableMark /><div><p className="small-note">Keep the author’s chair</p><h2>Feedback is a conversation.<br />You have the final word.</h2><p>Different readers can disagree. That’s useful. Roundtable helps you see those differences and return to the passages behind them. It’s an AI perspective on your work, with every creative decision still yours.</p><ul><li><Check size={16} /> Reactions connected to your manuscript</li><li><Check size={16} /> Reader focus you can shape</li><li><Check size={16} /> Saved feedback to revisit as you revise</li></ul><Link to="/signup" className="button button-primary">Start your first reading <ArrowUpRight size={18} /></Link></div></section>
  <section className="use-case-home page-width" aria-labelledby="use-case-heading"><h2 id="use-case-heading">Bring a revision question to the table.</h2><p>See how a passage, different reader reactions, and an author's choice fit together.</p><UseCaseLinks /></section>
  <ProductFAQ /></main><SiteFooter /></>;
}
