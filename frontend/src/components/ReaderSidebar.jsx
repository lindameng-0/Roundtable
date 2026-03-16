import React, { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronRight, Loader2, MessageSquare, HelpCircle } from "lucide-react";
import { StallBanner } from "./StallBanner";

const READER_AVATAR_URLS = [
  "https://images.unsplash.com/photo-1581883556531-e5f8027f557f?crop=entropy&cs=srgb&fm=jpg&q=85&w=80",
  "https://images.unsplash.com/photo-1658909835269-e76abd3ffb5d?crop=entropy&cs=srgb&fm=jpg&q=85&w=80",
  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&q=80&w=80",
  "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&q=80&w=80",
  "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&q=80&w=80",
];

const READER_COLORS = ["#C86B56", "#5C5855", "#8da399", "#D4Af37", "#2D2A26"];

// New comment type set
const COMMENT_TYPE_COLORS = {
  reaction:   { bg: "#EBF4FF", text: "#2563EB", label: "Reaction" },
  confusion:  { bg: "#FFF5F5", text: "#DC2626", label: "Confusion" },
  question:   { bg: "#F0FDF4", text: "#16A34A", label: "Question" },
  craft:      { bg: "#F5F0FF", text: "#7C3AED", label: "Craft" },
  callback:   { bg: "#FFF7ED", text: "#EA580C", label: "Callback" },
  // legacy fallbacks
  prediction: { bg: "#F5F0FF", text: "#7C3AED", label: "Prediction" },
  critique:   { bg: "#FFF0F0", text: "#DC2626", label: "Critique" },
  praise:     { bg: "#F0FFF4", text: "#16A34A", label: "Praise" },
  theory:     { bg: "#FFF7ED", text: "#EA580C", label: "Theory" },
  comparison: { bg: "#F0FDFA", text: "#0D9488", label: "Comparison" },
};

const PERSONALITY_COLORS = {
  analytical: "#5C5855", emotional: "#C86B56", casual: "#8da399",
  skeptical: "#D4Af37", genre_savvy: "#2D2A26",
};

// New types only (for filter bar)
const CURRENT_TYPES = ["reaction", "confusion", "question", "craft", "callback"];

function getReaderDisplayName(persona, index) {
  const n = persona?.name;
  if (n != null && String(n).trim()) return String(n).trim();
  return `Reader ${(index ?? persona?.avatar_index ?? 0) + 1}`;
}

