import React from "react";
import { BarChart2, Loader2 } from "lucide-react";

export function ProgressBar({ manuscript, readingDone, processingSection, totalSections, loadingReport, generateReport, progress }) {
  return <header className="border-b border-ink-900/10 flex-shrink-0">
    <div className="reading-toolbar"><div><h1 title={manuscript.title}>{manuscript.title}</h1><p role="status">{readingDone ? "Your readers have finished. Explore their notes or open the report." : processingSection ? `Reading section ${processingSection} of ${totalSections}` : "Preparing your reading room…"}</p></div><button data-testid="generate-report-btn" onClick={generateReport} disabled={loadingReport || !readingDone} title={!readingDone ? "Available when all readers finish" : "Open editorial report"} className="button button-primary disabled:opacity-40">{loadingReport ? <Loader2 size={15} className="animate-spin" /> : <BarChart2 size={15} />}Editor report</button></div>
    <div className="section-progress" role="progressbar" aria-label="Reading progress" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100}><div className="section-progress-fill" style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} /></div>
  </header>;
}
