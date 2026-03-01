import { useState, useRef, useEffect, useCallback } from "react";
import { toast } from "sonner";

const API_BASE = (process.env.REACT_APP_BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

/**
 * Manages the SSE reading stream, all real-time state, and stall detection.
 * State formats are preserved exactly from the original ReadingPage to avoid
 * breaking component consumers.
 *
 * commentsByLine: { [line]: [{readerId, readerName, comment: {line, type, comment}}] }
 * allComments:   [{readerId, readerName, comment: {line, type, comment}}]
 * reflections:   [{readerId, section_number, reflection}]
 * readerStatus:  { [readerId]: {currentSection, done, totalComments} }
 * thinkingReaders: Map<readerId, {reader_name, avatar_index, personality, section_number}>
 */
export function useReadingStream(manuscriptId) {
  const [commentsByLine, setCommentsByLine] = useState({});
  const [readerStatus, setReaderStatus] = useState({});
  const [reflections, setReflections] = useState([]);
  const [allComments, setAllComments] = useState([]);
  const [thinkingReaders, setThinkingReaders] = useState(new Map());
  const [readingDone, setReadingDone] = useState(false);
  const [processingSection, setProcessingSection] = useState(null);
  const [totalSections, setTotalSections] = useState(0);
  const [isStalled, setIsStalled] = useState(false);

  const esRef = useRef(null);
  const lastEventTimeRef = useRef(Date.now());
  // Prevents React StrictMode double-mount from opening two concurrent SSE connections.
  const readingStartedRef = useRef(false);

  // Stall detection: if no SSE event arrives in 120s while reading, show banner
  useEffect(() => {
    if (readingDone) {
      setIsStalled(false);
      return;
    }
    const interval = setInterval(() => {
      if (Date.now() - lastEventTimeRef.current > 120000) {
        setIsStalled(true);
      }
    }, 10000);
    return () => clearInterval(interval);
  }, [readingDone]);

  /** Load reactions that already exist in the DB (for resumed sessions). */
  const loadExistingReactions = useCallback((reactionsData, personasData) => {
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

    const statusMap = {};
    personasData.forEach((p) => {
      const readerReactions = reactionsData.filter((r) => r.reader_id === p.id);
      const commentCount = readerReactions.reduce((sum, r) => sum + (r.inline_comments?.length || 0), 0);
      statusMap[p.id] = { currentSection: null, done: true, totalComments: commentCount };
    });
    setReaderStatus(statusMap);
  }, []);

  /** Open the SSE read-all stream. Guard ensures only one stream at a time. */
  const startReadingAll = useCallback((ms, ps, reconnectAttempt = 0) => {
    if (readingStartedRef.current) {
      console.warn("startReadingAll: already in progress, ignoring duplicate call");
      return;
    }
    readingStartedRef.current = true;

    const url = `${API_BASE}/api/manuscripts/${ms.id}/read-all`;
    let cancelled = false;
    let completedNormally = false; // set true when all_complete arrives
    const controller = new AbortController();
    esRef.current = { close: () => { cancelled = true; controller.abort(); } };

    const handleEvent = (data) => {
      lastEventTimeRef.current = Date.now();
      setIsStalled(false);

      if (data.type === "start") {
        setTotalSections(data.total_sections);
        const statusMap = {};
        ps.forEach((p) => { statusMap[p.id] = { currentSection: null, done: false, totalComments: 0 }; });
        setReaderStatus(statusMap);

      } else if (data.type === "section_start") {
        setProcessingSection(data.section_number);
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
        // already processed — nothing to do

      } else if (data.type === "reader_thinking") {
        const { reader_id, reader_name, avatar_index, personality, section_number } = data;
        setThinkingReaders((prev) => {
          const next = new Map(prev);
          next.set(reader_id, { reader_name, avatar_index, personality, section_number });
          return next;
        });

      } else if (data.type === "reader_complete") {
        const { reader_id, reader_name, inline_comments = [], section_reflection, section_number } = data;

        setCommentsByLine((prev) => {
          const next = { ...prev };
          inline_comments.forEach((comment) => {
            const line = comment.line;
            if (!next[line]) next[line] = [];
            const exists = next[line].some(
              (c) => c.readerId === reader_id && c.comment.line === line && c.comment.type === comment.type
            );
            if (!exists) {
              next[line] = [...next[line], { readerId: reader_id, readerName: reader_name, comment }];
            }
          });
          return next;
        });

        setAllComments((prev) => [
          ...prev,
          ...inline_comments.map((c) => ({ readerId: reader_id, readerName: reader_name, comment: c })),
        ]);

        if (section_reflection) {
          setReflections((prev) => [...prev, { readerId: reader_id, section_number, reflection: section_reflection }]);
        }

        setThinkingReaders((prev) => { const next = new Map(prev); next.delete(reader_id); return next; });
        setReaderStatus((prev) => {
          const cur = prev[reader_id] || {};
          return { ...prev, [reader_id]: { ...cur, totalComments: (cur.totalComments || 0) + inline_comments.length } };
        });

      } else if (data.type === "section_complete") {
        // nothing extra needed

      } else if (data.type === "all_complete" || data.type === "reading_complete") {
        completedNormally = true;
        readingStartedRef.current = false;
        setReadingDone(true);
        setProcessingSection(null);
        setThinkingReaders(new Map());
        setReaderStatus((prev) => {
          const next = { ...prev };
          Object.keys(next).forEach((id) => { next[id] = { ...next[id], done: true, currentSection: null }; });
          return next;
        });
        toast.success("Your readers have finished. Generate your Editor Report?");

      } else if (data.type === "reader_error") {
        if (data.reader_id) {
          setThinkingReaders((prev) => { const next = new Map(prev); next.delete(data.reader_id); return next; });
        }
        toast.error(`${data.reader_name || "A reader"} had an error on section ${data.section_number}`);

      } else if (data.type === "reader_warning") {
        toast.warning(`${data.reader_name || "A reader"}: ${data.message || "formatting issue, partial feedback saved"}`, { duration: 4000 });

      } else if (data.type === "reader_crashed") {
        if (data.reader_id) {
          setThinkingReaders((prev) => { const next = new Map(prev); next.delete(data.reader_id); return next; });
        }
        toast.error(`${data.reader_name || "A reader"} stopped reading unexpectedly.`);
      }
    };

    (async () => {
      try {
        const resp = await fetch(url, { signal: controller.signal });
        if (!resp.ok || !resp.body) return;
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!cancelled) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith("data:")) {
              try { handleEvent(JSON.parse(trimmed.slice(5).trim())); } catch (_) {}
            }
          }
        }
      } catch (err) {
        if (!cancelled) console.error("SSE stream error:", err);
      } finally {
        // Auto-reconnect if the stream dropped before reading was complete
        if (!cancelled && !completedNormally && reconnectAttempt < 5) {
          console.warn(`SSE stream dropped (attempt ${reconnectAttempt + 1}), reconnecting in ${(reconnectAttempt + 1) * 1500}ms...`);
          readingStartedRef.current = false;
          setTimeout(() => {
            if (!cancelled) startReadingAll(ms, ps, reconnectAttempt + 1);
          }, (reconnectAttempt + 1) * 1500);
        }
      }
    })();
  }, []);

  const handleRetry = useCallback((manuscript, personas) => {
    setIsStalled(false);
    lastEventTimeRef.current = Date.now();
    readingStartedRef.current = false;
    esRef.current?.close();
    if (manuscript && personas?.length > 0) startReadingAll(manuscript, personas);
  }, [startReadingAll]);

  const handleViewPartial = useCallback(() => {
    setIsStalled(false);
    esRef.current?.close();
    readingStartedRef.current = false;
    setReadingDone(true);
    setProcessingSection(null);
    setThinkingReaders(new Map());
    toast.info("Showing partial results. You can still generate a report with what's been collected.");
  }, []);

  return {
    commentsByLine,
    readerStatus,
    reflections,
    allComments,
    thinkingReaders,
    readingDone,
    setReadingDone,
    processingSection,
    totalSections,
    isStalled,
    esRef,
    startReadingAll,
    loadExistingReactions,
    setTotalSections,
    handleRetry,
    handleViewPartial,
  };
}
