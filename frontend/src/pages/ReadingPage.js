import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { BarChart2, Loader2, ChevronDown, ChevronRight, MessageSquare, X } from "lucide-react";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const READER_AVATAR_URLS = [
  "https://images.unsplash.com/photo-1581883556531-e5f8027f557f?crop=entropy&cs=srgb&fm=jpg&q=85&w=80",
  "https://images.unsplash.com/photo-1658909835269-e76abd3ffb5d?crop=entropy&cs=srgb&fm=jpg&q=85&w=80",
  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&q=80&w=80",
  "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&q=80&w=80",
  "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&q=80&w=80",
];

// Consistent color per reader (by avatar_index)
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

const ALL_TYPES = Object.keys(COMMENT_TYPE_COLORS);

const PERSONALITY_COLORS = {
  analytical: "#5C5855",
  emotional: "#C86B56",
  casual: "#8da399",
  skeptical: "#D4Af37",
  genre_savvy: "#2D2A26",
};

// ─── Margin Dot ───────────────────────────────────────────────────────────────
function MarginDot({ lineNumber, comments, personas, onOpen }) {
  // Group by reader
  const readerGroups = useMemo(() => {
    const groups = {};
    comments.forEach(({ readerId, comment }) => {
      if (!groups[readerId]) groups[readerId] = [];
      groups[readerId].push(comment);
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
            style={{
              background: color,
              marginLeft: i > 0 ? "-4px" : "0",
              zIndex: 3 - i,
            }}
          />
        );
      })}
      {readerIds.length > 3 && (
        <span className="text-xs text-ink-400 ml-1">+{readerIds.length - 3}</span>
      )}
    </motion.button>
  );
}

