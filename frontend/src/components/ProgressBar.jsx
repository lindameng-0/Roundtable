import React from "react";
import { motion } from "framer-motion";
import { BarChart2, Loader2 } from "lucide-react";
import { UserMenu } from "./UserMenu";

/**
 * Top header bar: back link, manuscript title, reading status, and report button.
 * Includes the animated progress bar strip.
 */
export function ProgressBar({
  manuscript,
  navigate,
  readingDone,
  processingSection,
  totalSections,
  loadingReport,
  generateReport,
  progress,
  workflowProgress,
  workflowUsage,
  workflowModels,
  workflowBudget,
}) {
  const cost = workflowUsage?.estimated_cost_usd;
  return (
    <header className="border-b border-ink-900/8 bg-paper flex-shrink-0 z-20">
      <div className="px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            data-testid="back-to-setup-btn"
            onClick={() => navigate("/")}
            className="text-xs text-ink-400 hover:text-ink-900 transition-colors"
          >
            ← Roundtable
          </button>
          <div className="h-4 w-px bg-ink-900/10" />
          <h1
            className="font-serif text-lg text-ink-900 truncate max-w-xs"
            style={{ fontFamily: "'Cormorant Garamond', serif" }}
          >
            {manuscript.title}
          </h1>
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-2 text-xs text-ink-400">
            {readingDone ? (
              <span className="text-sage font-medium">Reading complete</span>
            ) : processingSection ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />
                <span>Readers on section {processingSection} of {totalSections}</span>
              </>
            ) : (
              <span>Starting...</span>
            )}
          </div>
          {workflowProgress?.total > 0 && (
            <div className="hidden md:block text-right text-xs text-ink-400" title="Estimated from recorded model token usage; provider billing is authoritative.">
              <p>{workflowProgress.completed}/{workflowProgress.total} reader tasks</p>
              {workflowModels?.length > 0 && <p>{workflowModels.join(" · ")}</p>}
              {cost !== undefined && cost !== null && (
                <p>{workflowUsage?.has_unknown_cost ? "Known cost " : "Estimated "}${Number(cost).toFixed(4)}</p>
              )}
              {workflowBudget && <p>Budget ${Number(workflowBudget.spent_usd || 0).toFixed(4)} / ${Number(workflowBudget.limit_usd || 0).toFixed(2)}</p>}
            </div>
          )}

          <button
            data-testid="generate-report-btn"
            onClick={readingDone ? generateReport : undefined}
            disabled={loadingReport || !readingDone}
            title={!readingDone ? "Readers are still reading — please wait until all sections are complete" : "Generate Editor Report"}
            className="flex items-center gap-2 text-xs border border-ink-900/12 hover:border-clay text-ink-600 hover:text-clay px-3 py-2 transition-all disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:border-ink-900/12 disabled:hover:text-ink-600"
            style={{ borderRadius: "2px" }}
          >
            {loadingReport ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />
            ) : (
              <BarChart2 className="w-3.5 h-3.5" strokeWidth={1.5} />
            )}
            Editor Report
          </button>
          <UserMenu />
        </div>
      </div>

      <div className="section-progress">
        <motion.div
          className="section-progress-fill"
          initial={false}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.6 }}
        />
      </div>
    </header>
  );
}
