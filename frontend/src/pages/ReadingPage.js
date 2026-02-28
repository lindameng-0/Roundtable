import React, { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { ChevronRight, ChevronLeft, ChevronDown, ChevronUp, FileText, BarChart2, Loader2 } from "lucide-react";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const READER_AVATAR_URLS = [
  "https://images.unsplash.com/photo-1581883556531-e5f8027f557f?crop=entropy&cs=srgb&fm=jpg&q=85&w=80",
  "https://images.unsplash.com/photo-1658909835269-e76abd3ffb5d?crop=entropy&cs=srgb&fm=jpg&q=85&w=80",
  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&q=80&w=80",
  "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&q=80&w=80",
  "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&q=80&w=80",
];

const PERSONALITY_COLORS = {
  analytical: "#5C5855",
  emotional: "#C86B56",
  casual: "#8da399",
  skeptical: "#D4Af37",
  genre_savvy: "#2D2A26",
};

function ReactionCard({ reaction, reader, isStreaming }) {
  const [expanded, setExpanded] = useState(false);
  const color = PERSONALITY_COLORS[reader?.personality] || "#5C5855";
  const avatarIdx = reader?.avatar_index ?? reaction?.avatar_index ?? 0;

  return (
    <motion.div
      initial={{ x: 40, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.4, ease: [0.32, 0.72, 0, 1] }}
      data-testid={`reaction-card-${reaction?.reader_name?.replace(/\s+/g, "-").toLowerCase()}`}
      className="bg-white border-l-4 shadow-sm mb-4 overflow-hidden"
      style={{ borderLeftColor: color, borderRadius: "2px" }}
    >
      <div className="p-4">
        {/* Header */}
        <div className="flex items-center gap-3 mb-3">
          <div className="w-8 h-8 overflow-hidden flex-shrink-0" style={{ borderRadius: "2px" }}>
            <img
              src={READER_AVATAR_URLS[avatarIdx % READER_AVATAR_URLS.length]}
              alt={reaction?.reader_name}
              className="w-full h-full object-cover"
              onError={(e) => { e.target.style.display = "none"; }}
            />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-ink-900 truncate">{reaction?.reader_name}</p>
            <p className="text-xs" style={{ color }}>
              {reader?.personality || "reader"}
            </p>
          </div>
          {isStreaming && (
            <Loader2 className="w-3.5 h-3.5 animate-spin text-ink-400 flex-shrink-0" strokeWidth={1.5} />
          )}
        </div>

        {/* Summary (always visible) */}
        <p className="text-sm text-ink-600 leading-relaxed">
          {reaction?.summary || reaction?.full_thoughts?.slice(0, 200)}
          {isStreaming && <span className="typing-cursor" />}
        </p>

        {/* Expand toggle */}
        {reaction?.full_thoughts && reaction.full_thoughts !== reaction?.summary && (
          <button
            data-testid={`expand-reaction-${reaction?.reader_name?.replace(/\s+/g, "-").toLowerCase()}`}
            onClick={() => setExpanded((e) => !e)}
            className="flex items-center gap-1 mt-2 text-xs text-ink-400 hover:text-clay transition-colors"
          >
            {expanded ? (
              <>
                <ChevronUp className="w-3 h-3" strokeWidth={1.5} /> Collapse
              </>
            ) : (
              <>
                <ChevronDown className="w-3 h-3" strokeWidth={1.5} /> Read full thoughts
              </>
            )}
          </button>
        )}
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-0 border-t border-ink-900/6">
              <p className="text-sm text-ink-600 leading-relaxed whitespace-pre-wrap mt-3">
                {reaction?.full_thoughts}
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function ReadingPage() {
  const { manuscriptId } = useParams();
  const navigate = useNavigate();
  const [manuscript, setManuscript] = useState(null);
  const [personas, setPersonas] = useState([]);
  const [currentSection, setCurrentSection] = useState(1);
  const [reactions, setReactions] = useState([]);
  const [streamingReaders, setStreamingReaders] = useState(new Set());
  const [isStreaming, setIsStreaming] = useState(false);
  const [hasRead, setHasRead] = useState(false);
  const [loadingReport, setLoadingReport] = useState(false);
  const sidebarRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    loadData();
    return () => abortRef.current?.abort();
  }, [manuscriptId]);

  const loadData = async () => {
    try {
      const [mRes, pRes] = await Promise.all([
        axios.get(`${API}/manuscripts/${manuscriptId}`),
        axios.get(`${API}/manuscripts/${manuscriptId}/personas`),
      ]);
      setManuscript(mRes.data);
      setPersonas(pRes.data);
    } catch (err) {
      toast.error("Failed to load manuscript");
    }
  };

  const loadExistingReactions = useCallback(async (sectionNum) => {
    try {
      const res = await axios.get(`${API}/manuscripts/${manuscriptId}/reactions/${sectionNum}`);
      if (res.data && res.data.length > 0) {
        setReactions(res.data);
        setHasRead(true);
        return true;
      }
    } catch {}
    return false;
  }, [manuscriptId]);

  useEffect(() => {
    setReactions([]);
    setHasRead(false);
    setStreamingReaders(new Set());
    loadExistingReactions(currentSection);
  }, [currentSection, loadExistingReactions]);

  const startReading = async () => {
    if (isStreaming) return;

    setIsStreaming(true);
    setReactions([]);
    setStreamingReaders(new Set());

    const url = `${process.env.REACT_APP_BACKEND_URL}/api/manuscripts/${manuscriptId}/read/${currentSection}`;
    const eventSource = new EventSource(url);
    abortRef.current = { abort: () => eventSource.close() };

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === "start") {
        // Initialize streaming state
      } else if (data.type === "reaction") {
        const reactionData = data.reaction;
        setReactions((prev) => {
          const exists = prev.find((r) => r.reader_id === reactionData.reader_id);
          if (exists) return prev;
          return [...prev, reactionData];
        });
        setStreamingReaders((prev) => {
          const next = new Set(prev);
          next.delete(data.reader_id);
          return next;
        });
        // Scroll sidebar to bottom
        setTimeout(() => {
          if (sidebarRef.current) {
            sidebarRef.current.scrollTop = sidebarRef.current.scrollHeight;
          }
        }, 100);
      } else if (data.type === "error") {
        toast.error(`${data.reader_name} had trouble reacting`);
      } else if (data.type === "complete") {
        setIsStreaming(false);
        setHasRead(true);
        eventSource.close();
      }
    };

    eventSource.onerror = () => {
      setIsStreaming(false);
      eventSource.close();
      if (!hasRead) toast.error("Connection error. Please try again.");
    };
  };

  const nextSection = () => {
    if (currentSection < (manuscript?.total_sections || 1)) {
      setCurrentSection((n) => n + 1);
    }
  };

  const prevSection = () => {
    if (currentSection > 1) {
      setCurrentSection((n) => n - 1);
    }
  };

  const generateReport = async () => {
    setLoadingReport(true);
    try {
      await axios.post(`${API}/manuscripts/${manuscriptId}/editor-report`);
      navigate(`/report/${manuscriptId}`);
    } catch (err) {
      toast.error("Failed to generate report. Make sure you've read at least one section.");
    } finally {
      setLoadingReport(false);
    }
  };

  const currentSectionData = manuscript?.sections?.find((s) => s.section_number === currentSection);
  const progress = manuscript ? (currentSection / manuscript.total_sections) * 100 : 0;

  const getPersonaForReaction = (reaction) => {
    return personas.find((p) => p.id === reaction.reader_id) || {
      personality: "reader",
      avatar_index: 0,
    };
  };

  if (!manuscript) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-6 h-6 animate-spin text-clay mx-auto mb-3" strokeWidth={1.5} />
          <p className="text-sm text-ink-400 font-sans">Loading manuscript...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-paper flex flex-col overflow-hidden" style={{ fontFamily: "'Manrope', sans-serif" }}>
      {/* Top bar */}
      <header className="border-b border-ink-900/8 bg-paper flex-shrink-0 z-10">
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
            <span className="text-xs text-ink-400 hidden sm:inline">{manuscript.genre}</span>
          </div>

          <div className="flex items-center gap-4">
            {/* Progress */}
            <div className="hidden sm:flex items-center gap-2 text-xs text-ink-400">
              <FileText className="w-3.5 h-3.5" strokeWidth={1.5} />
              Section {currentSection} of {manuscript.total_sections}
            </div>

            <button
              data-testid="generate-report-btn"
              onClick={generateReport}
              disabled={loadingReport}
              className="flex items-center gap-2 text-xs border border-ink-900/12 hover:border-clay text-ink-600 hover:text-clay px-3 py-2 transition-all"
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
            transition={{ duration: 0.5 }}
          />
        </div>
      </header>

      {/* Main split view */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Manuscript (60%) */}
        <div className="w-3/5 border-r border-ink-900/8 overflow-y-auto paper-texture" data-testid="manuscript-panel">
          <div className="max-w-2xl mx-auto px-16 py-12">
            {/* Section header */}
            <div className="mb-8">
              <p className="text-xs text-ink-400 uppercase tracking-widest mb-2">
                Section {currentSection} of {manuscript.total_sections}
              </p>
              <h2
                className="font-serif text-2xl text-ink-900 mb-1"
                style={{ fontFamily: "'Cormorant Garamond', serif" }}
              >
                {currentSectionData?.title || `Section ${currentSection}`}
              </h2>
              <div className="w-12 h-px bg-clay mt-3" />
            </div>

            {/* Manuscript text */}
            <div
              className="manuscript-text leading-loose"
              style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: "1.1rem", lineHeight: "1.9" }}
            >
              {currentSectionData?.text?.split("\n").map((para, i) =>
                para.trim() ? (
                  <p key={i} className="mb-5">
                    {para}
                  </p>
                ) : (
                  <br key={i} />
                )
              )}
            </div>

            {/* Navigation */}
            <div className="flex items-center justify-between mt-12 pt-8 border-t border-ink-900/8">
              <button
                data-testid="prev-section-btn"
                onClick={prevSection}
                disabled={currentSection === 1}
                className="flex items-center gap-2 text-sm text-ink-600 hover:text-ink-900 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-4 h-4" strokeWidth={1.5} />
                Previous
              </button>

              {!hasRead && !isStreaming ? (
                <button
                  data-testid="read-section-btn"
                  onClick={startReading}
                  className="flex items-center gap-2 bg-clay hover:bg-clay-hover text-white px-6 py-2.5 text-sm font-medium transition-all duration-200"
                  style={{ borderRadius: "2px" }}
                >
                  Send to readers
                  <ChevronRight className="w-4 h-4" strokeWidth={1.5} />
                </button>
              ) : isStreaming ? (
                <div className="flex items-center gap-2 text-sm text-ink-400">
                  <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.5} />
                  Readers reacting...
                </div>
              ) : (
                <button
                  data-testid="next-section-btn"
                  onClick={nextSection}
                  disabled={currentSection >= manuscript.total_sections}
                  className="flex items-center gap-2 bg-clay hover:bg-clay-hover text-white px-6 py-2.5 text-sm font-medium transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                  style={{ borderRadius: "2px" }}
                >
                  Next section
                  <ChevronRight className="w-4 h-4" strokeWidth={1.5} />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Right: Reactions sidebar (40%) */}
        <div
          ref={sidebarRef}
          className="w-2/5 overflow-y-auto bg-paper-dark"
          data-testid="reactions-sidebar"
        >
          <div className="p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xs text-ink-400 uppercase tracking-widest">
                Reader reactions
              </h3>
              {reactions.length > 0 && (
                <span className="text-xs text-ink-400">
                  {reactions.length} / {personas.length}
                </span>
              )}
            </div>

            {/* Streaming skeleton loaders */}
            {isStreaming && reactions.length < personas.length && (
              <div className="space-y-4 mb-4">
                {Array.from({ length: personas.length - reactions.length }).map((_, i) => (
                  <div
                    key={i}
                    className="bg-white border-l-4 border-l-ink-900/10 p-4 animate-pulse"
                    style={{ borderRadius: "2px" }}
                  >
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-8 h-8 bg-ink-900/8 rounded-sm" />
                      <div className="flex-1">
                        <div className="h-3 bg-ink-900/8 rounded w-24 mb-1.5" />
                        <div className="h-2 bg-ink-900/6 rounded w-16" />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div className="h-2.5 bg-ink-900/8 rounded w-full" />
                      <div className="h-2.5 bg-ink-900/8 rounded w-5/6" />
                      <div className="h-2.5 bg-ink-900/8 rounded w-4/6" />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Actual reactions */}
            {reactions.map((reaction) => (
              <ReactionCard
                key={reaction.id}
                reaction={reaction}
                reader={getPersonaForReaction(reaction)}
                isStreaming={streamingReaders.has(reaction.reader_id)}
              />
            ))}

            {/* Empty state */}
            {!isStreaming && reactions.length === 0 && (
              <div className="text-center py-16">
                <div className="w-12 h-12 border border-ink-900/12 flex items-center justify-center mx-auto mb-4" style={{ borderRadius: "2px" }}>
                  <FileText className="w-5 h-5 text-ink-400" strokeWidth={1.5} />
                </div>
                <p className="text-sm text-ink-400 mb-1">No reactions yet</p>
                <p className="text-xs text-ink-400/70">
                  Click "Send to readers" to get feedback
                </p>
              </div>
            )}

            {/* All read — suggest report */}
            {hasRead && reactions.length >= personas.length && currentSection >= manuscript.total_sections && (
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-6 p-4 bg-clay/5 border border-clay/20"
                style={{ borderRadius: "2px" }}
              >
                <p className="text-sm text-ink-900 font-medium mb-1">Manuscript complete</p>
                <p className="text-xs text-ink-600 mb-3">All sections have been read. Generate your editor report.</p>
                <button
                  data-testid="generate-report-sidebar-btn"
                  onClick={generateReport}
                  disabled={loadingReport}
                  className="w-full flex items-center justify-center gap-2 bg-clay hover:bg-clay-hover text-white px-4 py-2 text-sm font-medium transition-all"
                  style={{ borderRadius: "2px" }}
                >
                  {loadingReport ? (
                    <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.5} />
                  ) : (
                    <BarChart2 className="w-4 h-4" strokeWidth={1.5} />
                  )}
                  Generate Editor Report
                </button>
              </motion.div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
