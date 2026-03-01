import React, { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronRight, Loader2, MessageSquare } from "lucide-react";
import { StallBanner } from "./StallBanner";

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

const PERSONALITY_COLORS = {
  analytical: "#5C5855", emotional: "#C86B56", casual: "#8da399",
  skeptical: "#D4Af37", genre_savvy: "#2D2A26",
};

const ALL_TYPES = Object.keys(COMMENT_TYPE_COLORS);

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
          return (
            <div key={readerId} className="flex items-center gap-2.5 px-3 py-2.5">
              <div className="w-6 h-6 overflow-hidden flex-shrink-0" style={{ borderRadius: "2px", border: `1.5px solid ${readerColor}` }}>
                <img
                  src={READER_AVATAR_URLS[(info.avatar_index ?? 0) % READER_AVATAR_URLS.length]}
                  alt={info.reader_name}
                  className="w-full h-full object-cover"
                  onError={(e) => { e.target.style.display = "none"; }}
                />
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-xs font-medium text-ink-900">{info.reader_name}</span>
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

function ReaderPanel({ persona, readerStatus, reflections, totalComments, activeTypes, allComments }) {
  const [expanded, setExpanded] = useState(false);
  const [showAllComments, setShowAllComments] = useState(false);
  const color = PERSONALITY_COLORS[persona?.personality] || "#5C5855";
  const readerColor = READER_COLORS[persona?.avatar_index ?? 0];
  const { currentSection, done } = readerStatus || {};

  const filteredComments = useMemo(() => {
    return allComments.filter(
      (c) => c.readerId === persona.id && (activeTypes.size === 0 || activeTypes.has(c.comment?.type))
    );
  }, [allComments, persona.id, activeTypes]);

  return (
    <div
      data-testid={`reader-panel-${persona.name.replace(/\s+/g, "-").toLowerCase()}`}
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
            alt={persona.name}
            className="w-full h-full object-cover"
            onError={(e) => { e.target.style.display = "none"; }}
          />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-ink-900 truncate">{persona.name}</p>
          <p className="text-xs" style={{ color }}>
            {done ? `${totalComments} comments` : currentSection ? `Reading section ${currentSection}...` : "Waiting..."}
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
              {reflections.length > 0 && (
                <div className="mt-3 space-y-3">
                  {reflections.map((r, i) => (
                    <div key={i}>
                      <p className="text-xs text-ink-400 mb-1 mt-2">After section {r.section_number}</p>
                      <p className="text-sm text-ink-600 leading-relaxed" style={{ fontFamily: "'Cormorant Garamond', serif", fontStyle: "italic" }}>
                        {r.reflection}
                      </p>
                    </div>
                  ))}
                </div>
              )}
              {filteredComments.length > 0 && (
                <div className="mt-3">
                  <button
                    onClick={() => setShowAllComments((s) => !s)}
                    className="flex items-center gap-1 text-xs text-ink-400 hover:text-clay transition-colors"
                  >
                    <ChevronRight className={`w-3 h-3 transition-transform ${showAllComments ? "rotate-90" : ""}`} strokeWidth={1.5} />
                    {showAllComments ? "Hide" : "Show"} {filteredComments.length} comment{filteredComments.length !== 1 ? "s" : ""}
                  </button>
                  <AnimatePresence>
                    {showAllComments && (
                      <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden mt-2 space-y-2">
                        {filteredComments.map((c, i) => {
                          const typeStyle = COMMENT_TYPE_COLORS[c.comment?.type] || COMMENT_TYPE_COLORS.reaction;
                          return (
                            <div key={i} className="text-xs p-2 bg-paper" style={{ borderRadius: "2px" }}>
                              <div className="flex items-center gap-1.5 mb-1">
                                <span className="px-1.5 py-0.5 text-xs" style={{ background: typeStyle.bg, color: typeStyle.text, borderRadius: "2px" }}>{typeStyle.label}</span>
                                <span className="text-ink-400">L{c.comment?.line}</span>
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
              {filteredComments.length === 0 && reflections.length === 0 && (
                <p className="text-xs text-ink-400 mt-3">No comments yet</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
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

  return (
    <div className="w-2/5 overflow-y-auto bg-paper-dark flex flex-col" data-testid="reactions-sidebar">
      <div className="p-5 flex-1">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs text-ink-400 uppercase tracking-widest">Your Readers</h3>
          {totalCommentCount > 0 && <span className="text-xs text-ink-400">{totalCommentCount} annotations</span>}
        </div>

        {totalCommentCount > 0 && (
          <div className="mb-4">
            <p className="text-xs text-ink-400 mb-2">Filter by type</p>
            <div className="flex flex-wrap gap-1.5">
              {ALL_TYPES.map((type) => {
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
