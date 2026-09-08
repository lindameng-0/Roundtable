import { useConfirmation } from "../components/ConfirmationProvider";
import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import SiteHeader from "../components/SiteHeader";
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
  const confirm = useConfirmation();
  const { manuscriptId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const selectedReaderIdsFromState = location.state?.selectedReaderIds;

  // Page-owned state
  const [mobilePanel, setMobilePanel] = useState("manuscript");
  const [loadError, setLoadError] = useState("");
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
    const escape = event => { if (event.key === "Escape") handler(); };
    document.addEventListener("click", handler);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("click", handler); document.removeEventListener("keydown", escape); };
  }, []);

  const loadData = async () => {
    setLoadError("");
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
      setLoadError(status === 404 ? "This manuscript could not be found." : "We couldn’t load this reading. Please try again.");
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
        const estimate = Number(estimateRes.data.estimated_credits || 0);
        if (!estimateRes.data.can_start) {
          toast.error(`The editor needs about ${estimate.toFixed(2)} credits. Add credits on the billing page to continue.`);
          return;
        }
        if (!(await confirm({ title: "Create your editorial report?", description: `Estimated usage: ${estimate.toFixed(2)} credits. The final amount depends on response length.`, action: "Create report" }))) return;
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
    setMobilePanel("manuscript");
    const element = document.getElementById(targetId);
    if (!element) return;
    setOpenPopoverLine(openLine);
    window.history.replaceState(null, "", `#${targetId}`);
    window.requestAnimationFrame(() => element.scrollIntoView({ behavior: "smooth", block: "center" }));
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
    return <div><SiteHeader /><main id="main-content" className="feedback-state" tabIndex={-1}>{loadError ? <div role="alert"><p>{loadError}</p><button className="button button-quiet" onClick={loadData}>Try again</button></div> : <div role="status"><Loader2 className="animate-spin mb-3" size={22} />Opening the reading room…</div>}</main></div>;
  }

  return (
    <div className="reading-page bg-paper flex flex-col overflow-hidden" style={{ fontFamily: "'DM Sans', sans-serif" }}>
      <SiteHeader />
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

      <div className="mobile-reading-tabs" role="group" aria-label="Reading view"><button onClick={() => setMobilePanel("manuscript")} aria-pressed={mobilePanel === "manuscript"}>Manuscript</button><button onClick={() => setMobilePanel("readers")} aria-pressed={mobilePanel === "readers"}>Reader notes ({totalCommentCount})</button></div>
      <main id="main-content" tabIndex={-1} className="reading-panels" data-panel={mobilePanel}>
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
      </main>
    </div>
  );
}
