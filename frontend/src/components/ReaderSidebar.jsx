import ReaderAvatar from "./ReaderAvatar";
import { readerPalette, readerColorStyle } from "../readerPalette";
import React, { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronRight, Loader2, HelpCircle, CheckCircle } from "lucide-react";
import { StallBanner } from "./StallBanner";




// New comment type set
const COMMENT_TYPE_COLORS = Object.fromEntries(
  ["reaction", "confusion", "question", "craft", "callback", "prediction", "critique", "praise", "theory", "comparison"].map(type => [type, { bg: "var(--theme-wash)", text: "var(--theme)", label: type.charAt(0).toUpperCase() + type.slice(1) }])
);

// New types only (for filter bar)
const CURRENT_TYPES = ["reaction", "confusion", "question", "craft", "callback"];

function getReaderDisplayName(persona, index) {
  const n = persona?.name;
  if (n != null && String(n).trim()) return String(n).trim();
  return `Reader ${(index ?? persona?.avatar_index ?? 0) + 1}`;
}

function NavigableText({ text, onNavigate }) {
  return String(text || "").split(/(p-\d{6})/gi).map((part, index) => /^p-\d{6}$/i.test(part) ? (
    <button key={index} onClick={(event) => { event.stopPropagation(); onNavigate?.(part.toLowerCase()); }} className="text-clay hover:underline font-medium">{part}</button>
  ) : <React.Fragment key={index}>{part}</React.Fragment>);
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
          const readerColor = readerPalette(info.avatar_index).color;
          const displayName = (info.reader_name && String(info.reader_name).trim()) || `Reader ${(info.avatar_index ?? 0) + 1}`;
          return (
            <div key={readerId} className="flex items-center gap-2.5 px-3 py-2.5">
              <div className="w-6 h-6 overflow-hidden flex-shrink-0" style={{ borderRadius: "2px", border: `1.5px solid ${readerColor}` }}>
                <ReaderAvatar name={displayName} index={info.avatar_index} />
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-xs font-semibold" style={{ color: readerPalette(info.avatar_index).ink || readerColor }}>{displayName}</span>
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
function SectionJournalEntry({ entry, onNavigate }) {
  const [showCheckingIn, setShowCheckingIn] = useState(false);
  const { section_number, reading_journal, what_i_think_the_writer_is_doing, questions_for_writer, checking_in } = entry;

  return (
    <div className="pt-3 pb-4 border-b border-ink-900/5 last:border-0">
      <button onClick={() => onNavigate?.(`section-${section_number}`)} className="text-xs text-ink-400 hover:text-clay uppercase tracking-widest mb-2 transition-colors">Section {section_number}</button>

      {/* Primary: Reading Journal */}
      {reading_journal && (
        <p
          className="reader-journal-text text-sm text-ink-700 leading-relaxed mb-3"
          style={{
            fontFamily: "var(--reading-font)",
            fontSize: "1rem",
            lineHeight: "1.75",
            fontStyle: "normal",
          }}
        >
          <NavigableText text={reading_journal} onNavigate={onNavigate} />
        </p>
      )}

      {/* Secondary: What the writer is doing */}
      {what_i_think_the_writer_is_doing && (
        <div className="mb-3">
          <p className="text-xs text-ink-400 uppercase tracking-widest mb-1">Intent read</p>
          <p className="text-xs text-ink-600 leading-relaxed">
            <NavigableText text={what_i_think_the_writer_is_doing} onNavigate={onNavigate} />
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
                borderLeft: "2px solid #493449",
                borderRadius: "0 2px 2px 0",
                fontFamily: "var(--reading-font)",
                fontSize: "0.9rem",
                fontStyle: "normal",
              }}
            >
              <HelpCircle className="w-3 h-3 flex-shrink-0 mt-0.5 text-clay" strokeWidth={1.5} />
              <span><NavigableText text={q} onNavigate={onNavigate} /></span>
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

function ReaderPanel({ persona, readerStatus, reflections, totalComments, onNavigate, defaultExpanded = false }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const readerColor = readerPalette(persona?.avatar_index).color;
  const { currentSection, done } = readerStatus || {};

  // Sections with journals, sorted
  const sortedSections = useMemo(() => {
    return [...reflections].sort((a, b) => (a.section_number || 0) - (b.section_number || 0));
  }, [reflections]);

  const journalCount = sortedSections.length;
  const hasContent = journalCount > 0;

  return (
    <div
      data-testid={`reader-panel-${getReaderDisplayName(persona).replace(/\s+/g, "-").toLowerCase()}`}
      className="reader-notebook"
      style={readerColorStyle(persona.avatar_index)}
    >
      <button
        className="w-full flex items-center gap-3 p-4 text-left hover:bg-paper transition-colors"
        aria-expanded={expanded}
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="note-portrait" style={{ borderRadius: "2px", border: `2px solid ${readerColor}` }}>
          <ReaderAvatar name={getReaderDisplayName(persona)} index={persona.avatar_index} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-ink-900 truncate">{getReaderDisplayName(persona)}</p>
          <p className="text-xs" style={{ color: "var(--muted-ink)" }}>
            {done
              ? `${journalCount} journal${journalCount !== 1 ? "s" : ""} · ${totalComments} comment${totalComments !== 1 ? "s" : ""}`
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
          <motion.div initial={defaultExpanded ? false : { height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} transition={{ duration: 0.22 }} className="overflow-hidden">
            <div className="px-4 pb-4 border-t border-ink-900/6">
              {/* Section journals */}
              {sortedSections.length > 0 && (
                <div className="mt-3 space-y-0">
                  {sortedSections.map((entry, i) => (
                    <SectionJournalEntry key={`${entry.readerId}-${entry.section_number}-${i}`} entry={entry} onNavigate={onNavigate} />
                  ))}
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
function buildQuestionLedger(reflections, personas) {
  const ledger = new Map();
  [...reflections].sort((a, b) => (a.section_number || 0) - (b.section_number || 0)).forEach((entry) => {
    const persona = personas.find((item) => item.id === entry.readerId);
    const readerName = getReaderDisplayName(persona, persona?.avatar_index);
    const events = entry.question_events?.length ? entry.question_events : (entry.questions_for_writer || []).map((question, index) => ({
      question_id: `legacy-${entry.readerId}-${entry.section_number}-${index}`, question,
      kind: "story_question", raised_section: entry.section_number,
    }));
    events.forEach((event) => {
      if (!event.question_id || !event.question || ledger.has(event.question_id)) return;
      ledger.set(event.question_id, { ...event, readerId: entry.readerId, readerName, status: "open", raised_section: event.raised_section || entry.section_number });
    });
    (entry.question_updates || []).forEach((update) => {
      const question = ledger.get(update.question_id);
      if (!question) return;
      ledger.set(update.question_id, { ...question, status: update.status, resolution: update.resolution, resolved_section: update.status === "resolved" ? entry.section_number : null, paragraph_id: update.paragraph_id });
    });
  });
  return [...ledger.values()];
}

function QuestionItem({ item, manuscriptId, onNavigate }) {
  const [showResolution, setShowResolution] = useState(false);
  const resolved = item.status === "resolved";
  const statusLabel = { open: "Open", partially_resolved: "Partly understood", resolved: `Resolved in §${item.resolved_section}`, reinterpreted: "Interpretation changed" }[item.status] || item.status;
  return <div className={`pt-3 ${resolved ? "opacity-60" : ""}`}>
    <button className="w-full text-left" onClick={() => item.resolution && setShowResolution((value) => !value)}>
      <div className="flex gap-2 items-start">
        {resolved ? <CheckCircle className="w-3.5 h-3.5 text-sage mt-0.5 flex-shrink-0" /> : <HelpCircle className="w-3.5 h-3.5 text-clay mt-0.5 flex-shrink-0" />}
        <div className="flex-1">
          <p className={`text-sm text-ink-700 leading-relaxed ${resolved ? "line-through decoration-ink-400/40" : ""}`} style={{ fontFamily: "var(--reading-font)", fontStyle: "italic" }}>{item.question}</p>
          <div className="flex flex-wrap gap-2 mt-1 text-xs text-ink-400"><span>{item.readerName} · raised §{item.raised_section}</span><span className={resolved ? "text-sage" : item.status === "open" ? "text-clay" : "text-amber-700"}>{statusLabel}</span></div>
        </div>
        {item.resolution && <ChevronRight className={`w-3 h-3 text-ink-400 transition-transform ${showResolution ? "rotate-90" : ""}`} />}
      </div>
    </button>
    <AnimatePresence>{showResolution && item.resolution && <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden ml-5 mt-2 pl-3 border-l border-sage/30">
      <p className="text-xs uppercase tracking-widest text-ink-400 mb-1">What I understand now</p><p className="text-xs text-ink-600 leading-relaxed">{item.resolution}</p>
      {item.paragraph_id && <button onClick={() => onNavigate?.(item.paragraph_id)} className="block text-xs text-clay mt-2 hover:underline">Show resolving passage</button>}
    </motion.div>}</AnimatePresence>
  </div>;
}

export function ReaderSidebar({ manuscriptId, onNavigate, personas, readerStatus, reflections, allComments, thinkingReaders, totalCommentCount, activeTypes, toggleType, setActiveTypes, isStalled, readingDone, onRetry, onViewPartial }) {
  const [view, setView] = useState("reflections");
  const questions = useMemo(() => buildQuestionLedger(reflections, personas), [reflections, personas]);
  const visibleNotes = useMemo(() => allComments.filter(entry => activeTypes.size === 0 || activeTypes.has(entry.comment?.type)).sort((a,b) => (a.comment?.line || 0) - (b.comment?.line || 0)), [allComments, activeTypes]);
  return <div className="notebook-content" data-testid="reactions-sidebar">
    <div className="notebook-views" role="group" aria-label="Notebook view">
      <button aria-pressed={view === "reflections"} onClick={() => setView("reflections")}>Reflections</button>
      <button aria-pressed={view === "notes"} onClick={() => setView("notes")}>Passage notes <span>{totalCommentCount}</span></button>
      <button aria-pressed={view === "questions"} onClick={() => setView("questions")}>Questions <span>{questions.length}</span></button>
    </div>
    {isStalled && !readingDone && <StallBanner onRetry={onRetry} onViewPartial={onViewPartial} />}
    {thinkingReaders.size > 0 && <ThinkingStrip thinkingReaders={thinkingReaders} personas={personas} />}
    {view === "reflections" && <div className="notebook-reflections">
      <p className="notebook-guidance">Follow how each reader's impressions changed as they read.</p>
      {personas.map((persona, index) => {
        const status = readerStatus[persona.id] || {};
        return <ReaderPanel key={persona.id} persona={persona} readerStatus={status} reflections={reflections.filter(entry => entry.readerId === persona.id)} totalComments={status.totalComments || 0} onNavigate={onNavigate} defaultExpanded={index === 0} />;
      })}
      {personas.length === 0 && <p className="notebook-empty">Your readers will appear here when they are ready.</p>}
    </div>}
    {view === "notes" && <div className="notebook-passages">
      <div className="notebook-filters" role="group" aria-label="Filter passage notes">
        <button aria-pressed={activeTypes.size === 0} onClick={() => setActiveTypes(new Set())}>All notes</button>
        {CURRENT_TYPES.map(type => <button key={type} data-testid={`filter-type-${type}`} aria-pressed={activeTypes.has(type)} onClick={() => toggleType(type)}>{COMMENT_TYPE_COLORS[type].label}</button>)}
      </div>
      {visibleNotes.map((entry, index) => {
        const persona = personas.find(reader => reader.id === entry.readerId);
        return <button key={`${entry.readerId}-${index}`} className="notebook-passage" style={readerColorStyle(persona?.avatar_index)} onClick={() => onNavigate(entry.comment?.paragraph_id || `p-${String(entry.comment?.line || 0).padStart(6,"0")}`, entry.comment?.line)}>
          <span className="notebook-passage-author"><span className="passage-note-avatar"><ReaderAvatar name={entry.readerName} index={persona?.avatar_index} /></span><span>{entry.readerName}</span><small>Paragraph {entry.comment?.line}</small></span>
          <span className="notebook-passage-text">{entry.comment?.comment}</span><span className="notebook-passage-link">Read beside the passage <ChevronRight size={13} /></span>
        </button>;
      })}
      {visibleNotes.length === 0 && <p className="notebook-empty">{activeTypes.size > 0 ? "No notes match this filter. Choose All notes to see the rest." : readingDone ? "Your readers left no passage notes. Explore their reflections instead." : "Passage notes will appear here as your readers continue."}</p>}
    </div>}
    {view === "questions" && <div className="notebook-questions">
      <p className="notebook-guidance">Questions your readers raised, and what became clearer later.</p>
      {questions.map(question => <QuestionItem key={question.question_id} item={question} manuscriptId={manuscriptId} onNavigate={onNavigate} />)}
      {questions.length === 0 && <p className="notebook-empty">{readingDone ? "Your readers left no questions." : "Your readers' questions will appear here as they read."}</p>}
    </div>}
  </div>;
}
