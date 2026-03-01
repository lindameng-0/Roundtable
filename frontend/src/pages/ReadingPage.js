import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import axios from "axios";

import { useReadingStream } from "../hooks/useReadingStream";
import { ProgressBar } from "../components/ProgressBar";
import { ManuscriptView } from "../components/ManuscriptView";
import { ReaderSidebar } from "../components/ReaderSidebar";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

export default function ReadingPage() {
  const { manuscriptId } = useParams();
  const navigate = useNavigate();

  // Page-owned state
  const [manuscript, setManuscript] = useState(null);
  const [personas, setPersonas] = useState([]);
  const [loadingReport, setLoadingReport] = useState(false);
  const [openPopoverLine, setOpenPopoverLine] = useState(null);
  const [activeTypes, setActiveTypes] = useState(new Set());

  // All SSE-driven state comes from the hook
  const {
    commentsByLine, readerStatus, reflections, allComments,
    thinkingReaders, readingDone, processingSection, totalSections,
    isStalled, esRef, startReadingAll, loadExistingReactions,
    handleRetry, handleViewPartial,
  } = useReadingStream(manuscriptId);

  // Close stream on unmount
  useEffect(() => {
    return () => { esRef.current?.close(); };
  }, [esRef]);

  useEffect(() => {
    const handler = () => setOpenPopoverLine(null);
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, []);

  const loadData = async () => {
    try {
      const [mRes, pRes] = await Promise.all([
        axios.get(`${API}/manuscripts/${manuscriptId}`),
        axios.get(`${API}/manuscripts/${manuscriptId}/personas`),
      ]);
      setManuscript(mRes.data);
      setPersonas(pRes.data);

      const rRes = await axios.get(`${API}/manuscripts/${manuscriptId}/all-reactions`);
      const totalSecs = mRes.data.total_sections || 0;
      const existing = rRes.data || [];
      const sectionsWithReactions = new Set(existing.map((r) => r.section_number));
      const allDone = totalSecs > 0 && sectionsWithReactions.size >= totalSecs && existing.length >= totalSecs * pRes.data.length;

      if (existing.length > 0) loadExistingReactions(existing, pRes.data);
      if (!allDone) startReadingAll(mRes.data, pRes.data);
      else {
        // Mark done but don't start stream
        const { setReadingDone } = await import("../hooks/useReadingStream");
      }
    } catch {
      toast.error("Failed to load manuscript");
    }
  };

  useEffect(() => { loadData(); }, [manuscriptId]);

  const generateReport = async () => {
    setLoadingReport(true);
    try {
      await axios.post(`${API}/manuscripts/${manuscriptId}/editor-report`);
      navigate(`/report/${manuscriptId}`);
    } catch {
      toast.error("Failed to generate report. Make sure readers have finished at least one section.");
    } finally {
      setLoadingReport(false);
    }
  };

  const handleOpenPopover = useCallback((lineNumber) => {
    setOpenPopoverLine((prev) => (prev === lineNumber ? null : lineNumber));
  }, []);

  const toggleType = (type) => {
    setActiveTypes((prev) => { const next = new Set(prev); next.has(type) ? next.delete(type) : next.add(type); return next; });
  };

  const progress = totalSections > 0 && processingSection
    ? ((processingSection - 1) / totalSections) * 100
    : readingDone ? 100 : 0;

  const totalCommentCount = allComments.length;

  if (!manuscript) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-clay" strokeWidth={1.5} />
      </div>
    );
  }

  return (
    <div className="h-screen bg-paper flex flex-col overflow-hidden" style={{ fontFamily: "'Manrope', sans-serif" }}>
      <ProgressBar
        manuscript={manuscript}
        navigate={navigate}
        readingDone={readingDone}
        processingSection={processingSection}
        totalSections={totalSections}
        loadingReport={loadingReport}
        generateReport={generateReport}
        progress={progress}
      />

      <div className="flex flex-1 overflow-hidden">
        <ManuscriptView
          manuscript={manuscript}
          commentsByLine={commentsByLine}
          personas={personas}
          openPopoverLine={openPopoverLine}
          onOpenPopover={handleOpenPopover}
          readingDone={readingDone}
          totalSections={totalSections}
          totalCommentCount={totalCommentCount}
          generateReport={generateReport}
          loadingReport={loadingReport}
        />
        <ReaderSidebar
          personas={personas}
          readerStatus={readerStatus}
          reflections={reflections}
          allComments={allComments}
          thinkingReaders={thinkingReaders}
          totalCommentCount={totalCommentCount}
          activeTypes={activeTypes}
          toggleType={toggleType}
          setActiveTypes={setActiveTypes}
          isStalled={isStalled}
          readingDone={readingDone}
          onRetry={() => handleRetry(manuscript, personas)}
          onViewPartial={handleViewPartial}
        />
      </div>
    </div>
  );
}
