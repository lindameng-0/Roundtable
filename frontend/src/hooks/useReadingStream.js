import { useState, useRef, useEffect, useCallback } from "react";
import { toast } from "sonner";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const READER_AVATAR_URLS = [
  "https://images.unsplash.com/photo-1581883556531-e5f8027f557f?crop=entropy&cs=srgb&fm=jpg&q=85&w=120",
  "https://images.unsplash.com/photo-1658909835269-e76abd3ffb5d?crop=entropy&cs=srgb&fm=jpg&q=85&w=120",
  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&q=80&w=120",
  "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&q=80&w=120",
  "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&q=80&w=120",
];

export { READER_AVATAR_URLS };

/**
 * Manages the SSE reading stream, all real-time state, and stall detection.
 * The page component owns manuscript/personas loading and report generation.
 */
export function useReadingStream(manuscriptId) {
  const [commentsByLine, setCommentsByLine] = useState({});
  const [readerStatus, setReaderStatus] = useState({});
  const [reflections, setReflections] = useState({});
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

  // Stall detection: if no SSE event arrives in 60s while reading, show banner
  useEffect(() => {
    if (readingDone) {
      setIsStalled(false);
      return;
    }
    const interval = setInterval(() => {
      if (Date.now() - lastEventTimeRef.current > 60000) {
        setIsStalled(true);
      }
    }, 10000);
    return () => clearInterval(interval);
  }, [readingDone]);

  const loadExistingReactions = useCallback((reactions, personasData) => {
    const byLine = {};
    const statusMap = {};
    const reflMap = {};
    const all = [];

    personasData.forEach((p) => {
      statusMap[p.id] = { done: true, currentSection: null, name: p.name, avatarIndex: p.avatar_index };
    });

    reactions.forEach((r) => {
      const persona = personasData.find((p) => p.id === r.reader_id);
      if (!persona) return;
      (r.inline_comments || []).forEach((c) => {
        if (!byLine[c.line]) byLine[c.line] = [];
        byLine[c.line].push({
          readerId: r.reader_id,
          readerName: r.reader_name || persona.name,
          avatarIndex: r.avatar_index ?? persona.avatar_index ?? 0,
          personality: r.personality || persona.personality,
          type: c.type,
          comment: c.comment,
          sectionNumber: r.section_number,
        });
        all.push({
          readerId: r.reader_id,
          readerName: r.reader_name || persona.name,
          avatarIndex: r.avatar_index ?? persona.avatar_index ?? 0,
          personality: r.personality || persona.personality,
          type: c.type,
          comment: c.comment,
          line: c.line,
          sectionNumber: r.section_number,
        });
      });
      if (r.section_reflection) {
        const key = `${r.reader_id}_${r.section_number}`;
        reflMap[key] = {
          text: r.section_reflection,
          readerName: r.reader_name || persona.name,
          avatarIndex: r.avatar_index ?? persona.avatar_index ?? 0,
        };
      }
    });

    setCommentsByLine(byLine);
    setReaderStatus(statusMap);
    setReflections(reflMap);
    setAllComments(all);
  }, []);

  const startReading = useCallback((ms, ps) => {
    if (readingStartedRef.current) {
      console.warn("startReading: already in progress, ignoring duplicate call");
      return;
    }
    readingStartedRef.current = true;

    const url = `${process.env.REACT_APP_BACKEND_URL}/api/manuscripts/${ms.id}/read-all`;
    let cancelled = false;
    const controller = new AbortController();
    esRef.current = { close: () => { cancelled = true; controller.abort(); } };

    const handleEvent = (data) => {
      lastEventTimeRef.current = Date.now();
      setIsStalled(false);

      if (data.type === "start") {
        setTotalSections(data.total_sections || 0);

      } else if (data.type === "section_start") {
        setProcessingSection(data.section_number);

      } else if (data.type === "section_skipped") {
        // already processed — do nothing, annotations were loaded by loadExistingReactions

      } else if (data.type === "reader_thinking") {
        setThinkingReaders((prev) => {
          const next = new Map(prev);
          next.set(data.reader_id, {
            name: data.reader_name,
            avatarIndex: data.avatar_index,
            personality: data.personality,
            section: data.section_number,
          });
          return next;
        });
        setReaderStatus((prev) => ({
          ...prev,
          [data.reader_id]: {
            ...prev[data.reader_id],
            name: data.reader_name,
            avatarIndex: data.avatar_index,
            personality: data.personality,
            done: false,
            currentSection: data.section_number,
          },
        }));

      } else if (data.type === "reader_complete") {
        setThinkingReaders((prev) => {
          const next = new Map(prev);
          next.delete(data.reader_id);
          return next;
        });
        setReaderStatus((prev) => ({
          ...prev,
          [data.reader_id]: {
            ...prev[data.reader_id],
            name: data.reader_name,
            avatarIndex: data.avatar_index ?? 0,
            personality: data.personality,
            done: false,
            currentSection: data.section_number,
          },
        }));

        const newComments = data.inline_comments || [];
        setCommentsByLine((prev) => {
          const next = { ...prev };
          newComments.forEach((c) => {
            if (!next[c.line]) next[c.line] = [];
            next[c.line] = [
              ...next[c.line].filter((x) => x.readerId !== data.reader_id || x.type !== c.type || x.comment !== c.comment),
              {
                readerId: data.reader_id,
                readerName: data.reader_name,
                avatarIndex: data.avatar_index ?? 0,
                personality: data.personality,
                type: c.type,
                comment: c.comment,
                sectionNumber: data.section_number,
              },
            ];
          });
          return next;
        });
        setAllComments((prev) => [
          ...prev,
          ...newComments.map((c) => ({
            readerId: data.reader_id,
            readerName: data.reader_name,
            avatarIndex: data.avatar_index ?? 0,
            personality: data.personality,
            type: c.type,
            comment: c.comment,
            line: c.line,
            sectionNumber: data.section_number,
          })),
        ]);
        if (data.section_reflection) {
          setReflections((prev) => ({
            ...prev,
            [`${data.reader_id}_${data.section_number}`]: {
              text: data.section_reflection,
              readerName: data.reader_name,
              avatarIndex: data.avatar_index ?? 0,
            },
          }));
        }

      } else if (data.type === "section_complete") {
        setProcessingSection(null);

      } else if (data.type === "all_complete") {
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

      } else if (data.type === "reading_complete") {
        // Forward-compat alias for all_complete
        readingStartedRef.current = false;
        setReadingDone(true);
        setProcessingSection(null);
        setThinkingReaders(new Map());
        toast.success("Your readers have finished. Generate your Editor Report?");
      }
    };

    (async () => {
      try {
        const res = await fetch(url, { signal: controller.signal });
        if (!res.ok || !res.body) return;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!cancelled) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                handleEvent(JSON.parse(line.slice(6)));
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

  const handleRetry = useCallback((ms, ps) => {
    setIsStalled(false);
    lastEventTimeRef.current = Date.now();
    readingStartedRef.current = false;
    esRef.current?.close();
    if (ms && ps) startReading(ms, ps);
  }, [startReading]);

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
    startReading,
    loadExistingReactions,
    handleRetry,
    handleViewPartial,
  };
}
