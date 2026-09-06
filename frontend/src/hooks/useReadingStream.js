import { useState, useRef, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";

import { getApiBase } from "../apiConfig";
import { manuscriptRequestConfig } from "../manuscriptAccess";

const POLL_MS = 2000;

export function useReadingStream() {
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

  // Kept under the old name so ReadingPage can stop polling on unmount.
  const esRef = useRef(null);
  const retryRef = useRef(false);
  const readingStartedRef = useRef(false);
  const lastEventTimeRef = useRef(Date.now());

  useEffect(() => {
    if (readingDone || !readingStartedRef.current) {
      setIsStalled(false);
      return undefined;
    }
    const interval = setInterval(() => {
      if (Date.now() - lastEventTimeRef.current > 30000) setIsStalled(true);
    }, 5000);
    return () => clearInterval(interval);
  }, [readingDone]);

  const momentsToComments = (moments) =>
    (moments || []).map((moment) => ({
      line: moment.paragraph ?? moment.line,
      paragraph_id: moment.paragraph_id || null,
      type: moment.type,
      comment: moment.comment,
    }));

  const commentKey = (readerId, comment) =>
    `${readerId}|${comment.paragraph_id || comment.line || ""}|${comment.type || "reaction"}|${String(comment.comment || "").trim()}`;

  /** Rebuild visible feedback from durable reaction rows after every poll/reconnect. */
  const loadExistingReactions = useCallback((reactionsData, personasData, expectedSections = null) => {
    const nextByLine = {};
    const nextComments = [];
    const nextReflections = [];
    const seenReactions = new Set();
    const seenComments = new Set();

    (reactionsData || []).forEach((reaction) => {
      const { reader_id, reader_name, section_number } = reaction;
      const reactionKey = `${reader_id}|${section_number}`;
      if (seenReactions.has(reactionKey)) return;
      seenReactions.add(reactionKey);
      const response = reaction.response_json || {};
      const comments = (response.moments || []).length
        ? momentsToComments(response.moments)
        : (reaction.inline_comments || []).map((item) => ({
            line: item.line, paragraph_id: item.paragraph_id || null,
            type: item.type, comment: item.comment,
          }));
      comments.forEach((comment) => {
        const key = commentKey(reader_id, comment);
        if (seenComments.has(key)) return;
        seenComments.add(key);
        if (!nextByLine[comment.line]) nextByLine[comment.line] = [];
        const value = { readerId: reader_id, readerName: reader_name, comment };
        nextByLine[comment.line].push(value);
        nextComments.push(value);
      });

      const journal = response.reading_journal || reaction.section_reflection || null;
      const questions = Array.isArray(response.questions_for_writer) ? response.questions_for_writer : [];
      if (journal || response.what_i_think_the_writer_is_doing || questions.length) {
        nextReflections.push({
          readerId: reader_id, section_number, reading_journal: journal,
          what_i_think_the_writer_is_doing: response.what_i_think_the_writer_is_doing || null,
          questions_for_writer: questions,
          question_events: Array.isArray(response.question_events) ? response.question_events : [],
          question_updates: Array.isArray(response.question_updates) ? response.question_updates : [],
          checking_in: response.checking_in || null,
        });
      }
    });

    setCommentsByLine(nextByLine);
    setAllComments(nextComments);
    setReflections(nextReflections);
    const statuses = {};
    (personasData || []).forEach((persona) => {
      const rows = (reactionsData || []).filter((row) => row.reader_id === persona.id);
      const commentCount = rows.reduce((count, row) => {
        const response = row.response_json || {};
        return count + ((response.moments || []).length || (row.inline_comments || []).length);
      }, 0);
      statuses[persona.id] = {
        currentSection: rows.length && expectedSections && rows.length < expectedSections ? rows.length + 1 : null,
        done: Boolean(expectedSections && rows.length >= expectedSections),
        totalComments: commentCount,
      };
    });
    setReaderStatus(statuses);
  }, []);

  const startReadingAll = useCallback((manuscript, personas) => {
    if (readingStartedRef.current || !manuscript?.id || !personas?.length) return;
    readingStartedRef.current = true;
    setReadingDone(false);
    setIsStalled(false);
    setTotalSections(manuscript.total_sections || 0);
    const controller = new AbortController();
    let cancelled = false;
    esRef.current = { close: () => { cancelled = true; controller.abort(); readingStartedRef.current = false; } };

    (async () => {
      try {
        const ids = personas.map((persona) => persona.id).sort();
        const query = encodeURIComponent(ids.join(","));
        const retryQuery = retryRef.current ? "&retry=true" : "";
        retryRef.current = false;
        const queued = await axios.post(
          `${getApiBase()}/api/manuscripts/${manuscript.id}/jobs/reading?reader_ids=${query}${retryQuery}`,
          {}, { ...manuscriptRequestConfig(manuscript.id), signal: controller.signal },
        );
        const jobId = queued.data.id;
        let lastLoadedCompleted = -1;
        while (!cancelled) {
          const jobResponse = await axios.get(
            `${getApiBase()}/api/jobs/${jobId}`,
            { ...manuscriptRequestConfig(manuscript.id), signal: controller.signal },
          );
          lastEventTimeRef.current = Date.now();
          setIsStalled(false);
          const job = jobResponse.data;
          const progress = job.progress || {};
          setWorkflowProgress({ completed: progress.completed || 0, total: progress.total || 0, failed: progress.failed || 0 });
          if ((progress.completed || 0) !== lastLoadedCompleted || job.status === "completed") {
            const reactionsResponse = await axios.get(
              `${getApiBase()}/api/manuscripts/${manuscript.id}/all-reactions`,
              { ...manuscriptRequestConfig(manuscript.id), signal: controller.signal },
            );
            const selectedIds = new Set(ids);
            const reactions = (reactionsResponse.data || []).filter((row) => selectedIds.has(row.reader_id));
            loadExistingReactions(reactions, personas, manuscript.total_sections || 0);
            lastLoadedCompleted = progress.completed || 0;
          }
          setProcessingSection(job.progress?.section || null);
          if (job.status === "completed") {
            const workflow = job.result?.workflow || {};
            setWorkflowProgress({ completed: workflow.completed_tasks || 0, total: workflow.total_tasks || 0, failed: workflow.failed_tasks || 0 });
            setWorkflowUsage(workflow.usage || null);
            setWorkflowBudget(workflow.budget || null);
            setWorkflowModels(workflow.models || []);
            setReadingDone(true);
            setProcessingSection(null);
            setThinkingReaders(new Map());
            readingStartedRef.current = false;
            toast.success("Your readers have finished. Generate your Editor Report?");
            return;
          }
          if (job.status === "failed") {
            readingStartedRef.current = false;
            setIsStalled(true);
            toast.error(job.error || "Reading failed after automatic retries.", { duration: 9000 });
            return;
          }
          await new Promise((resolve) => setTimeout(resolve, POLL_MS));
        }
      } catch (error) {
        if (cancelled || error.code === "ERR_CANCELED") return;
        readingStartedRef.current = false;
        setIsStalled(true);
        const detail = error.response?.data?.detail;
        toast.error(typeof detail === "string" ? detail : detail?.message || "Could not start or reconnect to the reading job.");
      }
    })();
  }, [loadExistingReactions]);

  const handleRetry = useCallback((manuscript, personas) => {
    setIsStalled(false);
    esRef.current?.close();
    readingStartedRef.current = false;
    retryRef.current = true;
    startReadingAll(manuscript, personas);
  }, [startReadingAll]);

  const handleViewPartial = useCallback(() => {
    setIsStalled(false);
    esRef.current?.close();
    setReadingDone(true);
    setProcessingSection(null);
    setThinkingReaders(new Map());
    toast.info("Showing feedback saved so far. The server job will continue independently.");
  }, []);

  return {
    commentsByLine, readerStatus, reflections, allComments, thinkingReaders,
    readingDone, setReadingDone, processingSection, totalSections, isStalled,
    workflowProgress, workflowUsage, workflowModels, workflowBudget, esRef,
    startReadingAll, loadExistingReactions, setTotalSections, handleRetry, handleViewPartial,
  };
}
