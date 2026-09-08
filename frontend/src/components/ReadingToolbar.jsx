import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, List, PanelRight, BookOpen, FileText, Loader2 } from "lucide-react";
import { TableMark } from "./Brand";

export default function ReadingToolbar({ drawer, openDrawer, focusMode, setFocusMode, readingDone, processingSection, totalSections, progress, totalCommentCount, loadingReport, generateReport }) {
  return <header className="reading-workbar">
    <nav className="workbar-location" aria-label="Reading navigation">
      <Link to="/dashboard" className="workbar-home" aria-label="Back to manuscripts"><TableMark /><ArrowLeft size={14} /><span>Manuscripts</span></Link>
      <span className="workbar-divider" aria-hidden="true" />
      <button id="contents-trigger" onClick={() => openDrawer("contents")} aria-haspopup="dialog" aria-expanded={drawer === "contents"}><List size={16} />Contents</button>
    </nav>
    <p className="workbar-status" role="status">{readingDone ? "Reading complete" : processingSection ? `Readers at section ${processingSection} of ${totalSections}` : "Your readers are getting settled"}</p>
    <div className="workbar-tools">
      <button onClick={() => setFocusMode(!focusMode)} aria-pressed={focusMode} title="Hide annotations for uninterrupted reading"><BookOpen size={16} /><span>Focus</span></button>
      <button id="readers-trigger" onClick={() => openDrawer("readers")} aria-haspopup="dialog" aria-expanded={drawer === "readers"}><PanelRight size={16} /><span>Reader notebook</span>{totalCommentCount > 0 && <span className="workbar-count">{totalCommentCount}</span>}</button>
      <button data-testid="generate-report-btn" className="workbar-report" disabled={loadingReport || !readingDone} onClick={generateReport} title={readingDone ? "Open editorial report" : "Available when your readers finish"}>{loadingReport ? <Loader2 size={15} className="animate-spin" /> : <FileText size={15} />}<span>Report</span></button>
    </div>
    {!readingDone && <div className="workbar-progress" role="progressbar" aria-label="Reading progress" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} /></div>}
  </header>;
}