// ─── Comment Popover ──────────────────────────────────────────────────────────
function CommentPopover({ lineNumber, commentsByLine, personas, onClose }) {
  const comments = commentsByLine[lineNumber] || [];
  const popoverRef = useRef(null);

  useEffect(() => {
    const handleKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <motion.div
      ref={popoverRef}
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
          const typeStyle = COMMENT_TYPE_COLORS[c.comment.type] || COMMENT_TYPE_COLORS.reaction;
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
                <span
                  className="text-xs px-1.5 py-0.5 ml-auto"
                  style={{
                    background: typeStyle.bg,
                    color: typeStyle.text,
                    borderRadius: "2px",
                  }}
                >
                  {typeStyle.label}
                </span>
              </div>
              <p className="text-sm text-ink-600 leading-relaxed">{c.comment.comment}</p>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}

// ─── Annotated Paragraph ─────────────────────────────────────────────────────
function AnnotatedParagraph({ lineData, commentsByLine, personas, openPopoverLine, onOpenPopover }) {
  const { line, text } = lineData;
  const hasComments = commentsByLine[line] && commentsByLine[line].length > 0;
  const isOpen = openPopoverLine === line;

  return (
    <div className="relative mb-5 pl-8" style={{ minHeight: "1.5em" }}>
      {/* Margin area */}
      <div className="absolute left-0 top-0 bottom-0 w-8 flex items-start pt-1">
        {hasComments && (
          <MarginDot
            lineNumber={line}
            comments={commentsByLine[line]}
            personas={personas}
            onOpen={onOpenPopover}
          />
        )}
      </div>

      {/* Text */}
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

      {/* Popover anchored to paragraph */}
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

// ─── Thinking Strip ───────────────────────────────────────────────────────────
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
          const persona = personas.find((p) => p.id === readerId);
          const readerColor = READER_COLORS[info.avatar_index ?? 0];
          return (
            <div key={readerId} className="flex items-center gap-2.5 px-3 py-2.5">
              <div
                className="w-6 h-6 overflow-hidden flex-shrink-0"
                style={{ borderRadius: "2px", border: `1.5px solid ${readerColor}` }}
              >
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
              {/* Animated dots */}
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

// ─── Reader Panel (Sidebar) ───────────────────────────────────────────────────
function ReaderPanel({ persona, readerStatus, reflections, totalComments, activeTypes, allComments }) {
  const [expanded, setExpanded] = useState(false);
  const [showAllComments, setShowAllComments] = useState(false);
  const color = PERSONALITY_COLORS[persona?.personality] || "#5C5855";
  const readerColor = READER_COLORS[persona?.avatar_index ?? 0];
  const { currentSection, totalSections, done } = readerStatus || {};

  const filteredComments = useMemo(() => {
    return allComments.filter(
      (c) => c.readerId === persona.id && (activeTypes.size === 0 || activeTypes.has(c.comment.type))
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
        <div
          className="w-8 h-8 overflow-hidden flex-shrink-0"
          style={{ borderRadius: "2px", border: `2px solid ${readerColor}` }}
        >
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
            {done
              ? `${totalComments} comments`
              : currentSection
              ? `Reading section ${currentSection}...`
              : "Waiting..."}
          </p>
        </div>
        {done && (
          <span className="text-xs text-sage mr-2 flex-shrink-0">Done</span>
        )}
        {!done && currentSection && (
          <Loader2 className="w-3.5 h-3.5 animate-spin text-ink-400 flex-shrink-0" strokeWidth={1.5} />
        )}
        <ChevronDown
          className={`w-3.5 h-3.5 text-ink-400 transition-transform flex-shrink-0 ${expanded ? "rotate-180" : ""}`}
          strokeWidth={1.5}
        />
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: "auto" }}
            exit={{ height: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 border-t border-ink-900/6">
              {/* Section reflections */}
              {reflections.length > 0 && (
                <div className="mt-3 space-y-3">
                  {reflections.map((r, i) => (
                    <div key={i} className="text-xs text-ink-400 uppercase tracking-widest mb-1">
                      <p className="text-xs text-ink-400 mb-1 mt-2">After section {r.section_number}</p>
                      <p
                        className="text-sm text-ink-600 leading-relaxed normal-case tracking-normal"
                        style={{ fontFamily: "'Cormorant Garamond', serif", fontStyle: "italic" }}
                      >
                        {r.reflection}
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {/* Show all comments toggle */}
              {filteredComments.length > 0 && (
                <div className="mt-3">
                  <button
                    onClick={() => setShowAllComments((s) => !s)}
                    className="flex items-center gap-1 text-xs text-ink-400 hover:text-clay transition-colors"
                  >
                    <ChevronRight
                      className={`w-3 h-3 transition-transform ${showAllComments ? "rotate-90" : ""}`}
                      strokeWidth={1.5}
                    />
                    {showAllComments ? "Hide" : "Show"} {filteredComments.length} comment{filteredComments.length !== 1 ? "s" : ""}
                  </button>

                  <AnimatePresence>
                    {showAllComments && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden mt-2 space-y-2"
                      >
                        {filteredComments.map((c, i) => {
                          const typeStyle = COMMENT_TYPE_COLORS[c.comment.type] || COMMENT_TYPE_COLORS.reaction;
                          return (
                            <div key={i} className="text-xs p-2 bg-paper" style={{ borderRadius: "2px" }}>
                              <div className="flex items-center gap-1.5 mb-1">
                                <span
                                  className="px-1.5 py-0.5 text-xs"
                                  style={{ background: typeStyle.bg, color: typeStyle.text, borderRadius: "2px" }}
                                >
                                  {typeStyle.label}
                                </span>
                                <span className="text-ink-400">L{c.comment.line}</span>
                              </div>
                              <p className="text-ink-600 leading-relaxed">{c.comment.comment}</p>
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

// ─── Main ReadingPage ─────────────────────────────────────────────────────────
export default function ReadingPage() {
  const { manuscriptId } = useParams();
  const navigate = useNavigate();
  const [manuscript, setManuscript] = useState(null);
  const [personas, setPersonas] = useState([]);
  const [loadingReport, setLoadingReport] = useState(false);
  const [readingDone, setReadingDone] = useState(false);

  // currentSection being processed (for status bar)
  const [processingSection, setProcessingSection] = useState(null);
  const [totalSections, setTotalSections] = useState(0);

  // commentsByLine: Map<lineNumber, [{readerId, readerName, comment: {line, type, comment}}]>
  const [commentsByLine, setCommentsByLine] = useState({});

  // readerStatus: Map<readerId, {currentSection, done, totalComments}>
  const [readerStatus, setReaderStatus] = useState({});

  // reflections: [{readerId, section_number, reflection}]
  const [reflections, setReflections] = useState([]);

  // Flat list of all comments for sidebar filtering
  const [allComments, setAllComments] = useState([]);

  // Sidebar type filter
  const [activeTypes, setActiveTypes] = useState(new Set());

  // Popover state
  const [openPopoverLine, setOpenPopoverLine] = useState(null);

  // thinkingReaders: Set of reader_ids currently mid-LLM-call this section
  const [thinkingReaders, setThinkingReaders] = useState(new Map()); // readerId -> {name, avatarIndex, personality, sectionNumber}

  const esRef = useRef(null);
  const lastEventTimeRef = useRef(Date.now());
  const [isStalled, setIsStalled] = useState(false);

  useEffect(() => {
    loadData();
    return () => { esRef.current?.close(); };
  }, [manuscriptId]);

  // Stall detection: if no SSE event arrives in 60s while reading, show banner
  useEffect(() => {
    if (readingDone) {
      setIsStalled(false);
      return;
    }
    const interval = setInterval(() => {
      const elapsed = Date.now() - lastEventTimeRef.current;
      if (elapsed > 60000) {
        setIsStalled(true);
      }
    }, 10000);
    return () => clearInterval(interval);
  }, [readingDone]);

  const loadData = async () => {
    try {
      const [mRes, pRes] = await Promise.all([
        axios.get(`${API}/manuscripts/${manuscriptId}`),
        axios.get(`${API}/manuscripts/${manuscriptId}/personas`),
      ]);
      setManuscript(mRes.data);
      setPersonas(pRes.data);
      setTotalSections(mRes.data.total_sections || 0);

      // Load existing reactions (for resumed sessions)
      const rRes = await axios.get(`${API}/manuscripts/${manuscriptId}/all-reactions`);
      const totalSecs = mRes.data.total_sections || 0;
      const existingReactions = rRes.data || [];
      const sectionsWithReactions = new Set(existingReactions.map((r) => r.section_number));
      const allDone = totalSecs > 0 && sectionsWithReactions.size >= totalSecs &&
        existingReactions.length >= totalSecs * pRes.data.length;

      if (existingReactions.length > 0) {
        loadExistingReactions(existingReactions, pRes.data);
      }

      if (allDone) {
        setReadingDone(true);
      } else {
        // Start (or resume) reading — backend will skip already-completed sections
        startReadingAll(mRes.data, pRes.data);
      }
    } catch (err) {
      toast.error("Failed to load manuscript");
    }
  };

  const loadExistingReactions = (reactionsData, personasData) => {
    const newCommentsByLine = {};
    const newAllComments = [];
    const newReflections = [];

    reactionsData.forEach((r) => {
      const { reader_id, reader_name, inline_comments = [], section_reflection, section_number } = r;
      inline_comments.forEach((comment) => {
        const line = comment.line;
        if (!newCommentsByLine[line]) newCommentsByLine[line] = [];
        newCommentsByLine[line].push({ readerId: reader_id, readerName: reader_name, comment });
        newAllComments.push({ readerId: reader_id, readerName: reader_name, comment });
      });
      if (section_reflection) {
        newReflections.push({ readerId: reader_id, section_number, reflection: section_reflection });
      }
    });

    setCommentsByLine(newCommentsByLine);
    setAllComments(newAllComments);
    setReflections(newReflections);

    // Set reader statuses as done
    const statusMap = {};
    personasData.forEach((p) => {
      const readerReactions = reactionsData.filter((r) => r.reader_id === p.id);
      const commentCount = readerReactions.reduce((sum, r) => sum + (r.inline_comments?.length || 0), 0);
      statusMap[p.id] = { currentSection: null, done: true, totalComments: commentCount };
    });
    setReaderStatus(statusMap);
  };

  const startReadingAll = useCallback((ms, ps) => {
    const url = `${process.env.REACT_APP_BACKEND_URL}/api/manuscripts/${ms.id}/read-all`;
    let cancelled = false;

    // Use fetch+ReadableStream instead of EventSource — EventSource auto-reconnects
    // which causes duplicate reads when there's a gap between sections
    const controller = new AbortController();
    esRef.current = { close: () => { cancelled = true; controller.abort(); } };

    const handleEvent = (data) => {
      // Reset stall timer on every event
      lastEventTimeRef.current = Date.now();
      setIsStalled(false);

      if (data.type === "start") {
        setTotalSections(data.total_sections);
        // Init reader statuses
        const statusMap = {};
        ps.forEach((p) => { statusMap[p.id] = { currentSection: null, done: false, totalComments: 0 }; });
        setReaderStatus(statusMap);

      } else if (data.type === "section_start") {
        setProcessingSection(data.section_number);
        // Update all readers to show this section
        setReaderStatus((prev) => {
          const next = { ...prev };
          ps.forEach((p) => {
            if (!next[p.id]?.done) {
              next[p.id] = { ...next[p.id], currentSection: data.section_number };
            }
          });
          return next;
        });

      } else if (data.type === "section_skipped") {
        // Section already read (reconnect scenario) — nothing to do, comments already loaded
      } else if (data.type === "reader_thinking") {
        const { reader_id, reader_name, avatar_index, personality, section_number } = data;
        setThinkingReaders((prev) => {
          const next = new Map(prev);
          next.set(reader_id, { reader_name, avatar_index, personality, section_number });
          return next;
        });

      } else if (data.type === "reader_complete") {
        const { reader_id, reader_name, inline_comments = [], section_reflection, section_number } = data;

        // Add comments to state
        setCommentsByLine((prev) => {
          const next = { ...prev };
          inline_comments.forEach((comment) => {
            const line = comment.line;
            if (!next[line]) next[line] = [];
            // Avoid duplicate
            const exists = next[line].some((c) => c.readerId === reader_id && c.comment.line === line && c.comment.type === comment.type);
            if (!exists) {
              next[line] = [...next[line], { readerId: reader_id, readerName: reader_name, comment }];
            }
          });
          return next;
        });

        setAllComments((prev) => {
          const newOnes = inline_comments.map((c) => ({ readerId: reader_id, readerName: reader_name, comment: c }));
          return [...prev, ...newOnes];
        });

        if (section_reflection) {
          setReflections((prev) => [...prev, { readerId: reader_id, section_number, reflection: section_reflection }]);
        }

        // Update reader status + clear thinking state
        setThinkingReaders((prev) => {
          const next = new Map(prev);
          next.delete(reader_id);
          return next;
        });
        setReaderStatus((prev) => {
          const cur = prev[reader_id] || {};
          return {
            ...prev,
            [reader_id]: {
              ...cur,
              totalComments: (cur.totalComments || 0) + inline_comments.length,
            },
          };
        });

      } else if (data.type === "reader_error") {
        // Clear from thinking strip
        if (data.reader_id) {
          setThinkingReaders((prev) => {
            const next = new Map(prev);
            next.delete(data.reader_id);
            return next;
          });
        }
        toast.error(`${data.reader_name || "A reader"} had an error on section ${data.section_number}`);

      } else if (data.type === "reader_warning") {
        toast.warning(`${data.reader_name || "A reader"}: ${data.message || "formatting issue, partial feedback saved"}`, { duration: 4000 });

      } else if (data.type === "reader_crashed") {
        if (data.reader_id) {
          setThinkingReaders((prev) => {
            const next = new Map(prev);
            next.delete(data.reader_id);
            return next;
          });
        }
        toast.error(`${data.reader_name || "A reader"} stopped reading unexpectedly.`);

      } else if (data.type === "reading_complete") {
        // Alias for all_complete (sent by newer backend versions)
        setReadingDone(true);
        setProcessingSection(null);
        setThinkingReaders(new Map());
        setReaderStatus((prev) => {
          const next = { ...prev };
          Object.keys(next).forEach((id) => { next[id] = { ...next[id], done: true, currentSection: null }; });
          return next;
        });
        toast.success("Your readers have finished. Generate your Editor Report?");
        return;

      } else if (data.type === "section_complete") {
        // nothing extra needed

      } else if (data.type === "all_complete") {
        setReadingDone(true);
        setProcessingSection(null);
        setThinkingReaders(new Map());
        setReaderStatus((prev) => {
          const next = { ...prev };
          Object.keys(next).forEach((id) => { next[id] = { ...next[id], done: true, currentSection: null }; });
          return next;
        });
        toast.success("Your readers have finished. Generate your Editor Report?");
        return; // stop processing
      }
    };

    // Stream via fetch — no auto-reconnect unlike EventSource
    (async () => {
      try {
        const resp = await fetch(url, { signal: controller.signal });
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (!cancelled) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop(); // keep incomplete last line
          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith("data:")) {
              try {
                const data = JSON.parse(trimmed.slice(5).trim());
                handleEvent(data);
              } catch (_) {}
            }
          }
        }
      } catch (err) {
        if (!cancelled) {
          console.error("SSE stream error:", err);
        }
      }
    })();
  }, []);

  const generateReport = async () => {
    setLoadingReport(true);
    try {
      await axios.post(`${API}/manuscripts/${manuscriptId}/editor-report`);
      navigate(`/report/${manuscriptId}`);
    } catch (err) {
      toast.error("Failed to generate report. Make sure readers have finished at least one section.");
    } finally {
      setLoadingReport(false);
    }
  };

  const handleRetry = useCallback(() => {
    setIsStalled(false);
    lastEventTimeRef.current = Date.now();
    // Close existing stream if any
    esRef.current?.close();
    if (manuscript && personas.length > 0) {
      startReadingAll(manuscript, personas);
    }
  }, [manuscript, personas, startReadingAll]);

  const handleViewPartial = useCallback(() => {
    setIsStalled(false);
    esRef.current?.close();
    setReadingDone(true);
    setProcessingSection(null);
    setThinkingReaders(new Map());
    toast.info("Showing partial results. You can still generate a report with what's been collected.");
  }, []);

  const handleOpenPopover = useCallback((lineNumber, e) => {
    setOpenPopoverLine((prev) => (prev === lineNumber ? null : lineNumber));
  }, []);

  // Click away to close popover
  useEffect(() => {
    const handler = () => setOpenPopoverLine(null);
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, []);

  const toggleType = (type) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  // Build flat list of all paragraph_lines across all sections
  const allParagraphLines = useMemo(() => {
    if (!manuscript?.sections) return [];
    return manuscript.sections
      .sort((a, b) => a.section_number - b.section_number)
      .flatMap((s) => s.paragraph_lines || []);
  }, [manuscript]);

  const progress = totalSections > 0 && processingSection
    ? ((processingSection - 1) / totalSections) * 100
    : readingDone ? 100 : 0;

  // Per-reader data for sidebar
  const readerReflections = useCallback(
    (readerId) => reflections.filter((r) => r.readerId === readerId),
    [reflections]
  );

  if (!manuscript) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-clay" strokeWidth={1.5} />
      </div>
    );
  }

  const totalCommentCount = allComments.length;

  return (
    <div className="h-screen bg-paper flex flex-col overflow-hidden" style={{ fontFamily: "'Manrope', sans-serif" }}>
      {/* Top bar */}
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
            {/* Reading status */}
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
          </div>
        </div>

        {/* Progress bar */}
        <div className="section-progress">
          <motion.div
            className="section-progress-fill"
            initial={false}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.6 }}
          />
        </div>
      </header>

      {/* Main split view */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Full manuscript (60%) */}
        <div
          className="w-3/5 border-r border-ink-900/8 overflow-y-auto paper-texture"
          data-testid="manuscript-panel"
          onClick={() => setOpenPopoverLine(null)}
        >
          <div className="max-w-2xl mx-auto px-8 py-12">
            {/* Title */}
            <div className="mb-10">
              <h1
                className="font-serif text-3xl text-ink-900 mb-2"
                style={{ fontFamily: "'Cormorant Garamond', serif" }}
              >
                {manuscript.title}
              </h1>
              <div className="flex items-center gap-3 text-xs text-ink-400">
                <span>{manuscript.genre}</span>
                <span>·</span>
                <span>{totalCommentCount} annotations</span>
              </div>
              <div className="w-16 h-px bg-clay mt-4" />
            </div>

            {/* Render all paragraphs across all sections */}
            {manuscript.sections?.sort((a, b) => a.section_number - b.section_number).map((section) => (
              <div key={section.section_number} className="mb-10">
                {/* Section title */}
                <h2
                  className="font-serif text-xl text-ink-900 mb-6 pt-4 border-t border-ink-900/8"
                  style={{ fontFamily: "'Cormorant Garamond', serif" }}
                >
                  {section.title}
                </h2>

                {/* Paragraphs */}
                {(section.paragraph_lines || []).map((lineData) => (
                  <AnnotatedParagraph
                    key={lineData.line}
                    lineData={lineData}
                    commentsByLine={commentsByLine}
                    personas={personas}
                    openPopoverLine={openPopoverLine}
                    onOpenPopover={handleOpenPopover}
                  />
                ))}
              </div>
            ))}

            {/* Done call-to-action */}
            {readingDone && (
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-8 p-6 border border-clay/20 bg-clay/5"
                style={{ borderRadius: "2px" }}
                data-testid="reading-complete-banner"
              >
                <h3
                  className="font-serif text-xl text-ink-900 mb-2"
                  style={{ fontFamily: "'Cormorant Garamond', serif" }}
                >
                  Your readers have finished.
                </h3>
                <p className="text-sm text-ink-600 mb-4">
                  {totalCommentCount} annotations across {totalSections} sections. Ready for the editorial synthesis?
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

        {/* Right: Reader sidebar (40%) */}
        <div
          className="w-2/5 overflow-y-auto bg-paper-dark flex flex-col"
          data-testid="reactions-sidebar"
        >
          <div className="p-5 flex-1">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs text-ink-400 uppercase tracking-widest">Your Readers</h3>
              {totalCommentCount > 0 && (
                <span className="text-xs text-ink-400">{totalCommentCount} annotations</span>
              )}
            </div>

            {/* Type filter chips */}
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
                    <button
                      onClick={() => setActiveTypes(new Set())}
                      className="text-xs px-2 py-1 text-ink-400 hover:text-clay transition-colors"
                    >
                      Clear
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Thinking strip — shows while readers are mid-LLM-call */}
            <AnimatePresence>
              {thinkingReaders.size > 0 && (
                <ThinkingStrip thinkingReaders={thinkingReaders} personas={personas} />
              )}
            </AnimatePresence>

            {/* Reader panels */}
            {personas.map((persona) => {
              const status = readerStatus[persona.id] || { currentSection: null, done: false, totalComments: 0 };
              const personaReflections = readerReflections(persona.id);
              const filteredCount = allComments.filter(
                (c) => c.readerId === persona.id && (activeTypes.size === 0 || activeTypes.has(c.comment.type))
              ).length;

              return (
                <ReaderPanel
                  key={persona.id}
                  persona={persona}
                  readerStatus={{ ...status, totalSections }}
                  reflections={personaReflections}
                  totalComments={status.totalComments || 0}
                  activeTypes={activeTypes}
                  allComments={allComments}
                />
              );
            })}

            {/* Empty state if no personas yet */}
            {personas.length === 0 && (
              <div className="text-center py-16">
                <MessageSquare className="w-6 h-6 text-ink-400 mx-auto mb-3" strokeWidth={1.5} />
                <p className="text-sm text-ink-400">Loading readers...</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
