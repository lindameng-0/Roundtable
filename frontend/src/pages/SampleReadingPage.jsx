import React from "react";
import { Link } from "react-router-dom";
import SiteHeader, { SiteFooter } from "../components/SiteHeader";

const passages = [
  { id: "cup", text: "By eight, the tea had gone cold. Clara cleared one place at the table, then stopped. She put the second cup in the cupboard, where she would not have to see it. When the knock finally came, she left it there.", notes: [
    { reader: "Emotional reader", text: "Hiding the cup makes the waiting feel painful. I read it as grief, although the passage hasn’t told me who is absent." },
    { reader: "Analytical reader", text: "The knock gives this small action a consequence. I want to know whether the person at the door is the person she has been waiting for." },
  ] },
  { id: "door", text: "Her brother stood on the step with their mother’s blue suitcase. Rain ran from its handle onto his shoes. ‘The driver wouldn’t wait,’ he said. Clara moved aside. He carried the case past her, careful not to touch the doorframe, as if there were still someone inside who might complain.", notes: [
    { reader: "Emotional reader", text: "The care around the doorframe makes the mother feel present without putting her in the room. I would keep that detail." },
    { reader: "Skeptical reader", text: "I can follow the physical action, but not the arrangements. Was Clara expecting her brother, her mother, or both? The suitcase could mean a visit or a death." },
  ] },
  { id: "letter", text: "He set an envelope beside the untouched saucer. Clara recognized her own address in their mother’s handwriting. ‘She asked me to bring this.’ Upstairs, a floorboard creaked. He looked toward the ceiling. Clara took the envelope and turned it face down. ‘You’ll want some tea.’", notes: [
    { reader: "Analytical reader", text: "The floorboard changes my question from ‘What happened to their mother?’ to ‘Who is upstairs?’ That may be a good turn, but it competes with the letter at the end of a very short opening." },
    { reader: "Skeptical reader", text: "I’m tempted to call the sound a continuity problem if the house is empty. But the text never says it is empty. This is a question to check against the next scene, not an established mistake." },
  ] },
];

export default function SampleReadingPage() {
  return <><SiteHeader /><main id="main-content" className="sample-page page-width" tabIndex={-1}>
    <nav className="sample-breadcrumb" aria-label="Breadcrumb"><Link to="/">Roundtable</Link><span aria-hidden="true"> / </span>Sample manuscript feedback</nav>
    <header className="sample-intro">
      <p className="small-note">A passage, several readings, one author’s choice</p>
      <h1>What do your readers <br />see in the second cup?</h1>
      <p className="sample-lead">Follow a short fiction opening from passage-level reactions to a revision decision. The useful part isn’t getting every reader to agree. It’s understanding what their disagreement asks of the draft.</p>
      <p className="sample-disclosure"><strong>An editorial demonstration.</strong> This original fictional excerpt and the example feedback were created for this page with AI assistance. These are curated illustrations of the workflow, not a recorded Roundtable run or a customer’s manuscript.</p>
      <nav className="sample-contents" aria-label="On this page"><a href="#annotated-draft">Read the draft</a><a href="#editorial-assessment">Compare the reactions</a><a href="#revision">Consider a revision</a></nav>
    </header>
    <section id="annotated-draft" className="sample-draft" aria-labelledby="draft-heading">
      <div className="sample-draft-heading"><div><p className="small-note">Short fiction opening</p><h2 id="draft-heading">The second cup</h2></div><p>Read the passage first. <br />Then follow the notes beside it.</p></div>
      {passages.map((passage, index) => <div className="sample-passage" key={passage.id}>
        <div className="sample-prose"><span className="sample-passage-number">Passage {index + 1}</span><p id={`passage-${passage.id}`}>{passage.text}</p></div>
        <aside className="sample-notes" aria-label={`Reader reactions to passage ${index + 1}`}>{passage.notes.map(note => <article key={note.reader}><h3>{note.reader}</h3><p>{note.text}</p></article>)}</aside>
      </div>)}
    </section>
    <section id="editorial-assessment" className="sample-assessment" aria-labelledby="assessment-heading">
      <div><p className="small-note">Example editorial assessment</p><h2 id="assessment-heading">Preserve the feeling.<br />Clarify the promise.</h2><p>The emotional reading finds an absence; the skeptical reading asks who is missing. Both reactions arise from the same withheld information. The revision question is how much uncertainty this opening should carry.</p></div>
      <div className="sample-findings">
        <article><h3>Keep the physical details</h3><p>The cold tea, hidden cup, and careful movement through the door carry the emotion. Explaining that Clara is sad would repeat what those actions already suggest.</p></article>
        <article><h3>Choose the main question</h3><p>The mother, the letter, and the sound upstairs each invite a different kind of suspense. Decide which question you want readers to take into the next scene, then make the others support it.</p></article>
        <article><h3>Don’t turn an inference into a fact</h3><p>The emotional reader inferred grief. The skeptical reader imagined an empty house. Neither is established by the excerpt. A useful report should preserve that distinction instead of treating a reader’s guess as evidence.</p></article>
      </div>
    </section>
    <section id="revision" className="sample-revision" aria-labelledby="revision-heading">
      <p className="small-note">A possible revision</p><h2 id="revision-heading">Give the knock a history.</h2>
      <p className="sample-section-intro">Suppose the intended story is about siblings avoiding a difficult conversation. We can clarify that Clara expected her brother while keeping the mother’s situation unresolved.</p>
      <div className="sample-comparison">
        <article><h3>Original</h3><blockquote>By eight, the tea had gone cold. Clara cleared one place at the table, then stopped.</blockquote></article>
        <article><h3>One possible revision</h3><blockquote>Her brother had said seven. By eight, the tea had gone cold. Clara cleared his place at the table, then stopped.</blockquote></article>
      </div>
      <div className="sample-revision-note"><h3>What this changes—and what it costs</h3><p>Now the second cup belongs to someone specific. Clara’s action can suggest hurt or impatience as well as grief. We gain orientation, but lose some of the original’s ambiguity. If a ghost story is the intention, that ambiguity might be exactly what the opening needs.</p><p>Leave the floorboard question open until you have read the next scene. Removing it just because one reader objects could erase a deliberate setup.</p></div>
    </section>
    <section className="sample-takeaway" aria-labelledby="takeaway-heading"><h2 id="takeaway-heading">Bring a question to your next reading.</h2><p>Try: “Does this opening make the reader curious about the right thing?” Compare the reactions with the passages behind them, make one deliberate change, then ask a human reader what they understood. AI perspectives can help you form a revision question; they cannot tell you what your story must become.</p><div className="hero-actions"><Link to="/signup" className="button button-primary">Try a reading with your draft</Link><Link to="/pricing/" className="text-link">See plans and credits</Link></div><nav className="sample-related" aria-label="Related reading"><Link to="/ai-beta-reader/">How AI beta readers work</Link><Link to="/manuscript-feedback/">Working with manuscript feedback</Link></nav></section>
  </main><SiteFooter /></>;
}
