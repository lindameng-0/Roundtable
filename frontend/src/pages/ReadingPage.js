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
import { manuscriptRequestConfig } from "../manuscriptAccess";

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
    handleRetry, handleViewPartial, workflowProgress, workflowUsage, workflowModels, workflowBudget,
  } = useReadingStream(manuscriptId);

  // Stop browser polling on unmount. The durable worker continues independently.
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
        axios.get(`${API}/manuscripts/${manuscriptId}`, manuscriptRequestConfig(manuscriptId)),
        axios.get(`${API}/manuscripts/${manuscriptId}/personas`, manuscriptRequestConfig(manuscriptId)),
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

      const rRes = await axios.get(`${API}/manuscripts/${manuscriptId}/all-reactions`, manuscriptRequestConfig(manuscriptId));
      const totalSecs = mRes.data.total_sections || 0;
      const existing = rRes.data || [];
      const selectedPersonaIds = new Set(personaListToUse.map((persona) => persona.id));
      const selectedExisting = existing.filter((reaction) => selectedPersonaIds.has(reaction.reader_id));
      const completedPairs = new Set(selectedExisting.map((reaction) => `${reaction.reader_id}|${reaction.section_number}`));
      const allDone = totalSecs > 0 && personaListToUse.length > 0 && completedPairs.size >= totalSecs * personaListToUse.length;

      if (selectedExisting.length > 0) loadExistingReactions(selectedExisting, personaListToUse, totalSecs);
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

  useEffect(() => {
    if (!manuscript || !window.location.hash) return;
    const paragraphId = window.location.hash.slice(1);
    const timer = setTimeout(() => {
      document.getElementById(paragraphId)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 250);
    return () => clearTimeout(timer);
  }, [manuscript]);

  const openOrGenerateReport = async () => {
    setLoadingReport(true);
    try {
      const config = manuscriptRequestConfig(manuscriptId);
      const existing = await axios.get(`${API}/manuscripts/${manuscriptId}/editor-report`, config).catch((error) => {
        if (error.response?.status === 404) return null;
        throw error;
      });
      if (!existing) {
        const estimateRes = await axios.get(`${API}/manuscripts/${manuscriptId}/cost-estimate?operation=editor`, config);
        const estimate = Number(estimateRes.data.estimated_cost_usd || 0);
        if (!estimateRes.data.can_start) {
          toast.error(`The editor is estimated at $${estimate.toFixed(3)}, above the remaining manuscript budget.`);
          return;
        }
        if (!window.confirm(`Generate the editor report? This is estimated to use about $${estimate.toFixed(3)} of AI credit.`)) return;
        await axios.post(`${API}/manuscripts/${manuscriptId}/editor-report`, {}, config);
      }
      navigate(`/report/${manuscriptId}`);
    } catch (err) {
      const detail = err.response?.data?.detail ?? err.response?.data?.message;
      const msg = typeof detail === "string" ? detail : (Array.isArray(detail) ? detail.map((d) => d.msg ?? d).join(", ") : null);
      toast.error(msg || "Failed to generate report. Make sure readers have finished at least one section.");
    } finally {
      setLoadingReport(false);
    }
  };

  const navigateToManuscript = useCallback((targetId, openLine = null) => {
    if (!targetId) return;
    const element = document.getElementById(targetId);
    if (!element) return;
    setOpenPopoverLine(openLine);
    window.history.replaceState(null, "", `#${targetId}`);
    element.scrollIntoView({ behavior: "smooth", block: "center" });
    element.classList.add("reader-nav-highlight");
    window.setTimeout(() => element.classList.remove("reader-nav-highlight"), 1800);
  }, []);

  const handleOpenPopover = useCallback((lineNumber) => {
    setOpenPopoverLine((prev) => (prev === lineNumber ? null : lineNumber));
  }, []);

  const toggleType = (type) => {
    setActiveTypes((prev) => { const next = new Set(prev); next.has(type) ? next.delete(type) : next.add(type); return next; });
  };

  const progress = workflowProgress.total > 0
    ? (workflowProgress.completed / workflowProgress.total) * 100
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
        generateReport={openOrGenerateReport}
        progress={progress}
        workflowProgress={workflowProgress}
        workflowUsage={workflowUsage}
        workflowModels={workflowModels}
        workflowBudget={workflowBudget}
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
          generateReport={openOrGenerateReport}
          loadingReport={loadingReport}
        />
        <ReaderSidebar
          manuscriptId={manuscriptId}
          onNavigate={navigateToManuscript}
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
