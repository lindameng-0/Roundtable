import React, { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Check, MessageCircle } from "lucide-react";
import SiteHeader, { SiteFooter } from "../components/SiteHeader";
import { UseCaseLinks } from "./UseCasePage";
import { ProductFAQ } from "./GuidePage";
import { TableMark } from "../components/Brand";

const perspectives = [
  { name: "The emotional reader", initials: "E", focus: "Character & connection", quote: "That second cup gets to me. Putting it away feels like she is trying to stop hoping someone will come back.", detail: "A small action makes the emotion feel earned.", tone: "moss" },
  { name: "The analytical reader", initials: "A", focus: "Structure & clarity", quote: "Now I want to know who the cup was for. When the knock comes, I expect that question to matter.", detail: "A concrete detail creates a reason to keep reading.", tone: "plum" },
  { name: "The skeptical reader", initials: "S", focus: "Logic & credibility", quote: "I am not sure she wants to see whoever is at the door. Why leave their cup hidden when they finally arrive?", detail: "The motivation may need a little more context.", tone: "ochre" },
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
      <div className="hero-copy"><p className="small-note"><span className="short-rule" />AI beta readers for fiction writers</p><h1>One story.<br />Different reactions.</h1><p className="hero-description">Meet up to five AI beta readers designed to respond like people reading your story. Each brings distinct tastes, a voice, and a perspective. Follow their curiosity, connection, and doubts beside your words.</p><div className="hero-actions"><Link to="/signup" className="button button-primary">Meet your AI readers <ArrowUpRight size={18} /></Link><Link to="/sample-reading/" className="text-link">See different readers react</Link></div><p className="hero-footnote">Try your first reading free. No card needed. <Link to="/beta-readers/" className="text-link">Learn how beta readers help</Link></p><p className="hero-footnote"><strong>Your draft stays yours.</strong> We don’t publish your writing or use it to train AI. <Link to="/privacy/" className="text-link">How we protect your work</Link></p><div className="hero-colophon"><TableMark /><p>For the draft you believe in.<br />And the one you’re still figuring out.</p></div></div>
      <ReadingExample />
    </section>
    <section className="how-section" id="how-it-works"><div className="page-width"><div className="section-intro"><p className="small-note">From a first impression to your next revision</p><h2>A thoughtful read.<br />A clearer way forward.</h2><p>See what each AI reader notices, expects, and questions as the story unfolds. An editorial report brings their observations together afterward.</p></div><div className="how-steps">{[
      ["Bring a draft", "Paste your writing or upload a TXT, DOCX, or PDF. Confirm its genre and the audience you have in mind."],
      ["Meet distinct readers", "Each AI reader has their own tastes and reading habits. Choose a panel and give each a focus, from character connection to plot logic."],
      ["Compare their reactions", "One reader may connect with a character while another questions the same choice. Follow both reactions to the passage, then decide what you want to revise."],
    ].map(([title, text], i) => <article key={title}><span className="step-number">{i + 1}</span><h3>{title}</h3><p>{text}</p></article>)}</div></div></section>
    <section className="writer-note page-width"><TableMark /><div><p className="small-note">Keep the author’s chair</p><h2>Feedback is a conversation.<br />You have the final word.</h2><p>One reader finds the mystery intriguing. Another wants a clearer clue. Their different reactions help you explore how the same passage can be read. These are simulated perspectives; your judgment and feedback from human readers still matter.</p><ul><li><Check size={16} /> Reactions in each reader’s own voice</li><li><Check size={16} /> Different tastes and perspectives on the same passage</li><li><Check size={16} /> Passage-linked feedback you can compare</li></ul><Link to="/signup" className="button button-primary">Start your first reading <ArrowUpRight size={18} /></Link></div></section>
  <section className="use-case-home page-width" aria-labelledby="use-case-heading"><h2 id="use-case-heading">Bring a revision question to the table.</h2><p>See how a passage, different reader reactions, and an author's choice fit together.</p><UseCaseLinks /></section>
  <ProductFAQ /></main><SiteFooter /></>;
}
