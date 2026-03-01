import React from "react";
import { motion, AnimatePresence } from "framer-motion";

/**
 * Banner shown when no SSE events have arrived in 60 seconds.
 */
export function StallBanner({ onRetry, onViewPartial }) {
  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.2 }}
        className="mb-4 p-4 border border-amber-200 bg-amber-50"
        style={{ borderRadius: "2px" }}
        data-testid="stall-warning-banner"
      >
        <p className="text-xs text-amber-800 mb-3 leading-relaxed">
          Reading appears to be taking longer than expected. This can happen when the AI is processing a complex section.
        </p>
        <div className="flex gap-2">
          <button
            data-testid="retry-reading-btn"
            onClick={onRetry}
            className="text-xs px-3 py-1.5 bg-amber-700 text-white hover:bg-amber-800 transition-colors"
            style={{ borderRadius: "2px" }}
          >
            Retry
          </button>
          <button
            data-testid="view-partial-results-btn"
            onClick={onViewPartial}
            className="text-xs px-3 py-1.5 border border-amber-700 text-amber-700 hover:bg-amber-100 transition-colors"
            style={{ borderRadius: "2px" }}
          >
            View partial results
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
