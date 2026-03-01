import React, { useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BarChart2, Loader2 } from "lucide-react";
import { X } from "lucide-react";

const READER_AVATAR_URLS = [
  "https://images.unsplash.com/photo-1581883556531-e5f8027f557f?crop=entropy&cs=srgb&fm=jpg&q=85&w=80",
  "https://images.unsplash.com/photo-1658909835269-e76abd3ffb5d?crop=entropy&cs=srgb&fm=jpg&q=85&w=80",
  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&q=80&w=80",
  "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&q=80&w=80",
  "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&q=80&w=80",
];

const READER_COLORS = ["#C86B56", "#5C5855", "#8da399", "#D4Af37", "#2D2A26"];

const COMMENT_TYPE_COLORS = {
  reaction:   { bg: "#EBF4FF", text: "#2563EB", label: "Reaction" },
  prediction: { bg: "#F5F0FF", text: "#7C3AED", label: "Prediction" },
  confusion:  { bg: "#F5F5F5", text: "#6B7280", label: "Confusion" },
  critique:   { bg: "#FFF0F0", text: "#DC2626", label: "Critique" },
  praise:     { bg: "#F0FFF4", text: "#16A34A", label: "Praise" },
  theory:     { bg: "#FFF7ED", text: "#EA580C", label: "Theory" },
  comparison: { bg: "#F0FDFA", text: "#0D9488", label: "Comparison" },
};

