import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import axios from "axios";
import { useReadingStream } from "../hooks/useReadingStream";
import { ProgressBar } from "../components/ProgressBar";
import { ManuscriptView } from "../components/ManuscriptView";
import { ReaderSidebar } from "../components/ReaderSidebar";
import { getApi } from "../apiConfig";

const API = getApi();

export default function ReadingPage() {
  const { manuscriptId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const selectedReaderIdsFromState = location.state?.selectedReaderIds;

  // Page-owned state
  const [manuscript, setManuscript] = useState(null);
  const [personas, setPersonas] = useState([]);
  const [loadingReport, setLoadingReport] = useState(false);
  const [openPopoverLine, setOpenPopoverLine] = useState(null);
  const [activeTypes, setActiveTypes] = useState(new Set());

  // All SSE-driven state comes from the hook
  const {
    commentsByLine, readerStatus, reflections, allComments,
    thinkingReaders, readingDone, setReadingDone, processingSection, totalSections,
    setTotalSections, isStalled, esRef, startReadingAll, loadExistingReactions,
    handleRetry, handleViewPartial,
  } = useReadingStream(manuscriptId);

  // Close stream when user leaves the page so the backend pauses reader pipelines
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
      const personaList = Array.isArray(pRes.data) ? pRes.data : [];
      setManuscript(mRes.data);
      const selectedIds = selectedReaderIdsFromState && selectedReaderIdsFromState.length > 0
        ? selectedReaderIdsFromState
        : null;
      const personaListToUse = selectedIds
        ? personaList.filter((p) => selectedIds.includes(p.id))
        : personaList;
      setPersonas(personaListToUse);

      const rRes = await axios.get(`${API}/manuscripts/${manuscriptId}/all-reactions`);
      const totalSecs = mRes.data.total_sections || 0;
      const existing = rRes.data || [];
      const sectionsWithReactions = new Set(existing.map((r) => r.section_number));
      const allDone = totalSecs > 0 && personaListToUse.length > 0 && sectionsWithReactions.size >= totalSecs && existing.length >= totalSecs * personaListToUse.length;

      if (existing.length > 0) loadExistingReactions(existing, personaListToUse);
      if (allDone) {
        setTotalSections(mRes.data.total_sections || 0);
        setReadingDone(true);
      } else {
        startReadingAll(mRes.data, personaListToUse);
      }
    } catch (err) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail ?? err.response?.data?.message;
      const msg = typeof detail === "string" ? detail : (Array.isArray(detail) ? detail.map((d) => d.msg ?? d).join(", ") : err.message);
      if (status === 404) {
        toast.error("Manuscript not found. It may have been deleted or the link is wrong.");
      } else {
        toast.error(msg || "Failed to load manuscript");
      }
    }
  };

  useEffect(() => { loadData(); }, [manuscriptId, selectedReaderIdsFromState]);

  const generateReport = async () => {
    setLoadingReport(true);
    try {
      await axios.post(`${API}/manuscripts/${manuscriptId}/editor-report`);
      navigate(`/report/${manuscriptId}`);
    } catch (err) {
      const detail = err.response?.data?.detail ?? err.response?.data?.message;
      const msg = typeof detail === "string" ? detail : (Array.isArray(detail) ? detail.map((d) => d.msg ?? d).join(", ") : null);
      toast.error(msg || "Failed to generate report. Make sure readers have finished at least one section.");
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
