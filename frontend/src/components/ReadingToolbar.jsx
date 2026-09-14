import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, List, PanelRight, BookOpen, FileText, Loader2 } from "lucide-react";
import { TableMark } from "./Brand";

export default function ReadingToolbar({ drawer, openDrawer, focusMode, setFocusMode, readingDone, processingSection, totalSections, progress, totalCommentCount, loadingReport, generateReport, isStalled = false }) {
  const percent = Math.round(Math.max(0, Math.min(100, progress)));
  const status = isStalled ? "Your reading needs attention" : processingSection ? `Readers are working through section ${processingSection} of ${totalSections}` : percent > 0 || totalCommentCount > 0 ? "Your readers are making notes" : "Your readers are getting settled";
  return <><header className="reading-workbar">
    <nav className="workbar-location" aria-label="Reading navigation">
      <Link to="/dashboard" className="workbar-home" aria-label="Back to manuscripts"><TableMark /><ArrowLeft size={14} /><span>Manuscripts</span></Link>
      <span className="workbar-divider" aria-hidden="true" />
      <button id="contents-trigger" onClick={() => openDrawer("contents")} aria-haspopup="dialog" aria-expanded={drawer === "contents"}><List size={16} />Contents</button>
    </nav>
    {readingDone && <p className="workbar-status" role="status">Reading complete</p>}
    <div className="workbar-tools">
      <button onClick={() => setFocusMode(!focusMode)} aria-pressed={focusMode} title="Hide annotations for uninterrupted reading"><BookOpen size={16} /><span>Focus</span></button>
      <button id="readers-trigger" onClick={() => openDrawer("readers")} aria-haspopup="dialog" aria-expanded={drawer === "readers"}><PanelRight size={16} /><span>Reader notebook</span>{totalCommentCount > 0 && <span className="workbar-count">{totalCommentCount}</span>}</button>
      <button data-testid="generate-report-btn" className="workbar-report" disabled={loadingReport || !readingDone} onClick={generateReport} title={readingDone ? "Open editorial report" : "Available when your readers finish"}>{loadingReport ? <Loader2 size={15} className="animate-spin" /> : <FileText size={15} />}<span>Report</span></button>
    </div>
  </header>
    {!readingDone && <section className={`reading-progress-strip ${isStalled ? "is-paused" : ""}`} aria-label="Reading activity">
      <div className="reading-progress-copy" role="status"><strong>{!isStalled && <Loader2 size={16} className="reading-activity-spinner" />}{status}</strong><span>{totalCommentCount > 0 ? `${totalCommentCount} passage ${totalCommentCount === 1 ? "note" : "notes"} so far. New notes appear beside your manuscript` : "You can read along. Notes will appear as each reader finishes a section."}</span></div>
      <div className="reading-progress-meter"><span className="reading-progress-label">{percent}% read</span><div className={`workbar-progress ${percent === 0 && !isStalled ? "is-starting" : ""}`} role="progressbar" aria-label="Reading progress" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-valuetext={`${percent}% of reader sections complete${isStalled ? ", needs attention" : ""}`}><span style={{ width: `${percent}%` }} /></div></div>
    </section>}
  </>;
}