function MarginDot({ lineNumber, comments, personas, onOpen }) {
  const readerGroups = useMemo(() => {
    const groups = {};
    comments.forEach(({ readerId }) => {
      if (!groups[readerId]) groups[readerId] = [];
      groups[readerId].push(readerId);
    });
    return groups;
  }, [comments]);

  const readerIds = Object.keys(readerGroups);

  return (
    <motion.button
      data-testid={`margin-dot-line-${lineNumber}`}
      initial={{ scale: 0, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
      onClick={(e) => { e.stopPropagation(); onOpen(lineNumber, e); }}
      className="absolute left-0 top-1/2 -translate-y-1/2 flex items-center gap-px cursor-pointer z-10"
      style={{ transform: "translateY(-50%)" }}
    >
      {readerIds.slice(0, 3).map((rid, i) => {
        const persona = personas.find((p) => p.id === rid);
        const color = READER_COLORS[persona?.avatar_index ?? i];
        return (
          <div
            key={rid}
            className="w-2.5 h-2.5 rounded-full border border-white shadow-sm flex-shrink-0"
            style={{ background: color, marginLeft: i > 0 ? "-4px" : "0", zIndex: 3 - i }}
          />
        );
      })}
      {readerIds.length > 3 && (
        <span className="text-xs text-ink-400 ml-1">+{readerIds.length - 3}</span>
      )}
    </motion.button>
  );
}

function CommentPopover({ lineNumber, commentsByLine, personas, onClose }) {
  const comments = commentsByLine[lineNumber] || [];
  return (
    <motion.div
      initial={{ opacity: 0, y: -8, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.96 }}
      transition={{ duration: 0.18 }}
      data-testid="comment-popover"
      className="absolute left-8 bg-white border border-ink-900/10 shadow-xl z-50 w-80"
      style={{ borderRadius: "4px", top: "0" }}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-ink-900/6">
        <p className="text-xs text-ink-400 uppercase tracking-widest">Line {lineNumber}</p>
        <button onClick={onClose} className="text-ink-400 hover:text-ink-900 transition-colors">
          <X className="w-3.5 h-3.5" strokeWidth={1.5} />
        </button>
      </div>
      <div className="max-h-72 overflow-y-auto">
        {comments.map((c, i) => {
          const persona = personas.find((p) => p.id === c.readerId);
          const avatarIdx = persona?.avatar_index ?? 0;
          const readerColor = READER_COLORS[avatarIdx];
          const typeStyle = COMMENT_TYPE_COLORS[c.comment?.type] || COMMENT_TYPE_COLORS.reaction;
          return (
            <div key={i} className={`px-4 py-3 ${i > 0 ? "border-t border-ink-900/6" : ""}`}>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-5 h-5 rounded-sm overflow-hidden flex-shrink-0" style={{ border: `1.5px solid ${readerColor}` }}>
                  <img
                    src={READER_AVATAR_URLS[avatarIdx % READER_AVATAR_URLS.length]}
                    alt={c.readerName}
                    className="w-full h-full object-cover"
                    onError={(e) => { e.target.style.display = "none"; }}
                  />
                </div>
                <span className="text-xs font-semibold text-ink-900">{c.readerName}</span>
                <span className="text-xs px-1.5 py-0.5 ml-auto" style={{ background: typeStyle.bg, color: typeStyle.text, borderRadius: "2px" }}>
                  {typeStyle.label}
                </span>
              </div>
              <p className="text-sm text-ink-600 leading-relaxed">{c.comment?.comment}</p>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}

function AnnotatedParagraph({ lineData, commentsByLine, personas, openPopoverLine, onOpenPopover }) {
  const { line, text } = lineData;
  const hasComments = !!(commentsByLine[line]?.length);
  const isOpen = openPopoverLine === line;

  return (
    <div className="relative mb-5 pl-8" style={{ minHeight: "1.5em" }}>
      <div className="absolute left-0 top-0 bottom-0 w-8 flex items-start pt-1">
        {hasComments && (
          <MarginDot lineNumber={line} comments={commentsByLine[line]} personas={personas} onOpen={onOpenPopover} />
        )}
      </div>
      <p
        data-line={line}
        className={`manuscript-text transition-colors duration-200 ${hasComments ? "cursor-pointer" : ""}`}
        style={{
          fontFamily: "'Cormorant Garamond', serif",
          fontSize: "1.1rem",
          lineHeight: "1.9",
          background: isOpen ? "rgba(200, 107, 86, 0.04)" : "transparent",
          borderRadius: "2px",
          padding: "0 2px",
        }}
        onClick={hasComments ? (e) => onOpenPopover(line, e) : undefined}
      >
        {text}
      </p>
      <AnimatePresence>
        {isOpen && (
          <CommentPopover
            lineNumber={line}
            commentsByLine={commentsByLine}
            personas={personas}
            onClose={() => onOpenPopover(null, null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

/**
 * The scrollable left panel: manuscript text with inline annotation dots.
 */
export function ManuscriptView({
  manuscript,
  commentsByLine,
  personas,
  openPopoverLine,
  onOpenPopover,
  readingDone,
  totalSections,
  totalCommentCount,
  generateReport,
  loadingReport,
}) {
  return (
    <div
      className="w-3/5 border-r border-ink-900/8 overflow-y-auto paper-texture"
      data-testid="manuscript-panel"
      onClick={() => onOpenPopover(null, null)}
    >
      <div className="max-w-2xl mx-auto px-8 py-12">
        <div className="mb-10">
          <h1 className="font-serif text-3xl text-ink-900 mb-2" style={{ fontFamily: "'Cormorant Garamond', serif" }}>
            {manuscript.title}
          </h1>
          <div className="flex items-center gap-3 text-xs text-ink-400">
            <span>{manuscript.genre}</span>
            <span>·</span>
            <span>{totalCommentCount} annotations</span>
          </div>
          <div className="w-16 h-px bg-clay mt-4" />
        </div>

        {manuscript.sections?.sort((a, b) => a.section_number - b.section_number).map((section) => (
          <div key={section.section_number} className="mb-10">
            <h2
              className="font-serif text-xl text-ink-900 mb-6 pt-4 border-t border-ink-900/8"
              style={{ fontFamily: "'Cormorant Garamond', serif" }}
            >
              {section.title}
            </h2>
            {(section.paragraph_lines || []).map((lineData) => (
              <AnnotatedParagraph
                key={lineData.line}
                lineData={lineData}
                commentsByLine={commentsByLine}
                personas={personas}
                openPopoverLine={openPopoverLine}
                onOpenPopover={onOpenPopover}
              />
            ))}
          </div>
        ))}

        {readingDone && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-8 p-6 border border-clay/20 bg-clay/5"
            style={{ borderRadius: "2px" }}
            data-testid="reading-complete-banner"
          >
            <h3 className="font-serif text-xl text-ink-900 mb-2" style={{ fontFamily: "'Cormorant Garamond', serif" }}>
              Your readers have finished.
            </h3>
            <p className="text-sm text-ink-600 mb-4">
              {totalCommentCount} {totalCommentCount === 1 ? "annotation" : "annotations"} across {totalSections} {totalSections === 1 ? "section" : "sections"}. Ready for the editorial synthesis?
            </p>
            <button
              data-testid="generate-report-complete-btn"
              onClick={generateReport}
              disabled={loadingReport}
              className="flex items-center gap-2 bg-clay hover:bg-clay-hover text-white px-5 py-2.5 text-sm font-medium transition-all"
              style={{ borderRadius: "2px" }}
            >
              {loadingReport ? <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.5} /> : <BarChart2 className="w-4 h-4" strokeWidth={1.5} />}
              Generate Editor Report
            </button>
          </motion.div>
        )}
      </div>
    </div>
  );
}
