import { useConfirmation } from "../components/ConfirmationProvider";
import React, { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import SiteHeader from "../components/SiteHeader";
import { Loader2 } from "lucide-react";
import axios from "axios";
import { useReadingStream } from "../hooks/useReadingStream";
import ReadingToolbar from "../components/ReadingToolbar";
import ReadingDrawer from "../components/ReadingDrawer";
import { StallBanner } from "../components/StallBanner";
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
  const [drawer, setDrawer] = useState(null);
  const [focusMode, setFocusMode] = useState(false);
  const [activeSection, setActiveSection] = useState(null);
  const drawerOrigin = useRef(null);
  const navigationTarget = useRef(null);
  const openDrawer = useCallback(kind => {
    drawerOrigin.current = document.activeElement;
    navigationTarget.current = null;
    setDrawer(kind);
  }, []);
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
    handleRetry, handleViewPartial, workflowProgress,
  } = useReadingStream(manuscriptId);

  // Stop browser polling on unmount. The durable worker continues independently.
  useEffect(() => {
    return () => { esRef.current?.close(); };
  }, [esRef]);

  useEffect(() => {
    const escape = event => {
      if (event.key === "Escape" && !drawer && openPopoverLine != null) {
        setOpenPopoverLine(null);
        document.getElementById(`note-mark-${openPopoverLine}`)?.focus({ preventScroll: true });
      }
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [drawer, openPopoverLine]);

  useEffect(() => {
    if (!manuscript) return;
    const sections = [...(manuscript.sections || [])].sort((a,b) => a.section_number - b.section_number);
    setActiveSection(sections[0]?.section_number);
    const observer = new IntersectionObserver(entries => {
      const visible = entries.find(entry => entry.isIntersecting);
      if (visible) setActiveSection(Number(visible.target.id.replace("section-", "")));
    }, { root: document.getElementById("main-content"), rootMargin: "-5% 0px -75% 0px" });
    document.querySelectorAll(".book-section").forEach(section => observer.observe(section));
    return () => observer.disconnect();
  }, [manuscript]);

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
    navigationTarget.current = targetId;
    setDrawer(null);
    if (openLine != null) setFocusMode(false);
    const element = document.getElementById(targetId);
    if (!element) return;
    setOpenPopoverLine(openLine);
    window.history.replaceState(null, "", `#${targetId}`);
    window.requestAnimationFrame(() => {
      element.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
      element.focus({ preventScroll: true });
    });
    element.classList.add("reader-nav-highlight");
    window.setTimeout(() => element.classList.remove("reader-nav-highlight"), 1800);
  }, []);

  const handleOpenPopover = useCallback((lineNumber) => {
    setOpenPopoverLine((prev) => (prev === lineNumber ? null : lineNumber));
    if (lineNumber != null) window.requestAnimationFrame(() => {
      document.getElementById(`note-mark-${lineNumber}`)?.closest(".prose-paragraph")?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
    });
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
    <div className="reading-workspace">
      <ReadingToolbar drawer={drawer} openDrawer={openDrawer} focusMode={focusMode} setFocusMode={value => { setFocusMode(value); if (value) setOpenPopoverLine(null); }} readingDone={readingDone} processingSection={processingSection} totalSections={totalSections} progress={progress} totalCommentCount={totalCommentCount} loadingReport={loadingReport} generateReport={openOrGenerateReport} />
      <main id="main-content" tabIndex={-1} className="reading-canvas">
        {isStalled && !readingDone && <div className="reading-stall"><StallBanner onRetry={() => handleRetry(manuscript, personas)} onViewPartial={handleViewPartial} /></div>}
        <ManuscriptView manuscript={manuscript} commentsByLine={commentsByLine} personas={personas} openPopoverLine={openPopoverLine} onOpenPopover={handleOpenPopover} readingDone={readingDone} totalCommentCount={totalCommentCount} focusMode={focusMode} onOpenReaders={() => openDrawer("readers")} onNavigate={navigateToManuscript} />
      </main>
      <ReadingDrawer drawer={drawer} close={() => setDrawer(null)} origin={drawerOrigin} navigationTarget={navigationTarget}>
        {drawer === "contents" ? <nav className="book-contents" aria-label="Manuscript sections">
          <button className="contents-title" onClick={() => navigateToManuscript("manuscript-start")}>{manuscript.title}<span>Beginning of manuscript</span></button>
          {[...(manuscript.sections || [])].sort((a,b) => a.section_number - b.section_number).map(section => <button key={section.section_number} onClick={() => navigateToManuscript(`section-${section.section_number}`)} aria-current={activeSection === section.section_number ? "location" : undefined}><span>{section.section_number}</span>{section.title || `Section ${section.section_number}`}</button>)}
        </nav> : <ReaderSidebar manuscriptId={manuscriptId} onNavigate={navigateToManuscript} personas={personas} readerStatus={readerStatus} reflections={reflections} allComments={allComments} thinkingReaders={thinkingReaders} totalCommentCount={totalCommentCount} activeTypes={activeTypes} toggleType={toggleType} setActiveTypes={setActiveTypes} isStalled={isStalled} readingDone={readingDone} onRetry={() => handleRetry(manuscript, personas)} onViewPartial={handleViewPartial} />}
      </ReadingDrawer>
    </div>
  );
}
