import { useState, useRef, useEffect, useCallback } from "react";
import { toast } from "sonner";

import { getApiBase } from "../apiConfig";
import { getManuscriptHeaders } from "../manuscriptAccess";

/**
 * Manages the SSE reading stream, all real-time state, and stall detection.
 *
 * New schema from backend reader_complete events:
 *   checking_in, reading_journal, what_i_think_the_writer_is_doing,
 *   moments [{paragraph, type, comment}], questions_for_writer [string]
 *
 * commentsByLine: { [line]: [{readerId, readerName, comment: {line, type, comment}}] }
 * allComments:   [{readerId, readerName, comment: {line, type, comment}}]
 * reflections:   [{readerId, section_number, reading_journal, what_i_think_the_writer_is_doing, questions_for_writer, checking_in}]
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
  const [workflowProgress, setWorkflowProgress] = useState({ completed: 0, total: 0, failed: 0 });
  const [workflowUsage, setWorkflowUsage] = useState(null);
  const [workflowModels, setWorkflowModels] = useState([]);
  const [workflowBudget, setWorkflowBudget] = useState(null);

  const esRef = useRef(null);
  const lastEventTimeRef = useRef(Date.now());
  // Prevents React StrictMode double-mount from opening two concurrent SSE connections.
  const readingStartedRef = useRef(false);
  const completedTaskKeysRef = useRef(new Set());

  const addUsage = (current, usage) => {
    if (!usage || typeof usage !== "object") return current;
    const base = current || { calls: 0, input_tokens: 0, output_tokens: 0, estimated_cost_usd: 0, has_unknown_cost: false, by_role: {} };
    const role = usage.role || "reader";
    const costKnown = usage.estimated_cost_usd !== null && usage.estimated_cost_usd !== undefined;
    const roleBase = base.by_role?.[role] || { calls: 0, input_tokens: 0, output_tokens: 0, estimated_cost_usd: 0 };
    return {
      ...base,
      calls: (base.calls || 0) + 1,
      input_tokens: (base.input_tokens || 0) + (usage.input_tokens || 0),
      output_tokens: (base.output_tokens || 0) + (usage.output_tokens || 0),
      estimated_cost_usd: Number(((base.estimated_cost_usd || 0) + (costKnown ? usage.estimated_cost_usd : 0)).toFixed(6)),
      has_unknown_cost: Boolean(base.has_unknown_cost || !costKnown),
      by_role: { ...base.by_role, [role]: {
        calls: (roleBase.calls || 0) + 1,
        input_tokens: (roleBase.input_tokens || 0) + (usage.input_tokens || 0),
        output_tokens: (roleBase.output_tokens || 0) + (usage.output_tokens || 0),
        estimated_cost_usd: Number(((roleBase.estimated_cost_usd || 0) + (costKnown ? usage.estimated_cost_usd : 0)).toFixed(6)),
      } },
    };
  };

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

  /** Helper: convert a moments array [{paragraph,type,comment}] to comment format [{line,type,comment}]. */
  const _momentsToComments = (moments) =>
    (moments || []).map((m) => ({
      line: m.paragraph ?? m.line,
      paragraph_id: m.paragraph_id || null,
      type: m.type,
      comment: m.comment,
    }));

  const _commentKey = (readerId, comment) =>
    `${readerId}|${comment.paragraph_id || comment.line || ""}|${comment.type || "reaction"}|${String(comment.comment || "").trim()}`;

  const _reflectionKey = (reflection) =>
    `${reflection.readerId}|${reflection.section_number}`;

  /** Load reactions that already exist in the DB (for resumed sessions). */
  const loadExistingReactions = useCallback((reactionsData, personasData) => {
    const newCommentsByLine = {};
    const newAllComments = [];
    const newReflections = [];

    const seenReactions = new Set();
    const seenComments = new Set();
    reactionsData.forEach((r) => {
      const { reader_id, reader_name, section_number } = r;
      const reactionKey = `${reader_id}|${section_number}`;
      if (seenReactions.has(reactionKey)) return;
      seenReactions.add(reactionKey);
      completedTaskKeysRef.current.add(reactionKey);
      const rj = r.response_json || {};

      // Prefer new moments from response_json, fall back to legacy inline_comments
      const rawMoments = (rj.moments || []).length > 0 ? rj.moments : [];
      const legacyComments = r.inline_comments || [];

      const commentsSource =
        rawMoments.length > 0
          ? _momentsToComments(rawMoments)
          : legacyComments.map((c) => ({ line: c.line, paragraph_id: c.paragraph_id || null, type: c.type, comment: c.comment }));

      commentsSource.forEach((comment) => {
        const commentKey = _commentKey(reader_id, comment);
        if (seenComments.has(commentKey)) return;
        seenComments.add(commentKey);
        const line = comment.line;
        if (!newCommentsByLine[line]) newCommentsByLine[line] = [];
        newCommentsByLine[line].push({ readerId: reader_id, readerName: reader_name, comment });
        newAllComments.push({ readerId: reader_id, readerName: reader_name, comment });
      });

      // New reflection shape — pull from response_json first, fall back to top-level fields
      const reading_journal = rj.reading_journal || r.section_reflection || null;
      const what_i_think_the_writer_is_doing = rj.what_i_think_the_writer_is_doing || null;
      const questions_for_writer = Array.isArray(rj.questions_for_writer) ? rj.questions_for_writer : [];
      const checking_in = rj.checking_in || null;

      if (reading_journal || what_i_think_the_writer_is_doing || questions_for_writer.length > 0) {
        newReflections.push({
          readerId: reader_id,
          section_number,
          reading_journal,
          what_i_think_the_writer_is_doing,
          questions_for_writer,
          question_events: Array.isArray(rj.question_events) ? rj.question_events : [],
          question_updates: Array.isArray(rj.question_updates) ? rj.question_updates : [],
          checking_in,
        });
      }
    });

    setCommentsByLine(newCommentsByLine);
    setAllComments(newAllComments);
    setReflections(newReflections);

    const statusMap = {};
    personasData.forEach((p) => {
      const readerReactions = reactionsData.filter((r) => r.reader_id === p.id);
      const commentCount = readerReactions.reduce((sum, r) => {
        const rj = r.response_json || {};
        const moments = (rj.moments || []).length > 0 ? rj.moments : r.inline_comments || [];
        return sum + moments.length;
      }, 0);
      statusMap[p.id] = { currentSection: null, done: true, totalComments: commentCount };
    });
    setReaderStatus(statusMap);
    setWorkflowProgress({ completed: seenReactions.size, total: personasData.length * Math.max(0, ...reactionsData.map((r) => r.section_number || 0)), failed: 0 });
  }, []);

  /** Open the SSE read-all stream. Guard ensures only one stream at a time. */
  const startReadingAll = useCallback((ms, ps, reconnectAttempt = 0) => {
    if (readingStartedRef.current) {
      console.warn("startReadingAll: already in progress, ignoring duplicate call");
      return;
    }
    readingStartedRef.current = true;

    const url = ps.length > 0
      ? `${getApiBase()}/api/manuscripts/${ms.id}/read-all?reader_ids=${ps.map((p) => p.id).join(",")}`
      : `${getApiBase()}/api/manuscripts/${ms.id}/read-all`;
    let cancelled = false;
    let completedNormally = false; // set true when all_complete arrives
    const controller = new AbortController();
    esRef.current = { close: () => { cancelled = true; controller.abort(); } };

    const handleEvent = (data) => {
      lastEventTimeRef.current = Date.now();
      setIsStalled(false);

      if (data.type === "start") {
        setTotalSections(data.total_sections);
        setWorkflowProgress({ completed: data.completed_tasks || 0, total: data.total_tasks || (data.total_sections * data.total_readers), failed: 0 });
        setWorkflowUsage(data.usage || null);
        setWorkflowBudget(data.budget || null);
        setWorkflowModels(data.reader_models || []);
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
        const {
          reader_id,
          reader_name,
          moments = [],
          reading_journal,
          what_i_think_the_writer_is_doing,
          questions_for_writer = [],
          question_events = [],
          question_updates = [],
          checking_in,
          section_number,
          // Legacy fallback fields (may still arrive from cached existing reactions)
          inline_comments,
          section_reflection,
        } = data;
        const taskKey = `${reader_id}|${section_number}`;
        if (!completedTaskKeysRef.current.has(taskKey)) {
          completedTaskKeysRef.current.add(taskKey);
          setWorkflowProgress((prev) => ({ ...prev, completed: Math.min(prev.total || Infinity, prev.completed + 1) }));
          setWorkflowUsage((prev) => addUsage(prev, data.usage));
        }

        // Use moments (new schema) if present; otherwise fall back to inline_comments
        const rawMoments = moments.length > 0 ? moments : (inline_comments || []);
        const mappedComments =
          moments.length > 0
            ? _momentsToComments(moments)
            : (inline_comments || []).map((c) => ({ line: c.line, paragraph_id: c.paragraph_id || null, type: c.type, comment: c.comment }));

        setCommentsByLine((prev) => {
          const next = { ...prev };
          mappedComments.forEach((comment) => {
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

        setAllComments((prev) => {
          const seen = new Set(prev.map((item) => _commentKey(item.readerId, item.comment)));
          const additions = mappedComments
            .filter((comment) => !seen.has(_commentKey(reader_id, comment)))
            .map((comment) => ({ readerId: reader_id, readerName: reader_name, comment }));
          return additions.length ? [...prev, ...additions] : prev;
        });

        // Reading journal (new primary field, falls back to section_reflection)
        const journal = reading_journal || section_reflection || null;
        if (journal || what_i_think_the_writer_is_doing || questions_for_writer.length > 0) {
          setReflections((prev) => {
            const nextReflection = {
              readerId: reader_id,
              section_number,
              reading_journal: journal,
              what_i_think_the_writer_is_doing: what_i_think_the_writer_is_doing || null,
              questions_for_writer: Array.isArray(questions_for_writer) ? questions_for_writer : [],
              question_events: Array.isArray(question_events) ? question_events : [],
              question_updates: Array.isArray(question_updates) ? question_updates : [],
              checking_in: checking_in || null,
            };
            const key = _reflectionKey(nextReflection);
            const existingIndex = prev.findIndex((item) => _reflectionKey(item) === key);
            if (existingIndex === -1) return [...prev, nextReflection];
            const next = [...prev];
            next[existingIndex] = nextReflection;
            return next;
          });
        }

        setThinkingReaders((prev) => { const next = new Map(prev); next.delete(reader_id); return next; });
        setReaderStatus((prev) => {
          const cur = prev[reader_id] || {};
          return { ...prev, [reader_id]: { ...cur, totalComments: (cur.totalComments || 0) + mappedComments.length } };
        });

      } else if (data.type === "section_complete") {
        // nothing extra needed

      } else if (data.type === "all_complete" || data.type === "reading_complete") {
        completedNormally = true;
        readingStartedRef.current = false;
        const workflow = data.workflow;
        const genuinelyComplete = workflow ? workflow.complete : true;
        setReadingDone(genuinelyComplete);
        if (workflow) {
          setWorkflowProgress({ completed: workflow.completed_tasks, total: workflow.total_tasks, failed: workflow.failed_tasks });
          setWorkflowUsage(workflow.usage || null);
          setWorkflowBudget(workflow.budget || null);
          setWorkflowModels([...new Set((workflow.tasks || []).map((task) => task.actual_model || task.planned_model).filter(Boolean))]);
        }
        setProcessingSection(null);
        setThinkingReaders(new Map());
        setReaderStatus((prev) => {
          const next = { ...prev };
          Object.keys(next).forEach((id) => { next[id] = { ...next[id], done: true, currentSection: null }; });
          return next;
        });
        if (genuinelyComplete) {
          toast.success("Your readers have finished. Generate your Editor Report?");
        } else {
          setIsStalled(true);
          toast.warning(`${workflow?.failed_tasks || "Some"} reader task(s) still need retrying.`);
        }

      } else if (data.type === "reader_error") {
        setWorkflowProgress((prev) => ({ ...prev, failed: prev.failed + 1 }));
        if (data.reader_id) {
          setThinkingReaders((prev) => { const next = new Map(prev); next.delete(data.reader_id); return next; });
        }
        const detail = typeof data.error === "string" && data.error
          ? ` ${data.error.slice(0, 180)}`
          : "";
        toast.error(
          `${data.reader_name || "A reader"} had an error on section ${data.section_number}.` +
          `${detail} Retry will resume only the missing reader.`,
          { duration: 9000 }
        );

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
        const resp = await fetch(url, {
          signal: controller.signal,
          credentials: "include",
          headers: getManuscriptHeaders(ms.id),
        });
        if (!resp.ok || !resp.body) {
          completedNormally = true;
          readingStartedRef.current = false;
          let message = `Could not start readers (${resp.status})`;
          try {
            const body = await resp.json();
            const detail = body?.detail;
            message = typeof detail === "string" ? detail : detail?.message || message;
          } catch (_) {}
          toast.error(message, { duration: 9000 });
          return;
        }
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
    workflowProgress,
    workflowUsage,
    workflowModels,
    workflowBudget,
    esRef,
    startReadingAll,
    loadExistingReactions,
    setTotalSections,
    handleRetry,
    handleViewPartial,
  };
}