function ThinkingStrip({ thinkingReaders, personas }) {
  const entries = Array.from(thinkingReaders.entries());
  if (entries.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.2 }}
      className="mb-4 border border-ink-900/8 bg-white overflow-hidden"
      style={{ borderRadius: "2px" }}
      data-testid="thinking-strip"
    >
      <div className="px-3 py-2 border-b border-ink-900/6">
        <p className="text-xs text-ink-400 uppercase tracking-widest">Readers working now</p>
      </div>
      <div className="divide-y divide-ink-900/5">
        {entries.map(([readerId, info]) => {
          const readerColor = READER_COLORS[info.avatar_index ?? 0];
          const displayName = (info.reader_name && String(info.reader_name).trim()) || `Reader ${(info.avatar_index ?? 0) + 1}`;
          return (
            <div key={readerId} className="flex items-center gap-2.5 px-3 py-2.5">
              <div className="w-6 h-6 overflow-hidden flex-shrink-0" style={{ borderRadius: "2px", border: `1.5px solid ${readerColor}` }}>
                <img
                  src={READER_AVATAR_URLS[(info.avatar_index ?? 0) % READER_AVATAR_URLS.length]}
                  alt={displayName}
                  className="w-full h-full object-cover"
                  onError={(e) => { e.target.style.display = "none"; }}
                />
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-xs font-semibold text-ink-900">{displayName}</span>
                <span className="text-xs text-ink-400 ml-1.5">is reading section {info.section_number}...</span>
              </div>
              <div className="flex items-center gap-0.5 flex-shrink-0">
                {[0, 1, 2].map((i) => (
                  <motion.div
                    key={i}
                    className="w-1 h-1 rounded-full"
                    style={{ background: readerColor }}
                    animate={{ opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}

/**
 * A per-section journal entry within a reader card.
 * Shows reading_journal (primary), what_i_think_the_writer_is_doing (secondary),
 * questions_for_writer (highlighted), checking_in (collapsible).
 */
function SectionJournalEntry({ entry }) {
  const [showCheckingIn, setShowCheckingIn] = useState(false);
  const { section_number, reading_journal, what_i_think_the_writer_is_doing, questions_for_writer, checking_in } = entry;

  return (
    <div className="pt-3 pb-4 border-b border-ink-900/5 last:border-0">
      <p className="text-xs text-ink-400 uppercase tracking-widest mb-2">Section {section_number}</p>

      {/* Primary: Reading Journal */}
      {reading_journal && (
        <p
          className="text-sm text-ink-700 leading-relaxed mb-3"
          style={{
            fontFamily: "'Cormorant Garamond', serif",
            fontSize: "1rem",
            lineHeight: "1.75",
            fontStyle: "italic",
          }}
        >
          {reading_journal}
        </p>
      )}

      {/* Secondary: What the writer is doing */}
      {what_i_think_the_writer_is_doing && (
        <div className="mb-3">
          <p className="text-xs text-ink-400 uppercase tracking-widest mb-1">Intent read</p>
          <p className="text-xs text-ink-600 leading-relaxed">
            {what_i_think_the_writer_is_doing}
          </p>
        </div>
      )}

      {/* Questions for writer — visually highlighted */}
      {questions_for_writer && questions_for_writer.length > 0 && (
        <div className="space-y-1.5 mb-3">
          {questions_for_writer.map((q, i) => (
            <div
              key={i}
              className="flex gap-2 px-2.5 py-2 text-xs text-ink-700 leading-relaxed"
              style={{
                background: "rgba(200, 107, 86, 0.06)",
                borderLeft: "2px solid #C86B56",
                borderRadius: "0 2px 2px 0",
                fontFamily: "'Cormorant Garamond', serif",
                fontSize: "0.9rem",
                fontStyle: "italic",
              }}
            >
              <HelpCircle className="w-3 h-3 flex-shrink-0 mt-0.5 text-clay" strokeWidth={1.5} />
              <span>{q}</span>
            </div>
          ))}
        </div>
      )}

      {/* Checking in — low priority, collapsible */}
      {checking_in && (
        <div>
          <button
            onClick={() => setShowCheckingIn((s) => !s)}
            className="flex items-center gap-1 text-xs text-ink-400 hover:text-ink-600 transition-colors"
          >
            <ChevronRight
              className={`w-3 h-3 transition-transform ${showCheckingIn ? "rotate-90" : ""}`}
              strokeWidth={1.5}
            />
            Before reading
          </button>
          <AnimatePresence>
            {showCheckingIn && (
              <motion.p
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.18 }}
                className="overflow-hidden mt-1.5 text-xs text-ink-400 leading-relaxed pl-4"
                style={{ fontStyle: "italic" }}
              >
                {checking_in}
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}

function ReaderPanel({ persona, readerStatus, reflections, totalComments, activeTypes, allComments }) {
  const [expanded, setExpanded] = useState(false);
  const [showMoments, setShowMoments] = useState(false);
  const color = PERSONALITY_COLORS[persona?.personality] || "#5C5855";
  const readerColor = READER_COLORS[persona?.avatar_index ?? 0];
  const { currentSection, done } = readerStatus || {};

  // Moments filtered to this reader and active types
  const filteredMoments = useMemo(() => {
    return allComments.filter(
      (c) => c.readerId === persona.id && (activeTypes.size === 0 || activeTypes.has(c.comment?.type))
    );
  }, [allComments, persona.id, activeTypes]);

  // Sections with journals, sorted
  const sortedSections = useMemo(() => {
    return [...reflections].sort((a, b) => (a.section_number || 0) - (b.section_number || 0));
  }, [reflections]);

  const journalCount = sortedSections.length;
  const hasContent = journalCount > 0 || filteredMoments.length > 0;

  return (
    <div
      data-testid={`reader-panel-${getReaderDisplayName(persona).replace(/\s+/g, "-").toLowerCase()}`}
      className="border border-ink-900/8 bg-white mb-3 overflow-hidden"
      style={{ borderRadius: "2px" }}
    >
      <button
        className="w-full flex items-center gap-3 p-4 text-left hover:bg-paper transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="w-8 h-8 overflow-hidden flex-shrink-0" style={{ borderRadius: "2px", border: `2px solid ${readerColor}` }}>
          <img
            src={READER_AVATAR_URLS[(persona.avatar_index ?? 0) % READER_AVATAR_URLS.length]}
            alt={getReaderDisplayName(persona)}
            className="w-full h-full object-cover"
            onError={(e) => { e.target.style.display = "none"; }}
          />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-ink-900 truncate">{getReaderDisplayName(persona)}</p>
          <p className="text-xs" style={{ color }}>
            {done
              ? `${journalCount} journal${journalCount !== 1 ? "s" : ""} · ${totalComments} moment${totalComments !== 1 ? "s" : ""}`
              : currentSection
              ? `Reading section ${currentSection}...`
              : "Waiting..."}
          </p>
        </div>
        {done && <span className="text-xs text-sage mr-2 flex-shrink-0">Done</span>}
        {!done && currentSection && <Loader2 className="w-3.5 h-3.5 animate-spin text-ink-400 flex-shrink-0" strokeWidth={1.5} />}
        <ChevronDown className={`w-3.5 h-3.5 text-ink-400 transition-transform flex-shrink-0 ${expanded ? "rotate-180" : ""}`} strokeWidth={1.5} />
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} transition={{ duration: 0.22 }} className="overflow-hidden">
            <div className="px-4 pb-4 border-t border-ink-900/6">
              {/* Section journals */}
              {sortedSections.length > 0 && (
                <div className="mt-3 space-y-0">
                  {sortedSections.map((entry, i) => (
                    <SectionJournalEntry key={`${entry.readerId}-${entry.section_number}-${i}`} entry={entry} />
                  ))}
                </div>
              )}

              {/* Moments list (sparse, collapsible) */}
              {filteredMoments.length > 0 && (
                <div className="mt-3">
                  <button
                    onClick={() => setShowMoments((s) => !s)}
                    className="flex items-center gap-1 text-xs text-ink-400 hover:text-clay transition-colors"
                  >
                    <ChevronRight className={`w-3 h-3 transition-transform ${showMoments ? "rotate-90" : ""}`} strokeWidth={1.5} />
                    {showMoments ? "Hide" : "Show"} {filteredMoments.length} moment{filteredMoments.length !== 1 ? "s" : ""}
                  </button>
                  <AnimatePresence>
                    {showMoments && (
                      <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden mt-2 space-y-2">
                        {filteredMoments.map((c, i) => {
                          const typeStyle = COMMENT_TYPE_COLORS[c.comment?.type] || COMMENT_TYPE_COLORS.reaction;
                          return (
                            <div key={i} className="text-xs p-2 bg-paper" style={{ borderRadius: "2px" }}>
                              <div className="flex items-center gap-1.5 mb-1">
                                <span className="px-1.5 py-0.5 text-xs" style={{ background: typeStyle.bg, color: typeStyle.text, borderRadius: "2px" }}>{typeStyle.label}</span>
                                <span className="text-ink-400">¶{c.comment?.line}</span>
                              </div>
                              <p className="text-ink-600 leading-relaxed">{c.comment?.comment}</p>
                            </div>
                          );
                        })}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}

              {!hasContent && (
                <p className="text-xs text-ink-400 mt-3">No feedback yet</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/**
 * Aggregated questions panel: shows all questions from all readers, grouped.
 * Only shown when there are questions.
 */
function AggregatedQuestions({ reflections, personas }) {
  const [expanded, setExpanded] = useState(false);

  const allQuestions = useMemo(() => {
    const list = [];
    reflections.forEach((r) => {
      const persona = personas.find((p) => p.id === r.readerId);
      const readerName = getReaderDisplayName(persona, persona?.avatar_index);
      (r.questions_for_writer || []).forEach((q) => {
        list.push({ question: q, readerName, section_number: r.section_number });
      });
    });
    return list;
  }, [reflections, personas]);

  if (allQuestions.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-4 border border-clay/20 bg-white overflow-hidden"
      style={{ borderRadius: "2px" }}
    >
      <button
        className="w-full flex items-center justify-between px-3 py-2.5 text-left hover:bg-paper transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="flex items-center gap-2">
          <HelpCircle className="w-3.5 h-3.5 text-clay" strokeWidth={1.5} />
          <p className="text-xs text-clay uppercase tracking-widest font-medium">
            {allQuestions.length} question{allQuestions.length !== 1 ? "s" : ""} for you
          </p>
        </div>
        <ChevronDown className={`w-3 h-3 text-clay/60 transition-transform ${expanded ? "rotate-180" : ""}`} strokeWidth={1.5} />
      </button>
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: "auto" }}
            exit={{ height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 space-y-2 border-t border-clay/10">
              {allQuestions.map((item, i) => (
                <div key={i} className="pt-2">
                  <p
                    className="text-xs text-ink-700 leading-relaxed"
                    style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: "0.9rem", fontStyle: "italic" }}
                  >
                    {item.question}
                  </p>
                  <p className="text-xs text-ink-400 mt-0.5">
                    {item.readerName} · §{item.section_number}
                  </p>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

/**
 * The right sidebar: reader cards, type filters, thinking strip, stall banner.
 */
export function ReaderSidebar({
  personas,
  readerStatus,
  reflections,
  allComments,
  thinkingReaders,
  totalCommentCount,
  activeTypes,
  toggleType,
  setActiveTypes,
  isStalled,
  readingDone,
  onRetry,
  onViewPartial,
}) {
  const readerReflections = (readerId) => reflections.filter((r) => r.readerId === readerId);

  // Count total questions across all readers
  const totalQuestions = useMemo(
    () => reflections.reduce((sum, r) => sum + (r.questions_for_writer?.length || 0), 0),
    [reflections]
  );

  return (
    <div className="w-2/5 overflow-y-auto bg-paper-dark flex flex-col" data-testid="reactions-sidebar">
      <div className="p-5 flex-1">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs text-ink-400 uppercase tracking-widest">Your Readers</h3>
          {totalCommentCount > 0 && (
            <span className="text-xs text-ink-400">
              {totalCommentCount} moment{totalCommentCount !== 1 ? "s" : ""}
            </span>
          )}
        </div>

        {/* Moment type filter — only show if there are moments */}
        {totalCommentCount > 0 && (
          <div className="mb-4">
            <p className="text-xs text-ink-400 mb-2">Filter moments</p>
            <div className="flex flex-wrap gap-1.5">
              {CURRENT_TYPES.map((type) => {
                const typeStyle = COMMENT_TYPE_COLORS[type];
                const isActive = activeTypes.has(type);
                return (
                  <button
                    key={type}
                    data-testid={`filter-type-${type}`}
                    onClick={() => toggleType(type)}
                    className="text-xs px-2 py-1 border transition-all duration-150"
                    style={{
                      borderRadius: "2px",
                      background: isActive ? typeStyle.bg : "white",
                      color: isActive ? typeStyle.text : "#8C8885",
                      borderColor: isActive ? typeStyle.text + "40" : "rgba(45,42,38,0.1)",
                    }}
                  >
                    {typeStyle.label}
                  </button>
                );
              })}
              {activeTypes.size > 0 && (
                <button onClick={() => setActiveTypes(new Set())} className="text-xs px-2 py-1 text-ink-400 hover:text-clay transition-colors">
                  Clear
                </button>
              )}
            </div>
          </div>
        )}

        <AnimatePresence>
          {isStalled && !readingDone && <StallBanner onRetry={onRetry} onViewPartial={onViewPartial} />}
        </AnimatePresence>

        <AnimatePresence>
          {thinkingReaders.size > 0 && <ThinkingStrip thinkingReaders={thinkingReaders} personas={personas} />}
        </AnimatePresence>

        {/* Aggregated questions panel */}
        {totalQuestions > 0 && (
          <AggregatedQuestions reflections={reflections} personas={personas} />
        )}

        {personas.map((persona) => {
          const status = readerStatus[persona.id] || { currentSection: null, done: false, totalComments: 0 };
          return (
            <ReaderPanel
              key={persona.id}
              persona={persona}
              readerStatus={status}
              reflections={readerReflections(persona.id)}
              totalComments={status.totalComments || 0}
              activeTypes={activeTypes}
              allComments={allComments}
            />
          );
        })}

        {personas.length === 0 && (
          <div className="text-center py-16">
            <MessageSquare className="w-6 h-6 text-ink-400 mx-auto mb-3" strokeWidth={1.5} />
            <p className="text-sm text-ink-400">Loading readers...</p>
          </div>
        )}
      </div>
    </div>
  );
}
