import React from "react";
import { motion, AnimatePresence } from "framer-motion";

// New comment type set: reaction | confusion | question | craft | callback
const TYPE_COLORS = {
  reaction:  { color: "#2563EB", label: "Reaction" },
  confusion: { color: "#DC2626", label: "Confusion" },
  question:  { color: "#16A34A", label: "Question" },
  craft:     { color: "#7C3AED", label: "Craft" },
  callback:  { color: "#EA580C", label: "Callback" },
  // legacy fallbacks
  prediction: { color: "#7C3AED", label: "Prediction" },
  critique:   { color: "#DC2626", label: "Critique" },
  praise:     { color: "#16A34A", label: "Praise" },
  theory:     { color: "#EA580C", label: "Theory" },
  comparison: { color: "#0D9488", label: "Comparison" },
};

/**
 * Popover shown when a reader clicks a margin dot.
 * Shows all comments on a given line, filtered by active comment types.
 */
export function CommentPopover({ lineNum, comments, activeTypes, onClose }) {
  const filtered = activeTypes.size > 0 ? comments.filter((c) => activeTypes.has(c.type)) : comments;
  if (!filtered.length) return null;

  return (
    <AnimatePresence>
      <motion.div
        key={`popover-${lineNum}`}
        initial={{ opacity: 0, x: 8 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: 8 }}
        transition={{ duration: 0.18 }}
        className="absolute left-full top-0 ml-3 z-50 w-72 bg-white border border-ink-900/12 shadow-xl"
        style={{ borderRadius: "2px" }}
        data-testid="comment-popover"
      >
        <div className="p-1">
          {filtered.map((c, i) => {
            const typeInfo = TYPE_COLORS[c.type] || TYPE_COLORS.reaction;
            return (
              <div
                key={i}
                className={`p-3 ${i < filtered.length - 1 ? "border-b border-ink-900/6" : ""}`}
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <span
                    className="text-xs uppercase tracking-widest font-semibold px-1.5 py-0.5"
                    style={{
                      color: typeInfo.color,
                      background: `${typeInfo.color}15`,
                      borderRadius: "2px",
                    }}
                  >
                    {typeInfo.label}
                  </span>
                  <span className="text-xs text-ink-400">{c.readerName}</span>
                </div>
                <p className="text-sm text-ink-800 leading-relaxed" style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: "0.95rem" }}>
                  {c.comment}
                </p>
              </div>
            );
          })}
        </div>
        <button
          onClick={onClose}
          className="absolute top-2 right-2 text-ink-400 hover:text-ink-700 text-xs"
          data-testid="close-comment-popover"
        >
          ×
        </button>
      </motion.div>
    </AnimatePresence>
  );
}
